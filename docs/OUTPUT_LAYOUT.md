# Output language and compatibility

AutoGrad snapshots the GUI language when a job starts. Changing the language
while it runs affects the interface, not that job's saved directory layout.
English is the default for command-line and Python use; `Config.output_language`
can explicitly select `en` or `es`.

| Artifact | English | Spanish |
| --- | --- | --- |
| Default results root | `results/` | `resultados/` |
| Original winding | `Coil/` | `Bobina/` |
| Manufacturing molds | `Mold/` | `Molde/` |
| Final conductor and terminals | `Leads/` | `Leads/` |
| Field plots | `Plots/` | `Graficos/` |
| Solver and geometry diagnostics | `Diagnostics/` | `Diagnostico/` |
| Validated batch assembly | `Assembly/` | `Conjunto/` |
| Individual summary | `Summary.txt` | `Resumen.txt` |
| Batch summary | `Batch_summary.txt` | `Resumen_lote.txt` |
| Batch manifest | `batch.json` | `lote.json` |
| Assembly scene | `Gradients.glb` | `Gradientes.glb` |
| Assembly key report | `keys.json` | `encajes.json` |
| Sweep axis directory | `Axis_GX/` | `Eje_GX/` |

Each organized run stores its chosen language in `.output_layout.json`. When
reopening older runs, readers recognize both naming schemes and the historical
flat layout. Existing Spanish folders are preserved. Sidecar hashes, geometry,
units and numerical data do not depend on the output language.

A user-selected output location keeps its chosen name. Default paths use the
run language. Output language is presentation state, so it is excluded from
portable design presets and does not invalidate winding provenance.

If a new Pipeline design uses a directory holding results in the other language,
it receives a new localized results subdirectory rather than renaming or mixing
the earlier run. Reuse-only stages retain the original layout.

For a batch, all selected axes and its final assembly inherit the same language,
including parallel workers. Cancellation updates the matching manifest and
summary. Sweep job markers use the same localized axis directory as the worker.
English sweep CSVs use English column headers and phase names. Historical and
Spanish CSV headers remain readable for compatibility.
