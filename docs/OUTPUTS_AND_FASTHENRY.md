# Outputs and FastHenry — October 14, 2026

The desktop test named `test` had completed FastHenry successfully:
`Zc2a01df25192e.mat` stores the 1 Hz impedance, and the final JSON records
R = 0.0362738 Ω and L = 14.7778548 µH. The visible metrics TXT described the
winding before leads and showed `n/a`, making the final result hard to find.

Extraction was repeated using the installed COM server and the same 3963-point
trajectory (2683 solver points), producing the same values. This used real
FastHenry, not a simulated solver. Subsequent cancellation work is described in
[GZ_ROUTING_AND_CANCELLATION.md](GZ_ROUTING_AND_CANCELLATION.md).

## Organization

The current English layout provides `Summary.txt` and these directories:

- `Mold/`: mold STL files.
- `Leads/`: final conductor, separate terminals, numerical trajectory, final
  field, metrics and geometry report.
- `Plots/`: final-conductor PNGs; `CoilGen/` retains the pre-lead plots.
- `Coil/`: original wire STL, verified configuration, section references,
  field data and preliminary metrics.
- `Diagnostics/`: target inputs and FastHenry evidence.

New GUI runs use the selected interface language. The names in historical
Spanish runs remain supported; switching the interface language does not rename
an existing result. See [OUTPUT_LAYOUT.md](OUTPUT_LAYOUT.md).

Hash-linked files stay together and their binary contents are not rewritten.
JSON/viewer path references are updated when organizing files. Older flat results
also remain readable. New iteration names reserve already organized results to
avoid overwriting them. Unrelated user files are left untouched.

The completion dialog and final-field viewer show R in Ω and L in µH. Failure
or unavailability includes status and reason. The preliminary `Coil/` metrics
TXT explicitly points to the final summary. Inductance excludes external supply
and return wiring.

## Additional verification

A full pipeline used the GUI starting values: Gx, B0=+Y, radius 39 mm, height
170 mm, ROI 20 mm, Tikhonov 2500 and 12 levels. Real FastHenry returned
R = 0.0362719 Ω and L = 14.7768680 µH. The mold was watertight and organized
outputs retained valid design provenance. The desktop test had used B0=-Y,
so the small difference reflects distinct designs.

Axis and B0 arrows now adjust their lengths to the visible range during zoom.
Arrowheads keep their screen size, and labels follow the resized arrows. This
also applies to B0 in spatial field plots.
