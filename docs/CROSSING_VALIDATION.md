# Gx/Gy crossing investigation and correction — October 24, 2026

The original batch completed Gz but failed in Gx at four same-conductor
interference regions. Centerline distances were 1.51227, 0.0167387, 0.0154803
and 0.000282678 mm for 2 mm round cable.

## What changed

The local `overlap.py` and `final_field.py` changes added 3D segment-distance
checks and mandatory final-conductor rejection. `shift_return_paths.py` still
used historical crossing selection; its previous change only added diagnostics.
The new validation therefore stopped contacts that could previously continue.

Initially, the warning let a user accept the result, but final validation
rejected the same contacts after terminal creation. All four contacts already
existed in the original winding; the terminals did not create them.

## Cause and correction

The engine selected the branch to move independently at each crossing. Smoothing
with a convolution let one ramp reach neighboring crossings and move a branch
that should have stayed outside. At the worst contact both branches had almost
the same radius, 63.293 mm.

When the original selection leaves insufficient nominal separation, interacting
smoothing regions are grouped and assigned jointly to the two radial layers.
Each crossing requires opposite layers. The orientation closest to the original
selection is chosen while preserving requested shift and smoothing. Already
separated routes keep their original selection.

If constraints cannot be satisfied with two layers, no third layer is invented
and the crossing is not declared solved. Physical distances remain checked
after sweeping and after terminals. In the implementation tested here, a measured
remaining contact stopped the pipeline before leads rather than offering a
continuation that would later fail. Subsequent partial-result behavior is
documented in [GEOMETRY_RECOVERY.md](GEOMETRY_RECOVERY.md).

## Reproduction with the original parameters

The full batch used B0=+Y, ROI radii 50 mm, height 170 mm, a 200 × 10 mesh,
2 mm cable, groove A=2/B=1, zero crossing gap, 1 mm connection cuts and smoothing
`[7,7,7]` on all axes. Inside-to-outside order was Z, X, Y; complete inner anchor
radius was 53 mm and complete-gradient gap was 0.3 mm.

| Axis | Mold outer radius | Tikhonov | Levels |
| --- | ---: | ---: | ---: |
| Z | 59.0 mm | 20000 | 3 |
| X | 67.3 mm | 20000 | 12 |
| Y | 75.6 mm | 10000 | 12 |

The batch completed terminals, molds, B0 marks and keys. Assembly checked all
conductors, molds and ROI. Reloaded Gx/Gy mold and conductor STLs were closed,
consistently oriented, single-body solids with positive volume. Mold STL units
were mm; conductor STL units were m.

| Final result | Gx | Gy |
| --- | ---: | ---: |
| Minimum nonlocal segment distance | 3.81456 mm | 3.25712 mm |
| Conductor length | 8.32624 m | 8.43396 m |
| Simulated slope | 1.59502 mT/(m·A) | 1.15251 mT/(m·A) |
| Maximum ROI error relative to target amplitude | 8.64146 % | 6.35282 % |
| Analytical R | 0.0445254 Ω | 0.0451015 Ω |
| FastHenry R | 0.0445247 Ω | 0.0451008 Ω |
| FastHenry L | 18.0697 µH | 17.6880 µH |

Distances use exact segments and the same arc-neighborhood exclusion as final
conductor checks. Gz kept its parameters and results. Fields were recalculated
for the changed routing; earlier winding metrics were not reused.

A 3 mm cut / `[1,1,3]` smoothing alternative for Gx/Gy also completed with the
old selection. The engine correction allowed the investigated original settings
to remain unchanged.

## Tests and evidence

The historical suite passed **436 tests**, with two SciPy-fixture deprecation
warnings and no skips. `pip check` and Pipeline CLI help passed.

`tests/test_shift_return_paths.py` covers interacting ramps, unsatisfiable
two-layer constraints, unchanged separated routes and the exact failing Gx.
`tests/test_data/gx_crossing_ramps.npz` stores only mesh/path arrays, without
serialized Python objects or machine paths. `test_pipeline_collision_decision.py`
checks early measured-contact handling in English and Spanish.

The local run `Gx_Gy_reparado_20261024` retains summaries, manifest, per-axis
presets, assembly, before/after figure, `verificacion_exportados.json`, this
report and logs. Its historical filenames are retained in the evidence.
