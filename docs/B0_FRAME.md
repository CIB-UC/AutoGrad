# B0 and the coordinate frame

New designs use one physical XYZ frame for meshes, STL files, target samples,
field vectors and viewers. The default cylinder axis is **+Z**. Changing B0 does
not move the cylinder or exchange the ROI's X/Y/Z radii.

B0 supports +X, −X, +Y, −Y, +Z and −Z; the default is +Y. Optimization uses the
signed component `B_parallel = B · B0_hat`:

- Gx is `d(B_parallel)/dx`.
- Gy is `d(B_parallel)/dy`.
- Gz is `d(B_parallel)/dz`.

Reversing B0 reverses the target's physical component and corresponding current
direction to preserve the requested positive gradient. The vector also reaches
CoilGen cut selection. Contour significance, polarity selection, field errors,
derivatives and regression all use the same projection. Full vector fields are
retained for inspection.

Metrics record `b0_direction`, `b0_vector`, `coordinate_frame` and the signed
component. Design-state JSON saves B0 and configuration. CLI examples include
`--axis x --b0=+y` and `--axis z --b0=-x`.

## Compatibility with older designs

The previous workflow labeled internal y/z/x targets as Gx/Gy/Gz, while leaving
fields in the geometry frame and optimizing Bz. Mesh rotation alone did not
turn Bz into By. B0 selection corrects that inconsistency, so B0=+Y designs can
differ from older designs with matching names. Do not compare them by Gx/Gy/Gz
labels alone.

Historical files and names remain available. The old permutation helper is
retained only to locate older STLs. Reuse requires compatible design state,
sidecars, parameters and hashes. Designs lacking provenance must be regenerated;
changing viewer labels does not convert their geometry. The low-level engine
still defaults to +Z when called directly without `b_0_direction`.

## Verification

`tests/test_b0_physics.py` checks all 18 gradient-axis/B0-axis combinations,
sign reversal in a known optimization operator, analytical gradients against
Biot–Savart finite differences, transverse contours, polarity selection and
regression in physical coordinates.

After terminal creation, Biot–Savart is evaluated again on the retained winding
and both leads, preserving CoilGen current direction. External supply and return
wiring are excluded. See [validation and limitations](VALIDATION.md).
