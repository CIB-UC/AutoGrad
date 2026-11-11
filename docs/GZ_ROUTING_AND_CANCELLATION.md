# Gz routing and FastHenry cancellation — October 14, 2026

The advanced parameters were approved as configured. This report closes that
review and records the investigation of the two remaining technical issues.
It describes historical runs, rather than guaranteeing every later design.

## Gz terminal routing

The saved case failed because its terminal region pointed towards Y. For B0=Y,
the Gz winding has a usable corridor near X. Only the cut/exit reference changed:
the winding was not rotated, the target field was unchanged, and curvature and
clearance limits were preserved.

Two designs used B0=+Y, a 39 mm outer radius and a 200 × 10 mesh:

| Case | Height / ROI / levels | FastHenry R | FastHenry L | Final slope |
| --- | --- | --- | --- | --- |
| Previously failing saved case | 200 mm / 15 mm / 8 | 0.0173712 Ω | 4.023946 µH | 1.336469 mT/(m·A) |
| GUI starting values with Gz selected | 170 mm / 20 mm / 12 | 0.0252737 Ω | 7.844540 µH | 2.080715 mT/(m·A) |

Both completed terminal routing, final-field evaluation, real FastHenry and mold
generation. Minimum terminal bend radii were respectively 7.144 and 6.861 mm,
above the 6 mm limit. Required clearance remained 0.3 mm. Lead/winding boolean
intersection volumes were zero. Retained winding sections and vertices were
preserved.

Reloading the second exported mold revealed four zero-area faces: very small
edges had collapsed at STL float32 precision. Export now removes degenerate and
duplicate faces and validates the reloaded file before publishing it. Both final
STLs were watertight and consistently oriented. A failed reload is reported as
an error, rather than published as a valid result.

These results apply to the two geometries above. Other B0 directions and
dimensions still undergo the generator's checks.

## FastHenry COM lifecycle

The application starts the registered executable with `/Embedding` and waits
for automation readiness. Its owned process joins a Windows job with
`KILL_ON_JOB_CLOSE`. GUI workers use the same containment mechanism; cleanup
does not rely on COM answering `Quit`.

Checks with an installed FastHenry server covered:

- Normal extraction: unchanged R/L and no residual server.
- A deliberately frozen server, created by suspending its threads: timeout
  terminated client and server, leaving empty R/L and an explicit failure state.
- Cancellation from the GUI worker under that freeze: termination took 0.047 s
  and 0.062 s in the two checks; the server closed and the job became cancelled.
- A pre-existing test instance: it remained open. The new extraction reported
  unavailable and neither reused nor closed that instance.

Those measured times are observations, not universal latency bounds. Inductance
still covers only the modeled conductor, excluding external supply/return wiring.
The main checkout's full suite passed **273 tests**, in addition to these real
solver checks and the two Gz designs.

## Work outstanding at the time

Three-axis batch design and interlayer keys were still pending. Their subsequent
implementation is documented in [BATCH_AND_ASSEMBLY.md](BATCH_AND_ASSEMBLY.md).
