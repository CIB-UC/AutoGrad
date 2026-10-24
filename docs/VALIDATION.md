# Validation and limitations

This summary preserves the **October 21, 2026** engineering findings. Those
numerical values are historical. Publication preparation on **October 24, 2026**
reran automated tests, not complete electromagnetic/FastHenry campaigns.
Subsequent changes are documented in [CROSSING_VALIDATION.md](CROSSING_VALIDATION.md)
and [GEOMETRY_RECOVERY.md](GEOMETRY_RECOVERY.md), with their own configurations.

## Automated verification

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

The pre-localization publication baseline passed **475 tests**, with no skips,
in a clean Windows/Python 3.11.9 source copy. `pip check` found no incompatibilities.
Two warnings come from old fixtures referencing `scipy.io.matlab.mio5_params`.
The declared Python range does not imply every interpreter version was retested
in that review.

The AutoGrad rename then passed **41 existing GUI tests**, live English/Spanish
window checks, CLI help and the Windows launcher's setup-only check. Renaming
did not change calculation logic. The output-language revision adds tests for
English/Spanish organization, historical reuse, batch assembly, cancellation
and language capture at job launch. Its final clean-source run passed **491
tests**, with the same two deprecation warnings and no failures or skips,
in 103.05 s on Windows/Python 3.11.9.

Coverage includes the engine, B0 frames, parameters, units, metrics, terminals,
collisions, STL export/reload, batches, B0 marks, GUI and cancellation. Automated
checks do not substitute physical measurements or validate every configuration.

## Findings from October 21

- Cable validation measures nonlocal 3D segments using the actual round diameter.
  Manufacturing grooves do not define electrical area or replace round cable
  in that check. The final conductor is rechecked after both leads are created.
- Starting designs, including Gx at Tikhonov 2500 and 10000, contained real
  contacts. Finished field optimization alone does not establish manufacturability.
- `advanced.connection_cut_side=auto/low/high` reaches the engine; `auto` preserves
  historical behavior. Cut width, ramps and contour significance can change
  both geometry and field.
- Both shell halves were carved/exported/reloaded in m and mm. For generated
  cylinders the unique connected body spanning both axial ends is retained;
  ambiguous cases are rejected. User-supplied CAD halves are not filtered that way.
- Electrical conventions are `R = ρL/A`, ρ in Ω·m and `σ = 1/ρ` in S/m.
  `specific_conductivity` is a legacy name for **resistivity**. Real cable area
  and manufacturing groove clearance remain distinct.

## Simulated set that passed geometry checks

Three windings with terminals, three molds and two keys were obtained using the
production assembler. Earlier failed attempts were not counted as complete batches.
Shared settings were B0=+Y, height 170 mm, ROI radii 20 mm, complete inner anchor
26.5 mm, cable 2 mm and nominal complete-gradient gap 0.3 mm.

| Axis | Tikhonov | Levels | Minimum significance | Cut | Ramp | Cut plane | Additional groove clearance per side |
| --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| X | 2500 | 12 | 5 % | 3 mm | [1,1,3] | nearest | 0 mm |
| Y | 2500 | 6 | 15 % | 3 mm | [1,1,3] | B0 | 0.1 mm |
| Z | 2500 | 6 | 5 % | 1 mm | [7,7,7] | nearest | 0.1 mm |

Key stations were 202.5° and 180°, with 0.3 mm side/axial clearance. All 18
assembler checks found no conductor/ROI/mold intersections. The three final
STLs were reloaded and checked for closure, orientation and one positive-volume
body. The GLB scene retained its three geometries and dimensions.

| Axis | Final length | Simulated slope mT/(m·A) | Maximum ROI error relative to target amplitude | Analytical R | FastHenry R |
| --- | ---: | ---: | ---: | ---: | ---: |
| X | 6.883981758 m | 4.518582 | 3.211 % | 0.03681282276 Ω | 0.0368128 Ω |
| Y | 3.174224907 m | 1.289057 | 1.554 % | 0.01697450443 Ω | 0.0169745 Ω |
| Z | 2.017418089 m | 1.250204 | **16.057 %** | 0.01078835726 Ω | 0.0107884 Ω |

Real FastHenry ran at 1 Hz using full trajectories and equal-area square sections.
Agreement with `ρL/A` supports that electrical extraction, not absence of physical
interference or high-frequency equivalence of round/square sections. External
return wiring and mutual inductance are excluded.

## Scope and retained evidence

Geometric validity **does not certify field linearity**: Gz retains a 16.057 %
maximum simulated ROI error. No physical field, R/L or manufactured fit was
measured. Bend radius was not certified for the entire winding; terminal planning
kept its 6 mm constraint in the documented case.

Historical campaign files remain locally under `experiments/comparacion_pycoilgen/`,
including its report, `results.json`, presets and `validation/assembly_final/`.
Experimental scripts/checkpoints/results are excluded from the clean distribution.
This summary cannot reproduce that campaign exactly without those artifacts.
For a new study, preserve its configuration and full output directory and compare
final, rather than pre-lead, metrics.
