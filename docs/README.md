# AutoGrad technical documentation

Use the [main README](../README.md) for installation and current commands.
The [application README](../halbach_coils/README.md) covers GUI controls, B0 marks
and shell inputs.

| Document | Contents |
| --- | --- |
| [B0_FRAME.md](B0_FRAME.md) | Physical XYZ, signed components, polarity and older designs. |
| [OUTPUT_LAYOUT.md](OUTPUT_LAYOUT.md) | GUI-dependent output names, saved language and historical compatibility. |
| [VALIDATION.md](VALIDATION.md) | Automated verification, engineering findings and limitations. |
| [CROSSING_VALIDATION.md](CROSSING_VALIDATION.md) | Crossing-ramp correction and the original Gx/Gy batch reproduction. |
| [GEOMETRY_RECOVERY.md](GEOMETRY_RECOVERY.md) | Turn spacing, route recovery, clearance-aware sweeps and partial results. |
| [BATCH_AND_ASSEMBLY.md](BATCH_AND_ASSEMBLY.md) | Complete/plastic radii, gaps, keys and historical CAD checks. |
| [OUTPUTS_AND_FASTHENRY.md](OUTPUTS_AND_FASTHENRY.md) | Output organization and pre-lead versus final electrical metrics. |
| [GZ_ROUTING_AND_CANCELLATION.md](GZ_ROUTING_AND_CANCELLATION.md) | Historical Gz routing and owned FastHenry process cleanup. |
| [PUBLICATION.md](PUBLICATION.md) | Prepared branch, review checks and maintainer-approved upload. |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Conventions, versioned inputs and checks for future changes. |
| [Engine data](../data/README.md) | Reusable datasets and binary fixtures. |

Dated reports describe particular versions, configurations and runs. Their test
counts and electrical values are historical evidence, not predictions for all
designs. Distinguish physical measurements from simulation and CAD checks.

Large results, experimental scripts and machine-recovery notes remain local and
are excluded from publication. Documentation is in English; Spanish strings in
runtime localization and legacy artifact names are retained intentionally.
