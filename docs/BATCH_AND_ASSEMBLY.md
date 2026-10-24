# Batch design and assembly keys

This document records batch geometry and historical verification runs. Their
parameters do not guarantee that the same designs pass later versions' checks.
See [VALIDATION.md](VALIDATION.md) and [GEOMETRY_RECOVERY.md](GEOMETRY_RECOVERY.md)
for subsequent contact detection and routing changes.

Batch design originally replaced Standalone and ran all three axes sequentially.
The current application supports any nonempty selection of axes and optional
parallel calculation. All selected designs share physical XYZ, longitudinal Z
and one B0 direction. Individual pipeline stages still evaluate fields, leads,
FastHenry and molds.

## Dimensions

Enter one anchor radius: either the innermost complete gradient's inner radius
or the outermost complete gradient's outer radius, including cable and grooves.
Switching modes initially preserves geometry; the anchor can then be edited.

Each axis has cable diameter, crossing-layer gap, Tikhonov factor and level count.
Shared A/B factors scale cable diameter into radial groove height and tangential
groove width. Mold wall thickness follows the individual Pipeline formula:

`wall = 2 × radial_groove_height + layer_gap − 2 × radial_trim`

`radial_trim = trim_fraction × radial_groove_height`

The inter-gradient gap is `outer_gradient_inner_radius − inner_gradient_outer_radius`
using complete envelopes, including exposed cable. Plastic radii are displayed
separately. Exposed cable contributes to gradient thickness rather than consuming
the requested gap. Zero gap is allowed as theoretical contact; negative values
are rejected. Final CAD checks still evaluate discretized conductors, leads and
keys in three dimensions.

Starting values: height 170 mm, innermost complete radius 26.5 mm, cable 2 mm,
A=2/B=1, zero crossing-layer gap and 0.3 mm inter-gradient gap. Complete inner/outer
radii are Gz 26.5/34.5, Gx 34.8/42.8 and Gy 43.1/51.1 mm. Plastic radii are
28.5/32.5, 36.8/40.8 and 45.1/49.1 mm. Initial Tikhonov 2500 and 12 levels per
axis are starting points, not optimization of the complete set or its coupling.

Reference STLs use longitudinal X and were interpreted as
`(new_X,new_Y,new_Z)=(STL_Y,STL_Z,STL_X)`, ordered Gz → Gx → Gy. Their measured
plastic radii are 26.5/29.5, 30.5/33.5 and 34.5/37.5 mm. These dimensions alone
do not specify cable outside the plastic. Reference files guide geometry;
new solids are generated from current calculation results.

## Keys

Each adjacent pair has an inner-mold tab and outer-mold slot, open from −Z.
Starting tab width and length are 4 mm. Current default slot clearance is
0.3 mm per tangential side and at the axial stop: a 4 mm tab therefore gets
a 4.6 mm slot width and 4.3 mm useful length. The clearance control affects
preview and exported STL equally. Check a small printed sample with the intended
printer and material before printing the full set.

The tab end follows the receiver's outer radius. Preferred stations are
202.5° and 180°, measured from +X towards +Y. Occupied positions trigger a search
for another station without rotating gradients. No antenna recess is generated.
The stop limits +Z travel; keys prevent relative rotation; withdrawal towards
−Z remains possible. No snap latch or two-direction axial retention is added.

Before publishing assembly outputs, checks cover conductor/conductor,
conductor/other-mold, mold/mold and the shared ROI. Serialized STLs are reloaded
and checked for closure, orientation, one connected body and interference.
CAD stays in double precision until export. The key report records intersection
tolerance. CAD uses a conservative circumscribed ROI ellipsoid; electromagnetic
evaluation keeps the original ROI.

## Outputs and cancellation

English runs write `Batch_summary.txt` and `batch.json`. Numbered layer folders
keep the individual Pipeline layout. Gradient buttons open final field plots
and show FastHenry values. `Assembly/` contains manufacturing STLs,
`Gradients.glb` and `keys.json`: STL uses mm, GLB uses m, in physical coordinates.
Spanish names remain supported as described in [OUTPUT_LAYOUT.md](OUTPUT_LAYOUT.md).

Assembly outputs appear only after all checks pass. Failure, discard or Stop
retains individual designs and marks the batch incomplete. Stop terminates the
worker and descendants and updates the job marker, manifest and summary.

## Initial implementation verification

All three starting designs completed with their final terminal leads. Installed
FastHenry returned:

| Gradient | R [Ω] | L [µH] |
| --- | ---: | ---: |
| Gz | 0.0190474 | 5.68220 |
| Gx | 0.0362015 | 14.73924 |
| Gy | 0.0379879 | 18.24711 |

These are separate circuits, excluding external supply/return wiring and mutual
inductance. The exported set passed 18 intersection checks. Reloaded STLs were
closed, consistently oriented, single-body solids. Final key positions were
202.5° and 180°, with the **0.1 mm clearance used in that historical run**.

That run exposed Gx/Gy STL precision issues. Export retains double precision
during booleans and locally repairs edges that collapse at serialization,
exactly zero-volume CAD sheets and collinear faces. Reload validation remains
mandatory; voxelization is not used for these cases. Real batch cancellation
took 0.041 s and left cancelled manifest/summary states.

The suite passed **336 tests**. A new GUI execution through `WorkerRunner` and
a real Windows process completed all gradients in 490.4 s with the same R/L.
All three plot buttons, final job status and final STLs were checked. Historical
local evidence is under `halbach_coils/resultados/verificacion_lote_final_20261015/`,
including `verificacion.json`, `Vista_conjunto.png` and the assembly CAD report.

Moving in-memory copies of the final parts confirmed interference for ±1°
rotation and 1 mm travel towards +Z. The original position and 1 mm withdrawal
towards −Z stayed clear, verifying rotation restraint and the axial stop.

## Correcting the gap definition

The first implementation measured the gap between plastic walls. A saved
`Desktop/test` case with 50 mm anchor, 2 mm cable and 2 mm gap had groove-envelope
overlaps of 254.246 mm³ for Gz/Gx and 235.759 mm³ for Gx/Gy. Those STLs represent
grooves, not round 2 mm cable, although even nominal cable paths were nearly
touching. The GUI's claimed inter-gradient spacing was therefore inconsistent.

Since manifest format 2, anchor and gap describe complete gradients. The same
50 mm anchor and 2 mm gap produce complete radii 50/58, 60/68 and 70/78 mm,
with plastic radii 52/56, 62/66 and 72/76 mm. Older results, individual Pipeline
formulas and CAD checks are preserved. New spacing requires recalculation
because the electromagnetic design radii change.

Cable/cable checks now use hash-verified final trajectories, real round diameter
and exact segment distances. Groove STLs remain appropriate for mold/key checks.
A subtraction-tool overlap outside the plastic is not automatically a cable
collision.

A GUI rerun with 50 mm anchor, 2 mm gap, 30 mm ROI, Tikhonov 2500 and 12 levels
per axis completed in 297.4 s. All molds were closed, keys valid and FastHenry
successful. Evidence is under
`halbach_coils/resultados/verificacion_lote_gap_20261015/`. The suite passed
**343 tests**, and all 18 exported-set checks were repeated using round cable.

## Assembly export corrections

A batch with complete inner radius 30 mm, gap 2 mm, cable 2 mm and ROI 20 mm
completed individual designs but failed exporting keys. CAD conversion now
accepts read-only `to_mesh64()` vertex buffers by creating writable memory when
needed.

Faces that become collinear only at float32 STL precision are repaired by
splitting a neighboring face at the existing vertex before removing the
degenerate face. Rounded coordinates are preserved without opening a crack.
Closure, orientation, degeneracy and interference checks remain mandatory.

Only assembly was regenerated from that batch's real outputs: coils and
FastHenry were not recalculated. All 81 individual files kept their SHA-256,
and the assembly passed 18 checks. The suite passed **348 tests**, including
read-only-buffer and collinear-face regressions.
