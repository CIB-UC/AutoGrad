# AutoGrad

Design `Gx`, `Gy` and `Gz` gradient coils for a low-field MRI scanner based on a
Halbach magnet. AutoGrad combines a graphical application, the included
`pyCoilGen` engine, terminal routing, field evaluation and STL mould generation.
It can also assemble three concentric gradients with alignment keys and B₀ marks.

This checkout includes the application, its modified engine, reusable shell
inputs and regression tests. No separate clone or global installation of
`pycoilgen` is needed.

## Quick start on Windows

1. Install **64-bit CPython 3.11, 3.12, 3.13 or 3.14**, with Tkinter. The project
   explicitly excludes Python **3.14.1**; use another supported patch release.
2. Clone this repository, or download its ZIP and extract the complete folder:

   ```powershell
   git clone https://github.com/CIB-UC/Gradients-PyCoilGen.git AutoGrad
   cd AutoGrad
   ```

3. Double-click **`AutoGrad.bat`**. First launch creates `.venv`, installs
   the dependencies declared in `pyproject.toml`, checks them and opens the GUI.
   Internet access is required for setup unless the packages are cached.
4. Choose an **Output directory**, review the **Pipeline** parameters and select
   **Run pipeline**. Computation may take several minutes.

The GUI starts in English. Use **Settings > Language > Español** for Spanish;
this selection lasts for the current session. The launcher uses the project's
virtual environment and leaves global Python packages unchanged.

## Application modes

| Mode | Workflow |
| --- | --- |
| **Pipeline** | Optimise one gradient, route its terminal leads, evaluate the final conductor and carve the winding grooves into a mould. |
| **Batch design** | Run the selected concentric gradients in their nesting order, optionally in parallel, check their final geometry and export the assembled moulds. |
| **Tikhonov sweep** | Compare regularisation factors, validate winding clearance, optionally refine the range and restore a valid result in Pipeline. |

The GUI supports Cu, Al, Ag and custom resistivity, advanced mesh/ROI and winding
parameters, saved field plots and cancellation of the calculation process and
its children. Only one calculation runs at a time. Cancelled or failed runs keep
partial files and a status marker.

Batch designs can include any nonempty selection of Gx, Gy and Gz. Independent
gradient calculations and sweep samples can run in separate processes; Windows
FastHenry extraction remains serial. A known geometric failure produces a
`needs_revision` result with its files and diagnostics retained. Other selected
axes can finish, but the assembly requires valid results from every included axis.
Sweep recommendations use only geometrically valid rows with finite metrics.
See [geometry recovery and result states](docs/GEOMETRY_RECOVERY.md).

This is an engineering design tool. A completed numerical run does not certify
field linearity, winding feasibility or printed fit. Review final field and
geometry reports before manufacture. The [validation notes](docs/VALIDATION.md)
describe the tested cases and their limits, including collisions found with
starting parameters and the field error of a geometrically valid example.

## Installation and verification

Windows is the supported desktop workflow. The package declares
`>=3.11,!=3.14.1,<3.15`; the launcher tries 3.14, 3.13, 3.12 and 3.11 in that
order, then a compatible `python` on `PATH`. Other operating systems have not
been validated as complete application workflows.

For manual installation, run from the repository root:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-project.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

Replace `3.14` with your supported interpreter version. `requirements-project.txt`
installs this checkout in editable mode with test tools. Runtime versions are
pinned once in [pyproject.toml](pyproject.toml), including the `trimesh` extras
`networkx`, `rtree` and `scikit-image` used by the application. The test count can
change; the command's final result gives the current status.

If the environment is broken, close the GUI and processes using `.venv`, rename
that directory to `.venv.old`, then launch `AutoGrad.bat` to create a new
one. Remove the backup when no longer needed.

### FastHenry2 (optional)

FastHenry2 supplies additional resistance and inductance estimates. It is not
included. Without a working installation, those solver values remain unavailable
and geometry generation can still run. The resolver checks
`Config.fasthenry.bin_path`, `PATH`, then existing known Windows installation paths.

Final metrics distinguish analytical `R = ρL/A` from FastHenry R/L and record
solver status. The electrical model uses the real cable area; FastHenry uses an
equal-area square approximation. External supply/return wiring and mutual
inductance between gradients are outside this model. See
[outputs and FastHenry](docs/OUTPUTS_AND_FASTHENRY.md).

## Running from a terminal

Run from the repository root with the project interpreter:

```powershell
.\.venv\Scripts\python.exe halbach_coils\run_gui.py
.\.venv\Scripts\python.exe halbach_coils\run_pipeline.py --help
```

For example, generate a wire layout without terminal or mould stages:

```powershell
.\.venv\Scripts\python.exe halbach_coils\run_pipeline.py --axis y --b0=+y --radius 0.039 --height 0.170 --tikhonov 2500 --levels 12 --skip-leads --skip-shell --no-plots
```

CLI lengths are **metres**; GUI lengths are **millimetres**. Their defaults are
not identical: specify geometry explicitly when comparing runs. A negative B₀
direction uses the equals form, for example `--b0=-y`.

| CLI option | Meaning |
| --- | --- |
| `--axis x\|y\|z` | Physical gradient axis. |
| `--b0=+y` | Signed main-field direction; all six axis directions are supported. |
| `--output-dir PATH` | Output location; otherwise a new run directory is created under `halbach_coils/results/pipeline/`. |
| `--no-plots` | Disable interactive plots. |
| `--skip-gradient` | Reuse a compatible wire and its provenance sidecars. |
| `--skip-leads`, `--skip-shell` | Omit the corresponding stage. |
| `--no-b0-marker` | Disable the mould orientation marks enabled by the CLI. |

## Coordinates and units

The default bore axis is physical **+Z** and the default main-field direction is
**B₀ = +Y**. The optimised component is signed `B_parallel = B · B0_hat`:
`Gx = d(B_parallel)/dx`, `Gy = d(B_parallel)/dy` and `Gz = d(B_parallel)/dz`.
Changing B₀ does not rotate the cylinder or the ROI. Meshes, fields, STL exports
and previews use the same physical XYZ frame.

Earlier versions used a different axis mapping and optimised Bz. Compare older
designs using their saved configuration and component, not their Gx/Gy/Gz name
alone. See the [coordinate-frame contract](docs/B0_FRAME.md).

GUI dimensions and default STL exports use mm; internal geometry and CLI
lengths use m. STL has no unit metadata: declare units when importing custom
shells or reading exports. GLB assembly scenes use metres.

## Inputs and outputs

Reusable shell inputs live in `halbach_coils/assets/shells/`, as matching
`g_Na.stl` / `g_Nb.stl` halves. The GUI discovers pairs at startup and can also
generate a one-piece cylindrical former. The [application README](halbach_coils/README.md)
details shell selection, B₀ marks, advanced controls and the batch workflow.

Generated results normally live under `halbach_coils/results/` and are ignored
by Git. Use an output directory outside the source tree for long studies. Custom
output paths inside the repository must also be reviewed before committing.

New results use the GUI language selected when the job starts. The English layout
is shown below; Spanish sessions use localized folder and summary names. Existing
results keep their original names when reopened in either language. Command-line
and Python runs default to English. See [output language and compatibility](docs/OUTPUT_LAYOUT.md).

A completed individual Pipeline run uses this layout:

```text
run/
├── Summary.txt       # Final field/electrical summary and FastHenry status
├── Mold/             # Manufacturing shell STL(s)
├── Leads/            # Final conductor, terminal paths, field data and metrics
├── Plots/            # Final PNG plots; CoilGen/ holds pre-lead plots
├── Coil/             # Original wire and configuration/reference sidecars
└── Diagnostics/      # Solver inputs, raw results and diagnostics
```

Keep the complete run folder to reproduce or reuse a design. Configuration and
sidecar hashes are checked; older wires without provenance must be regenerated.
`Coil/*_metrics.txt` describes the wire **before leads**; read `Summary.txt` or
`Leads/*_final_metrics.json` for final values.

Batch runs add `Batch_summary.txt`, `batch.json` and numbered layer directories
in the selected order (initially Gz → Gx → Gy). Only a successful final geometry
check publishes `Assembly/`, containing assembly mould STLs, `Gradients.glb`
and `keys.json`. Use those STLs for assembly. See
[batch dimensions and keys](docs/BATCH_AND_ASSEMBLY.md).

Field viewers open after completed designs. Reopen data with **Results > Open
field plots...**; B₀ comes from the saved result. Sweeps save CSV/text summaries
and `Sweep_Config.json`; **Load previous CSV...** and **Use selected in Pipeline**
restore the study parameters with the chosen Tikhonov factor.

## Repository guide

```text
AutoGrad/
├── AutoGrad.bat       # Windows setup and GUI launcher
├── halbach_coils/           # Supported application
│   ├── coilgen/            # Configuration, pipeline, geometry and metrics
│   ├── gui/                # Tkinter GUI and English/Spanish translations
│   ├── assets/shells/      # Reusable input STL halves
│   ├── run_gui.py
│   └── run_pipeline.py
├── pyCoilGen/              # Included, locally modified optimisation engine
├── data/                   # Curated engine inputs and regression meshes
├── tests/                  # Application/engine tests and fixtures
├── docs/                   # Technical guides, validation and publication
├── requirements-project.txt
├── pyproject.toml          # Metadata and pinned dependencies
└── LICENSE.txt
```

Local environments, results, experimental scripts, archives, backups and retired
application code are excluded from the publication branch. Required STL/NumPy
inputs remain versioned through explicit `.gitignore` exceptions. See
[contributing](CONTRIBUTING.md) and the [publication guide](docs/PUBLICATION.md).

## Troubleshooting

- **Python is not found:** install a supported 64-bit interpreter and rerun the launcher.
- **Manual launch closes immediately:** use the terminal command above to retain the traceback.
- **A shell pair is missing:** check both filenames and restart the GUI.
- **FastHenry shows `n/a`:** inspect solver status and configure its executable if needed.
- **A design reports collisions or fails assembly:** inspect its report and revise the winding parameters; a completed wire optimisation alone does not establish manufacturability.

## Licence and upstream attribution

Distributed under the **GNU GPL v3 or later**; see [LICENSE.txt](LICENSE.txt).
The engine derives from [kev-m/pyCoilGen](https://github.com/kev-m/pyCoilGen) and
retains its upstream authorship. The [upstream documentation](https://pycoilgen.readthedocs.io/)
describes the general engine; this repository's guides cover the Halbach
application and local modifications. Preserve the licence and attribution when
redistributing either part.
