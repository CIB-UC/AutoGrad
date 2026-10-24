# Contributing to AutoGrad

Start with the [README](README.md) for Windows setup and application commands,
and the [technical index](docs/README.md) for coordinates, geometry and validation.
Use the included engine rather than a separately installed `pycoilgen`.

## Development checks

Work on a feature branch and run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe halbach_coils\run_pipeline.py --help
```

For changes to geometry, field operators, units or process management, add a
regression that exercises the behaviour and run the full suite. Test fixtures
should be small and portable. FastHenry tests use controlled substitutes where
appropriate; a passing suite alone does not establish that a real solver is
installed or that a physical coil has been validated.

For GUI changes, also exercise the affected control in the application. For
manufacturing changes, retain the complete run outside Git, reload the exported
STL and check units, closure, orientation, dimensions and interference with the
real conductor. Report simulated and measured results separately and record the
configuration used.

## Code conventions

- `halbach_coils/coilgen/config.py` is the source of physical/manufacturing defaults.
  Lengths are metres internally. Convert GUI millimetres at the interface boundary.
- Preserve physical XYZ and the signed field component described in
  [B0_FRAME.md](docs/B0_FRAME.md). B₀ selection does not rotate the design geometry.
- Keep real cable area, groove dimensions, resistivity and conductivity distinct.
  The legacy `specific_conductivity` setting denotes resistivity in Ω·m.
- Register every argument passed to `pyCoilGen(log, arg_dict)` in
  `pyCoilGen/sub_functions/parse_input.py` or the relevant plugin. Use
  `smooth_factor`; `smooth_flag` is not a supported engine argument.
- A `target_field_definition_file` overrides `field_shape_function` in the engine.
- Write GUI source text in English and add Spanish text to `TRANSLATIONS` in
  `halbach_coils/gui/i18n.py`. Use `root.tr(...)` for dynamically created text.
- Declare dependency versions in `pyproject.toml`; `requirements-project.txt`
  delegates to the local project rather than duplicating the pins.

## What belongs in Git

Include application and engine source, documentation, licences, tests, required
fixtures and reusable input shells. Shell pairs use `g_Na.stl` / `g_Nb.stl` under
`halbach_coils/assets/shells/`; keep each pair together.

Exclude environments, caches, generated runs, solver intermediates, archives,
private experimental checkpoints and retired local scripts. The `.gitignore`
exceptions preserve the required STL/NumPy inputs. Place custom run directories
outside the checkout when possible.

Before committing, inspect:

```powershell
git status --short
git diff --check
git diff --cached --stat
```

An ignore rule does not remove files already tracked by Git. The prepared
publication branch was built with a clean index, so it excludes local historical
material even when that material remains tracked on the original local branch.
See [PUBLICACION.md](docs/PUBLICACION.md) for the initial upload.

## Attribution

Keep the GPL licence and the upstream pyCoilGen authorship. Describe local engine
changes in the review together with regression coverage and numerical or
manufacturing limitations.
