# Reproducible return paths

The layer planner is separate from displacement, sweep pruning, physical
clearance recovery, interconnection retries, and terminal generation. None of
these operations is a substitute for the others.

`plan_return_path_layers` in `shift_return_paths.py` preserves the historical
selection, applies the original sample-based convolution, and conditionally
tries the joint two-layer assignment. It returns both decisions and a versioned
report (`joint_layers_exact_support_v2`). The reassignment checkbox permits this
conditional operation; it does not disable recovery or connection retries.

The verified GX reference (200×10 mesh, 20 levels, 1.5 mm wire, −3 mm shift,
[7,7,7], Tk=28480) changes from 6 interior intervals and one interior/interior
crossing to 13 interior intervals and 39 mixed crossings after joint assignment.
Its 6381-station winding is reproduced exactly, allowing for current direction.
The 22-level GX reference is also reproduced exactly, with 43 mixed crossings.
No recovery moves either GX. This does not guarantee the same result for other
geometry, sampling, or connection choices.

The GY20 reference is different: joint assignment returns no solution for its
sample grouping; spatial recovery produces the archived winding. An odd-cycle
witness identifies the incompatible groups and UV crossing indices. It proves
incompatibility of this grouping, not physical impossibility for all routes.

The current planner also tests an exact-support assignment if coarse grouping
fails. It places descent seeds subject to the actual convolution weights and
requires opposite saturated layers at crossing segments. This resolves false
grouping conflicts without changing geometry settings or retrying connections.
An independently checked closed cylindrical example changes from one crossed
return/four physical contact pairs to four mixed crossings/zero contacts.
Its minimum nonlocal clearance is 2.966419 mm for 1.5 mm wire.

After spatial recovery, AutoGrad checks the actual cylindrical projection of
the selected winding. Two descending/return branches may not cross each other,
including branches at different intermediate radii; a single transition under
the original layer is permitted and must still pass exact real-wire clearance.
Pipeline and batches stop before terminals/mold if the requested distribution
was not achieved, even if physical clearance alone passes. This criterion does
not add interconnection attempts or change terminal manufacturing checks.
GY20 still has three crossings between return branches after its historical
spatial repair, so it is now explicitly unresolved for this requested pattern.
The original files are preserved; their physical-clearance result is unchanged.

## Automatic evidence

AutoGrad enables `save_return_path_trace` in its shared gradient runner, used
by Pipeline and batches. `*_wire_N_return_paths.npz` and its JSON are placed in
Diagnostics/Diagnostico by output organization. The report also appears in
`*_geometry.json` and the run summary explains the selection outcome.

The archive contains the connected input and mesh/UV, prepared surface,
historical and joint selections, smoothing kernel, interpolated crossing
factors, effective normals, shifted path, pruned path, recovered path, and
current-oriented final path if reached. JSON includes effective arguments,
algorithm status, source hashes (including local edits), versions, and clearance
diagnostics. `stage` identifies the latest completed checkpoint.
Requested arguments and the selected part's effective arguments are stored
separately, including any retry's changed connection cut width/side.

Statuses distinguish `joint_applied`, `joint_exact_support_applied`, `joint_incompatible`,
`reassignment_disabled`, `historical_sufficient`, `historical_insufficient`,
`no_crossings`, and `normal_shift_skipped`. A failed joint assignment preserves
the historical choice and is visible; a successful layer plan still requires
the real 3D conductor check.

The initial archive is written before sweeping and updated for the selected
route after recovery and current orientation. Rejected connection alternatives
are not archived independently. The final archive identifies the selected
route's effective arguments. A run that stops early retains an earlier stage.

## Replay without an optimizer

From the repository root, using the project's Python:

```powershell
.venv\Scripts\python.exe -m pyCoilGen.sub_functions.return_path_trace `
  path/to/Gradient_Gx_wire_0_return_paths.npz `
  --stage recovered --output replayed_winding.npz
```

Replay validates the NPZ hash, recalculates the recorded planner decisions,
and recomputes displacement with the same arithmetic order. Version-one
archives select the preserved version-one planner. Changed decisions
or geometry are rejected. Existing output files are never overwritten.

`shifted` recalculates displacement. `pruned`, `recovered`, and `final` return
the recorded later geometry after verifying the displacement. Recovery is not
rerun under wall-clock limits. The output contains a diagnostic `path` in physical
XYZ metres; it is not a signed replacement for a manufacturing design sidecar.

The plan belongs to that specific input mesh, station order, and parameters.
The smoothing factors remain **samples**, not millimetres. Altering sampling
changes physical ramp lengths and requires a new plan. The archive supports
exact replay and regression detection; it does not certify continuous curvature,
winding order, tool access, or universal two-layer routability.

The focused investigation and full measurements are available locally in
`experiments/return_paths_20261102/INFORME.md`. The fixtures used by
`tests/test_return_path_reference.py` are numeric, require no pickle or solver,
and preserve the GX20 layer choice and GY20 incompatibility.

Terminal generation is unchanged: normal mode keeps `strict_manufacturing=False`
with exact separation of the real circular conductor. Manufacturing
recommendations remain warnings.
