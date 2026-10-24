# AutoGrad application

This directory contains the supported Halbach-specific application built on the
vendored `pyCoilGen` engine. Start with the repository-level [README](../README.md)
for requirements, first-time installation, coordinate conventions and the
complete workflow. This package uses the modified engine included in this
repository; do not replace it with a separately installed `pycoilgen`.

## Entry points

Run commands from the repository root with the project virtual environment:

```powershell
.\.venv\Scripts\python.exe halbach_coils\run_gui.py
.\.venv\Scripts\python.exe halbach_coils\run_pipeline.py --help
```

On Windows, `AutoGrad.bat` at the repository root is the recommended
launcher because it creates and verifies `.venv` before opening the GUI.

The GUI starts in English. **Settings > Language > Español** switches to Spanish
for the current session. The **B₀** menu selects the signed main-field direction;
**Results > Open field plots...** reopens saved `*_field_data.npz` results.

GUI lengths are in **mm**. CLI and `Config` lengths are in **m**. Defaults differ
between GUI and CLI, so pass geometry explicitly when comparing runs.

## Directory guide

| Path | Purpose |
| --- | --- |
| `coilgen/` | Supported pipeline, configuration, metrics, sweep, lead, and shell code |
| `gui/` | Tkinter panels and the English/Spanish translation catalogue |
| `assets/shells/` | Tracked matching STL halves discovered by the GUI |
| `run_pipeline.py` | Non-interactive pipeline entry point |
| `run_gui.py` | Graphical entry point |
| `resultados/` | Generated run directories; ignored by Git |

Retired scripts may remain in a local `obsolete/` folder. They are excluded from
the publication branch and are not required by the application or its tests.

## Modes and saved results

- **Pipeline** runs gradient generation, terminal routing and shell carving.
  Clear a stage checkbox only when deliberately reusing compatible intermediate
  files. A reused wire requires its matching design JSON, field data and lead
  references; the application verifies their configuration and hashes.
- **Batch design** runs the selected gradients in a common physical frame. The initial
  nesting order is Gz → Gx → Gy. Choose the inner radius of the innermost
  complete gradient or the outer radius of the outermost one, a shared height
  and ROI, and the radial gap between complete gradients. These envelopes
  include exposed cable and grooves; plastic radii are displayed separately.
  Each Gx/Gy/Gz row has an inclusion checkbox. Uncheck a gradient to generate
  only the selected axes; at least one must remain selected. The preview,
  radii, radial gaps and assembly keys are recalculated for the selected set,
  retaining its inside-to-outside order. Excluded gradients produce no output.
  Enable **Generate gradients simultaneously (one process each)** to run each
  selected gradient in a separate process. Final assembly waits for all selected axes;
  the default runs the gradients sequentially. Windows FastHenry calculations
  run one at a time because the gradients share its COM server.
- **Tikhonov sweep** writes CSV/text results and `Sweep_Config.json`. Load a
  previous CSV, select a row and choose **Use selected in Pipeline** to restore
  the study configuration with that row's regularisation factor. Set
  **Simultaneous processes** to choose how many Tikhonov values run at once
  (default: 1, sequential). Each calculation uses its own output folder; the
  fine phase starts after all coarse calculations finish. The CLI accepts the
  same setting through `--processes`.

`Resumen.txt` and `Leads/*_final_metrics.json` describe the final conductor,
including both terminal leads. `Bobina/*_metrics.txt` describes the original
wire before leads. For batch manufacture use the final STLs in `Conjunto/`;
the numbered layer folders retain individual pipeline outputs. Preserve the
entire run folder, including sidecars, when sharing a result outside Git.

Every field plot displays the generated gradient efficiency in mT/m/A.
**Generated field contours** shows signed B-parallel isolines at 1 A in the
physical XY, XZ and YZ sections, with a shared mT/A color scale. These maps
interpolate inside the sampled ROI without extrapolation. They are included
in the field viewer and exported automatically as `*_field_contours.png`;
saved field NPZ files can also show this view without rerunning the design.

The three modes share one active job. **Stop** terminates the worker and its
children; closing the GUI cancels the active job. Partial files are retained,
and failed, discarded or cancelled batches are marked incomplete.

## Parameters and electrical conventions

The material selector fills room-temperature resistivity for Cu, Al or Ag;
choose **Custom** for another material or temperature-adjusted value. Use
`ρ` in **Ω·m**, `σ = 1/ρ` in **S/m** and the actual cable area for `R = ρL/A`.
The legacy setting named `specific_conductivity` stores **resistivity**; see
the explicit properties in `coilgen/config.py` before using it directly.

The cable diameter and groove geometry are independent. Groove height, width
and clearance change the manufacturing subtraction solid, not the electrical
area. FastHenry uses an equal-area square approximation of the round cable.
Solver status and analytical resistance are recorded separately.

**Advanced CoilGen parameters > Show more parameters** exposes mesh/ROI sampling,
contours, interconnections, integration and optimisation controls. Hover over a
label or value for help in the selected language. Expanding Pipeline controls
shows a reduced preview; the summary reports full sample counts. Hiding controls
preserves values; **Restore defaults** resets only these advanced settings.
Geometry or winding changes require a new run. Mouse-wheel zoom works in 3D views.

Starting parameters are examples, not validated manufacturing presets. The
current detector checks real cable distances in 3D and can reject geometries
that older versions accepted. Read [validation and limitations](../docs/VALIDACION.md)
before interpreting a completed optimisation as a usable assembly.

## Shell asset convention

Each printable shell layer is a matching pair named `g_Na.stl` and `g_Nb.stl`,
where `N` is the layer number. Both files must exist in `assets/shells/` before
the pair appears in the GUI. Restart the GUI after adding a pair.

Keep only reusable input halves in this directory. `.gitignore` explicitly
allows these STL inputs while excluding generated meshes elsewhere. A duplicate
`assets/shells.zip` is not needed. Generated runs belong under `resultados/` or
an output directory outside the checkout.

STL has no unit metadata. Set the input-unit option correctly for custom halves;
default exports are in mm. For a one-piece generated cylinder, no input STL is
required. A batch's keys have a default 0.3 mm clearance per side and at the
axial stop; see [batch dimensions and assembly](../docs/LOTE_Y_ENCAJES.md).

## B0 orientation marks

The Pipeline panel offers **Add B₀ orientation marks to the shell**, enabled
initially. The pipeline CLI also enables it; use `--no-b0-marker` to disable it.
Python callers can opt in with `cfg.shell.b0_marker = True`.

A shallow rectangular recess is carved in both annular end faces, along the
physical B0 axis regardless of its sign or the gradient axis. The positive
side is preferred; if occupied, both marks use the opposite side of that same
axis. Its dimensions follow the finished shell wall thickness, radius and height; there
are no size controls. For a rotated cylinder the end-face direction follows
the projection of B0. When B0 is parallel to the cylinder, the recess instead
runs longitudinally on the outer wall near each end. Marks are applied after
all shell trims and included in the validated output STL. If a footprint
overlaps a groove, lead exit or missing rim material on both sides, generation
reports an error before exporting shells; it never moves the mark away from B0.

Batch Design has a single **Add aligned B₀ marks to all three gradients** checkbox,
enabled initially (`BatchConfig.include_b0_markers` for Python callers). Batch
marks are added together to the three final STL files in `Conjunto/`, after the
individual pipelines finish. All marks use the same side and angular position
of the shared physical B0 axis. If that side is occupied on any layer, the
opposite side is tried for all three; if neither side fits all layers, the
assembly reports an error. Individual pipeline files remain unchanged.

Key placement reserves the marks' angular region with automatic clearance,
so neither a male key nor a receiving slot can occupy it. This also works with
keys disabled and with axial B0. The final shared position is saved in
`Conjunto/encajes.json` and shown in the batch preview.

## Where to make changes

- Change physical and manufacturing defaults in `coilgen/config.py`; it is the
  configuration source of truth.
- Add GUI source text in English and its Spanish translation in `gui/i18n.py`.
- Preserve the common physical XYZ frame and signed field projection described
  in the [frame contract](../docs/B0_FRAME.md).
- Keep numerical studies and retired scripts outside the published source.

Before submitting changes, run:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for engine integration constraints and
the [documentation index](../docs/README.md) for technical reports.
