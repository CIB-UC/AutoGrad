# Interference recovery and GUI result states

Implementation and verification history, October 24, 2026. Numerical examples
refer to the recorded runs; they are not universal manufacturing guarantees.

## Physical checks and recovery bounds

Round-wire clearance is always checked in sweeps and Pipeline. Disabling overlap
messages reduces logging only; it does not disable physical validation.

After connecting contours, shifting crossings and cleaning the path before
solid sweeping, the engine tries to separate neighboring turns that remain too
close. It preserves layer radii, available height, path order and level count;
it does not change Tikhonov, ROI or assembly dimensions. Already valid paths are
left unchanged.

The first recovery stage uses smooth local moves on cylindrical layers, bounded
by half a cable diameter per station. If a chain of turns remains crowded, a
joint solution applies a smooth, monotone cubic axial transformation. It keeps
XY exactly, preserves available height, bounds movement to two diameters and
keeps the transformation derivative between 0.5 and 1.5. Linear programming
finds a minimal adjustment, followed by exact segment-distance checks; optimizer
approximations do not certify geometry. These stages share 24 iterations and
a 20 s budget. Their small target margin does not enlarge the excluded connected
neighborhood. Crossings requiring another route/layer assignment keep a diagnostic.

Repeated intersections at a contour vertex are also deduplicated. The earlier
implementation mixed rows and columns while removing duplicates and could
normalize a zero-length vector. UV points, XYZ points and segment indices now
remain synchronized before selecting the two cuts.

A repaired trajectory is accepted only if it passes the complete check and can
be projected onto the mesh to update UV coordinates and normals. Otherwise the
original is restored. Field, length, resistance, leads and mold use the actual
exported trajectory. Final-conductor and assembly checks remain independent.

## Results requiring revision

Known interference or infeasible terminal routing returns
`PipelineResult.needs_revision`, with a message and retained artifacts. The GUI
shows a warning and marks the job partial. A failed conductor is not used to
carve a mold.

In a batch, that axis becomes `needs_revision` and other axes continue. Assembly
waits for every selected axis to have valid geometry. Assembly interference or
unplaceable keys likewise produces a reviewable partial result while preserving
completed layers. Unexpected errors and cancellation retain distinct states.

The localized diagnostics directory contains `*_geometry.json`, recording
status, required separation, contacts, attempts and applied displacement. The run
summary links the report and shows maximum adjustment.

## Tikhonov sweeps

Rows/CSV include `Geometry_status`, contact-zone count and a report path. States
are `valid`, `interference`, `failed` and `unchecked`. Only valid rows with finite
metrics may be recommended by slope/error. Fine search stays inside requested
Tikhonov limits.

If no feasible geometry is found, all attempts are saved and recommendations
remain empty. The GUI retains the table and suggests reviewing space, levels
or range. Older CSVs without clearance evidence are unverified and cannot be
applied as validated recommendations. Sweeps check the winding; the full pipeline
checks terminals and assembly.

## Reproducing the 20-level Gy failure

The batch used B0=+Y, height 170 mm, ROI radii 50 mm, cable 2 mm, groove A=2/B=1,
1 mm cuts and `[7,7,7]` smoothing. Complete anchor radius was 55 mm, gradient gap
0.3 mm, Z/X/Y levels 3/20/20 and Tikhonov 10000/28480/38495.

| Gy result | Value |
| --- | ---: |
| Mold outer radius | 77.6 mm |
| Initial minimum branch separation | 1.870983 mm |
| Initial contacting segment pairs | 38 in two zones |
| Final minimum including leads | 2.025412 mm |
| Maximum adjustment | 0.235670 mm |
| Iterations | 7 |
| Final length | 15.743051 m |
| Final simulated slope | 2.558515 mT/(m·A) |
| Analytical / FastHenry R | 0.08418764 / 0.084186 Ω |
| FastHenry L | 73.81750 µH |

Gz/Gx needed no new turn-spacing adjustment. All axes and assembly completed.
Final molds were reloaded in mm: closed, consistently oriented, one positive-volume
body. Conductor hashes and saved final trajectories were rechecked. Historical
local evidence is in `ahorasi_robusto_20261024`, including presets, conductors,
molds, assembly, plots, reports and logs. Field error and CAD validity are
separate results; some diameter/space/level combinations remain infeasible.

At that implementation stage the full suite passed **463 tests** with no skips,
two old SciPy-fixture deprecation warnings, successful `pip check` and CLI help.
Coverage included the real Gy, radial/height bounds, rotated cylinders, UV updates,
budget exhaustion, rollback, unchanged valid routes, sweep recommendations,
infeasible/legacy CSVs, continued batch axes, partial states and bilingual GUI
controls. Later general verification is recorded in [VALIDATION.md](VALIDATION.md).

## Second case: Gy at 69.6 mm, a crowded chain

The next batch used a 51 mm anchor and 1 mm Gz cable. Mold outer radii were
Z/X/Y = 54/61.3/69.6 mm; levels remained 3/24/20 and Tikhonov
10000/28480/38495. The reduced Gy radius leaves less turn space than the earlier
77.6 mm case, despite unchanged electrical parameters.

Two distinct defects appeared: a duplicate cut at a vertex caused a divide by
zero in `find_group_cut_position`, and four regions contained a chain of crowded
turns. Local recovery exhausted its budget and reverted; extending to 120
iterations still failed. Fixing duplicate cuts alone did not fix the contacts.

Older checks examined selected projected crossings/layers. Current checks also
measure 3D distances between turns without a projected crossing, exposing contacts
in calculations that previously finished. A new full batch used matching per-axis
configuration JSON, within SI rounding, and joint recovery:

| Gy at 69.6 mm | Value |
| --- | ---: |
| Initial minimum separation | 1.718620 mm |
| Final minimum including leads | 2.038990 mm |
| Maximum axial movement | 3.388272 mm |
| Radii and available height | Preserved |
| Iterations | 12 local + 1 joint solve |
| Levels / Tikhonov | 20 / 38495, unchanged |
| Final length | 15.588987 m |
| Final simulated slope | 3.285959 mT/(m·A) |
| Final mean target-field error | 1.358205 % |
| Analytical / FastHenry R | 0.08336376 / 0.0833619 Ω |
| FastHenry L | 75.10458 µH |

All axes, terminals, molds and keys completed. Nine final STLs (conductors,
individual molds and assembly molds) were reloaded: closed, one body, consistent
orientation, positive volume and correct dimensions/units. Conductor hashes,
trajectories and all 18 assembly checks were verified. Evidence is in
`Gx_Gy_robusto_20261024_v2`, including presets and
`Diagnostico/verificacion_exportados.json` under its historical layout. Regressions
cover vertex/seam cuts, the real chain, exact XY preservation, axial monotonicity,
recovery bounds and closest-point segment parameters.

## Connection recovery in batches without Z

An X/Y batch with 1.5 mm cable, 22 levels and Gy radius 65.8 mm produced same-layer
contacts with minimum 0.000535 mm. Local spacing returned
`crossing_requires_different_routing` without retrying interconnections. This
required a route change as well as turn spacing.

After an invalid first route, the engine preserves contours and rebuilds only
connections and shifts. Automatic cut mode tries the opposite side and openings
of at least two/three cable diameters, up to five distinct alternatives. Explicit
side requests are respected. Independent group copies prevent contamination
between attempts; stream-function optimization, Tikhonov, levels, radius, height
and diameter remain unchanged.

A candidate is accepted only if every path passes full physical checks. Field
evaluation/export then use the selected parts. If none passes, the first result
and diagnostic are preserved with complete attempt history. `routing_recovery`
records requested/effective cuts and all attempts. At that stage only **three
focused tests** ran, covering recovery, independent attempts, retained results
and side selection. The full batch/suite was intentionally not rerun then.

## Verified 22-level Gy crossing recovery

A subsequent log confirmed that all five cut alternatives failed. Spatial
recovery now precedes those retries and can move branches radially within their
existing envelope. Earlier spacing allowed only tangential moves and rejected
nearly coincident intersections. Axial bounds, path order and stations are
preserved; failed attempts restore the original.

Recovery compares affected segments and neighbors against the full path. Before
acceptance, an independent exact global check is performed. This reduces repeated
global searches without reducing final validation.

`gy_crossing_22_levels.npz` preserves the failing Gy (Tikhonov 38495, 22 levels,
1.5 mm cable, design radius 65.8 mm). Its focused result was:

| Measurement | Value |
| --- | ---: |
| Initially contacting pairs | 38 |
| Initial minimum | 0.000535163 mm |
| Adjusted minimum | 1.515095 mm |
| Required separation | 1.5 mm |
| Maximum movement | 1.810955 mm |
| Iterations | 155 |
| Measured adjustment time | 2.31 s |
| Contacts in final global check | 0 |

Radial range and available height were preserved. Analytical cylindrical normals
also yielded zero contacts and minimum 1.515034 mm. UV update and pre-sweep
integration passed a regression on the real geometry.

Remaining cut-recovery candidates are checked before solid construction. An
accepted candidate retains its already cleaned path, without trimming stations
again. Generated cylinders use known radial normals instead of a UV triangle
search per station. Spherical cutting also fixes an exclusive slice endpoint
that dropped single-station candidates and produced empty-mean warnings.

**Nine focused tests passed in 7.52 s**, covering real geometry, envelope/height,
active/global distance equivalence, budget exhaustion, UV updates, selective
solid finalization and single-station cuts. At that stage, full batch, terminals,
molds and assembly were left for the user's run rather than claimed verified.

## Winding closure in physical checks

The next X/Y batch passed that spacing stage but failed final-conductor checks.
Solid sweeping always connects its last section to the first, while prior checks
visited only consecutive stations and inferred closure from endpoint distance.
The endpoints were 3.130792 mm apart, more than the cable diameter, so the closing
segment was omitted until final lead evaluation recovered it.

`tests/test_data/gy_closing_segment.npz` preserves the real Gy, original terminals
and cut indices. Four contacts involve the closing segment, with minimum
0.119348 mm. The earlier report therefore falsely showed no contacts.

Recovery now explicitly represents closure before adjusting the winding while
preserving its original station count and section correspondence. Route selection
and independent swept-winding checks include that same segment. Final paths
between terminals remain open.

This reference needed five iterations and at most 1.418352 mm movement within
existing radial/axial bounds. Reconstructing the corrected path with the same
terminals and cut gave zero contacts and minimum 1.515034 mm for 1.5 mm cable.
The earlier 22-level trajectory also passed with closure included before sweeping.

**Eighteen focused tests passed in 17.63 s**, covering real closure, reconstruction
with saved terminals, independent checks, spatial recovery, UV updates, retries
and crossing diagnostics. No complete batch, new STLs, molds or assembly were
run at that stage.
