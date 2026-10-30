# Incomplete Gx runs after the cylinder mesh change

## Confirmed cause

The reported Gx run was stopped by a coordinate-projection bug after its wire
clearance recovery had already succeeded. The recovery result was discarded,
the original colliding path was restored, and five alternative interconnections
were attempted. This is not evidence that the requested winding cannot fit.

The saved run used B0=+Y, R=50 mm, cylinder height=120 mm (mesh height=114 mm),
ROI radii=30 mm, a 40 x 40 mesh, Tikhonov=2500, 20 levels, 2 mm circular cable,
groove factors A=2/B=1, 1 mm connection cuts and [7,7,7] shift smoothing.
`reassign_crossing_layers` was false; the reproduction preserves that setting.

The original geometry JSON records 1035 contacting segment pairs in nine
displayed areas, with minimum centerline distance 0.0015125566 mm. It also records
a repaired candidate with minimum 2.0202318 mm, followed by:

```
Cannot project repaired turns onto the cylinder mesh.
```

`_updated_uv` first projected the repaired stations onto an ideal circular
cylinder, then measured their distance to the mesh's flat triangles. It rejected
distances above 5% of the cable diameter: 0.1 mm here. The maximum gap between
the ideal circle and a facet is `R * (1 - cos(pi / n_circ))`:

| Circumferential divisions | Gap at R=50 mm | Old result |
| --- | ---: | --- |
| 200 | 0.0061684 mm | Accepted |
| 40 | 0.1541333 mm | Rejected |

Thus a valid repair could be rejected solely because of mesh discretization.
The threshold also depends on radius and cable diameter, so other dimensions
may trigger the same defect even at other mesh resolutions.

## Version history

The histories were read directly with Git, including the current GitHub heads.

| Date (Chile) | Revision | Relevant behavior |
| --- | --- | --- |
| 2026-08-20 18:58 | [cSOZAo `dcb2b15`](https://github.com/cSOZAo/halbach-gradient-coils/commit/dcb2b15035f17f924d834d4c49976f0cac3214a1) | Added crossing metadata and an overridable congestion warning. It did not perform the present complete 3D distance check. |
| 2026-10-24 17:32 | [AutoGrad `01c8408`](https://github.com/CIB-UC/AutoGrad/commit/01c8408) | First published application snapshot in this repository already includes mandatory 3D clearance checks, bounded repair, alternative-route retries and the defective UV projection. The import does not retain separate commits for these internal changes. |
| 2026-10-28 16:46 | [AutoGrad `705f97e`](https://github.com/CIB-UC/AutoGrad/commit/705f97e26ede05855466fd5ebe506ef7a943c23c) | Changed cylinder defaults from 200 x 10 to 40 x 40, activating the projection regression for the reported dimensions. |
| 2026-10-29 22:52 | [AutoGrad `12e5d91`](https://github.com/CIB-UC/AutoGrad/commit/12e5d91) | Added the crossing-layer reassignment control. Disabling it can leave more work for recovery, but does not explain the rejection of an already separated candidate. |

These are two distinct changes: stricter physical validation exposes some real
contacts that earlier runs could overlook; the mesh/projection incompatibility
then prevents this particular recoverable winding from completing. Historical
completion alone does not certify clearance, and the current partial-result
message incorrectly suggests lack of space when projection is the actual cause.

The local checkout is based on the older `dac090f` history with substantial
existing uncommitted changes. The relevant recovery code also exists in the
published AutoGrad history; it is not exclusively local. No checkout, reset,
commit or publication was performed during this investigation.

## Correction

UV coordinates now come from radial intersections with the actual mesh
triangles at the repaired station's existing height. Barycentric containment
must succeed. The operation changes the coordinate reference, not the repaired
3D trajectory. It supports rotated cylinders and coarse facets, and still
rejects stations outside the axial mesh.

The round-wire distance check, recovery bounds, cylinder dimensions, cable
diameter, level count, Tikhonov and routing options are unchanged. A failed UV
projection still restores the original path. Its diagnostic now reports the
restored path's minimum and saves the rejected candidate's minimum separately,
instead of mixing the two geometries.

## Reproduction evidence

The saved winding was reproduced before and after the fix, independently of
optimization and routing retries:

| Measurement | Before | After |
| --- | ---: | ---: |
| Initial contacting pairs | 1035 | 1035 |
| Retained contacting pairs | 1035 | 0 |
| Retained minimum distance | 0.0015126 mm | 2.0203524 mm |
| Largest accepted displacement | 0 mm (rollback) | 2.7134777 mm |
| Direct recovery time | 6.64 s (then rejected) | 6.28 s (accepted) |

The independent exact global check confirms zero remaining contacts. Radial and
axial bounds and the number of stations are preserved. Timing is illustrative,
not a controlled performance benchmark.

`tests/test_data/gx_40x40_projection.npz` contains only the reported trajectory
in SI coordinates, without pickled objects or machine paths. Regression tests
cover the actual winding, 200/40/16 circumferential divisions, rotated cylinders,
axial rejection and diagnostic consistency on rollback.

Local reproduction scripts, before/after JSON and separate pipeline runs are
retained under `scratchpad/regression_20261029/`. The user's original result
directory is left intact. FastHenry is disabled for these geometry reproductions.

## Full-pipeline check and remaining limitation

The saved winding configuration was rerun with the fix, including the saved
false crossing-reassignment setting. The design sidecar does not save the user's
lead or shell settings. The reproduction therefore used `Config` defaults for
those stages, rather than a verified copy of the user's GUI terminal settings.
Specifically, leads used the Gx preset (exit -Z, preferred sector +Y, angular
half-width 0.35 rad), a 20 mm initial cut, 15 mm initial tip separation, minimum
bend radius 6 mm, surface clearance 0.3 mm and initial exit margin 5 mm. Automatic
search expands cut, separation, sector and exit options. Consequently, the
terminal-stage failure below is a result for these test settings; it is not
evidence that the user's own terminal settings fail.

The winding passed with zero contact
areas, minimum separation 2.0202318 mm and maximum displacement 2.7130610 mm.
No alternative winding interconnections were attempted. pyCoilGen reported
82.39 s, compared with 168.87 s in the supplied log; these are separate runs,
not a controlled timing benchmark.

The pipeline then reached terminal generation. The lead planner rejected its
10 sector/exit variants with tangent, section-plane and bend-radius failures.
The run returned `needs_revision` after 120.56 s and did not carve a mold.
That is a second limitation, not a remaining winding-clearance failure. Its
causality has not been established merely by fixing projection. In particular,
this investigation does not claim a complete manufacturable coil or validated
FastHenry values for this configuration.

The lead planner was also run independently against the user's original,
unrepaired sweep reference, again using the default terminal settings above.
It rejected all 10 variants in 72.36 s, with the
same categories of tangent, section-plane, bend-radius and clearance failures.
This establishes that terminal rejection is not introduced by the UV fix or
by accepting the repaired trajectory. It does not prove that no physically
possible terminal route exists beyond the implemented search.

## Historical mesh comparison and another performance issue

An additional run changed only the mesh back to 200 x 10 while retaining the
current clearance checks. It still exhausted all five winding-route retries.
pyCoilGen exported a 7071-station path after 291.30 s. An independent exact
check of that exported reference found 11604 contacting segment pairs and
minimum separation 1.3808975 mm. Returning to the old mesh alone therefore
does not produce a physically accepted result for these parameters.

The comparison was deliberately stopped after export and independent checking,
while `detect_collisions` was grouping the contacts. It was not a completed
historical-version pipeline run. `_cluster_records` checks every pair of contact
records in nested Python loops: 67320606 proximity comparisons for 11604
records, solely to group diagnostic locations. This is another concrete source
of poor scaling when a winding has many contacts. It does not alter the exact
physical distance verdict. That grouping implementation and the terminal
planner were left unchanged in this fix.

The focused geometry/routing group passed 36 tests in 64.45 s, and the focused
projection/pipeline/lead group passed 39 tests in 49.04 s. There are 66 distinct
tests across the two groups; the overlapping projection and rollback tests ran
in both. The first regression run failed at the 40- and 16-division projection
cases before the implementation changed. At that focused-investigation stage,
the full repository suite had not yet been run.

## Subsequent successful user run

The user subsequently completed a new Gx run in `test`. Its saved configuration
differs from the investigated 20-level case: it uses 10 levels, 1 mm layer gap,
crossing reassignment enabled and 16 cross-section samples (instead of 20 levels,
zero layer gap, reassignment disabled and 12 samples). Radius, height, ROI,
Tikhonov and mesh match the reported values above. These are distinct winding
configurations, even though their lead search uses the same default options.

The new job records `completed`, with no partial result. Winding diagnostics
record zero contacts without repair. The lead report records validated terminal
geometry, retained original vertices and zero solid intersections at the two
junctions. The mold STL is present. Final simulated slope is
2.136933 mT/(m A), and FastHenry reports success with R=0.0279225 ohm and
L=8.837428 microhenry. This successful run supersedes any interpretation that
terminal generation fails generally; the earlier rejection applies only to the
specific 20-level configuration and search settings documented above.

## Publication validation

For the requested GitHub update, the six changed files were applied to a clean
worktree based on published `main` (`eb9c585`), without changing unrelated local
work. The full suite passed **504 tests in 196.87 s**, with two existing
SciPy-fixture deprecation warnings. `pip check`, Pipeline CLI help and staged
whitespace checks passed. The exported conductor with terminals and mold from
the successful user run were also reloaded: both were watertight, consistently
oriented meshes with positive volume.
