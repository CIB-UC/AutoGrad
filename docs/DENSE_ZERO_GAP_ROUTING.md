# Twenty-level Gx with zero layer gap

The October 30, 2026 correction addresses a reproduced Gx case without reducing
levels, enlarging the cylinder, adding a layer gap or relaxing physical checks.
It follows the earlier [cylinder projection correction](REGRESSION_2026-10-29.md).

## Reproduced settings

| Parameter | Value |
| --- | --- |
| Gradient / B0 | Gx / +Y |
| Cylinder outer radius / height | 50 / 120 mm |
| Winding mesh height | 114 mm |
| ROI radii | 30 mm |
| Cylinder mesh | 40 x 40 |
| Tikhonov / levels | 2500 / 20 |
| Round cable diameter | 2 mm |
| Groove radial / transverse profile | 4 / 2 mm |
| Layer gap / normal shift | 0 / -4 mm |
| Connection cut / smoothing | 1 mm / [7,7,7] |
| Crossing reassignment | Enabled |
| Cross-section samples | 16 |

These are the user's successful 10-level settings with only levels changed to
20 and the layer gap changed to zero. The older 20-level reproduction used
reassignment disabled and 12 cross-section samples; its inclined terminal cut
is also covered by a portable regression fixture.

## Three causes

### Spatial recovery was skipped for noncoincident ramp contacts

The initial path contained 1018 contacting segment pairs and minimum separation
0.2583569 mm. Fixed-radius turn separation could not solve them. Spatial
recovery previously ran only for contacts closer than one tenth of the cable
diameter: 0.2 mm in this case. This slightly larger contact therefore exhausted
five route alternatives without trying the recovery that actually resolves it.

An unsuccessful supported fixed-radius repair now also reaches spatial
recovery. The existing spatial bounds, iteration/time limits and exact global
distance check are retained. The accepted report keeps the unsuccessful
cylindrical stage as diagnostic evidence. Stream-function optimization and
alternative interconnections are not repeated when this repair succeeds.

### A constant-radius terminal could not preserve an inclined cut

Faceted cylinders and repaired crossings can leave the plane of a valid cut
slightly inclined to the ideal cylindrical tangent. Projecting that direction
onto a constant-radius surface produced either a tangent error or a mismatch
with the original section. The old search rejected all of its bounded choices.

Already valid constant-radius leads retain their exact original trajectories.
For an otherwise rejected inclined cut, the lead now follows its actual tangent
and smoothly brakes its radial velocity to zero over a short transition. The
radius stays monotone between its original value and its final value; both must
remain within the existing winding envelope. The section frame stays orthonormal
to the tangent, preserving the polygon rather than flattening or resizing it.

The reported case needs about 0.03751 mm radial adjustment at one terminal.
The other terminal retains the previous constant-radius route. Minimum bend
radius remains 6 mm, required surface clearance remains 0.3 mm and the exact
intersection checks are retained. The existing search selects a 48 mm cut,
15 mm tip separation and 24 mm exit margin; its limits were not expanded.

### An overlapping groove surface was unsuitable Boolean input

The deformed manufacturing groove can overlap itself even when the real round
cable has sufficient clearance. Treating its indexed sweep surface as a solid
left internal sheets and nonmanifold edges in the carved mold. Cleaning STL
triangles or simplifying the result alone did not resolve the reproduced case.

Terminal export now preserves the ordered groove sections and their original
side-triangle diagonals in its numeric current-path sidecar. They are tied to
the selected conductor STL by its hash. For an unexpanded, non-voxel groove,
the shell generator unions the exact capped sweep segments before subtraction.
Each segment preserves the original side triangles. This removes internal
overlap surfaces without voxel reconstruction, profile expansion or geometry
changes outside the defined swept volume. Older outputs without these arrays
retain the previous loading path; a stale reference is rejected.

At STL precision, a narrow neck can disappear and release a loose channel
offcut. Generated cylinders therefore repeat their existing connected-carrier
selection after serialization: keep the unique positive body joining both rims,
and remove disconnected positive offcuts. Selection does not use a volume cutoff.
Negative cavity surfaces are preserved, and custom CAD inputs do not use this
generated-carrier policy. Strict export validation still runs before publishing.

Opposite coincident faces produced by quantization are canceled as pairs.
Retaining one arbitrary face from an opposite pair would leave an open sheet;
equal-orientation duplicate boundaries still retain one face. Serialized
components are split without hole repair, so carrier selection cannot conceal
an opening. Positive offcuts are removed while negative cavity surfaces remain.

## Verification

The complete pipeline, including a real FastHenry solve and mold export, was
run with the settings above. All stages completed in 141.59 s, with pyCoilGen
reporting 85.03 s and no alternative winding-route retries. These timings are
individual observed runs, not controlled performance benchmarks. The initial
failing winding alone took 230.80 s while exhausting the five route alternatives.

| Final measurement | 16 samples, reassignment on | Original 12 samples, reassignment off |
| --- | ---: | ---: |
| Levels / layer gap | 20 / 0 mm | 20 / 0 mm |
| Coil minimum separation | 2.0202318 mm | 2.0202318 mm |
| Final conductor contacting pairs | 0 | 0 |
| Minimum terminal bend radius | 8.99703 mm | 8.99717 mm |
| Final conductor length | 9.971096 m | 9.972181 m |
| Simulated gradient | 4.192638 mT/(m A) | 4.192351 mT/(m A) |
| FastHenry R | 0.0533209 ohm | 0.0533267 ohm |
| FastHenry L | 32.38580 microhenry | 32.38564 microhenry |
| Positive mold bodies | 1 | 1 |
| Mold bounding box | 100 x 100 x 120 mm | 100 x 100 x 120 mm |

The 12-sample verification reused its previously generated, hash-validated
coil, then regenerated terminals, fields, FastHenry and mold with the corrected
implementation. Both conductor and mold STLs were reloaded: watertight,
consistently oriented, finite positive-volume solids, without zero-area faces.
The 12-sample mold retains its negative cavity surface instead of filling it;
both molds have one positive carrier body. Exact nonlocal 2 mm centerline checks
pass after terminals, and independent solid checks show no terminal/retained-coil
intersection beyond numerical roundoff. The final serialized 16-sample mold was
regenerated after the coincident-face correction and its SHA-256 is unchanged.

Automated regressions include the actual inclined cut and the actual initial
1018-contact path. They check an exact shared ring, corner-to-corner distances,
area, tangent, radial bounds, independent curvature, physical clearance, rigid
frame transforms and unchanged previously valid terminals. Groove tests check
overlap union, original nonplanar side diagonals, metre/mm units, reference
integrity, connected carriers and preservation of negative cavities.

The final clean-source verification passed **515 tests in 151.37 s**, with two
existing SciPy-fixture deprecation warnings. `pip check`, Pipeline CLI help and
staged whitespace checks passed. The active local application files match the
files used for this clean verification.

Local reproduction and verification evidence is retained under
`scratchpad/dense_leads_20261030/`, outside the published source tree. The user's
original `test` run is preserved.
