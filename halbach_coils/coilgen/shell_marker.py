"""Automatically sized, unsigned B0 orientation marks for the finished shell.

All geometry is in metres and the physical XYZ frame. Transverse B0 is
projected onto each annular end face. Axial B0 uses a longitudinal recess on
the outside wall near each end, since it has no direction in the end plane.
"""

from __future__ import annotations

import manifold3d as m3d
import numpy as np

from .config import Config
from .geometry import b0_unit_vector, rodrigues_rotation_matrix


def _box(size, basis, center):
    transform = np.column_stack((basis, center))
    return m3d.Manifold.cube(tuple(size), center=True).transform(transform)


class MarkerPlacementError(RuntimeError):
    """No complete rim footprint is available on the requested B0 side."""


def marker_dimensions(inner, outer, height):
    """Automatic length, width and depth, in the input dimensions' units."""
    wall = outer - inner
    if not np.isfinite([inner, outer, height]).all() or min(inner, wall, height) <= 0:
        raise ValueError('B0 marks require a hollow shell with positive wall thickness and height.')
    length = min(.60 * wall, .04 * height)
    return length, min(.22 * wall, .025 * outer, length / 3), min(.12 * wall, .005 * height)


def marker_radial_direction(cfg):
    """Positive unsigned B0 projection, or the cylinder's X reference for axial B0."""
    axis = cfg.rotated_cylinder_axis
    b0 = b0_unit_vector('+' + cfg.b0_direction[-1].lower())
    radial = b0 - np.dot(b0, axis) * axis
    transverse = np.linalg.norm(radial) > 1e-8
    if transverse:
        radial /= np.linalg.norm(radial)
    else:
        rotation = rodrigues_rotation_matrix(cfg.cylinder.rot_axis, cfg.cylinder.rot_angle)
        radial = rotation @ np.array([1., 0., 0.])
    return radial, transverse


def mark_shell_b0(results: list[tuple[str, m3d.Manifold]], cfg: Config,
                  *, side: int | None = None) -> list[tuple[str, m3d.Manifold]]:
    """Carve marks after all radius trims, before export/unit conversion.

    Disabled is a strict no-op. Dimensions follow the *finished* shell,
    including custom halves and radial trims. Validate that both footprints
    are supported by material before cutting: never shift a mark away from
    B0 to dodge a groove, or silently publish a missing/partly erased mark.
    ``side`` is an internal assembly constraint to keep all batch marks aligned.
    """
    if not cfg.shell.b0_marker:
        return results
    if side is not None and side not in (1, -1):
        raise ValueError('B0 marker side must be +1 or -1.')

    axis = cfg.rotated_cylinder_axis
    vertices = np.vstack([
        np.asarray(solid.to_mesh64().vert_properties)[:, :3]
        for _, solid in results
    ])
    axial = vertices @ axis
    radii = np.linalg.norm(vertices - axial[:, None] * axis, axis=1)
    lower, upper = float(axial.min()), float(axial.max())
    inner, outer = float(radii.min()), float(radii.max())
    # Leave 20% of the wall radially on either side of an end-face mark.
    # The width cap also keeps the rectangle inside the curved outer edge.
    length, width, depth = marker_dimensions(inner, outer, upper - lower)
    overcut = depth * .1
    radial, transverse = marker_radial_direction(cfg)
    # Either side of the same B0 axis conveys the same unsigned direction.
    # Choose a side clear at *both* ends; keep the marks at the same azimuth.
    for side in ((1, -1) if side is None else (side,)):
        radial_side = side * radial
        basis = np.column_stack((radial_side, np.cross(axis, radial_side), axis))
        cutters = []
        for end, inward in ((lower, 1), (upper, -1)):
            if transverse:
                radial_center = (inner + outer) / 2
                center = radial_center * radial_side + (end + inward * (depth - overcut) / 2) * axis
                cutter = _box((length, width, depth + overcut), basis, center)
                support = _box((length, width, depth), basis,
                               radial_center * radial_side + (end + inward * depth / 2) * axis)
            else:
                axial_center = end + inward * .75 * length
                center = (outer - (depth - overcut) / 2) * radial_side + axial_center * axis
                cutter = _box((depth + overcut, width, length), basis, center)
                # Check below the greatest sagitta across the curved wall.
                sagitta = outer - np.sqrt(outer**2 - (width / 2)**2)
                support_depth = depth - sagitta - overcut
                support = _box((support_depth, width, length), basis,
                               (outer - depth + support_depth / 2) * radial_side + axial_center * axis)

            supported_volume = sum((solid ^ support).volume() for _, solid in results)
            if supported_volume < support.volume() * (1 - 1e-5):
                break
            cutters.append(cutter)
        if len(cutters) == 2:
            break
    else:
        raise MarkerPlacementError(
            'B0 marker overlaps a groove, lead exit or gap in the shell at an end on the requested sides. '
            'Disable the B0 orientation mark or leave a clear rim at the B0 axis.')

    print(f"  B0 orientation marks: {cfg.b0_direction[-1].upper()} axis (unsigned), "
          f"{'end faces' if transverse else 'outer wall near the ends'}")
    print(f"    Radial location (physical XYZ): {np.round(side * radial, 6).tolist()}")
    print(f"    Automatic size: {length*1000:.3f} x {width*1000:.3f} mm, "
          f"depth {depth*1000:.3f} mm")
    marked = []
    for label, solid in results:
        for cutter in cutters:
            solid = solid - cutter
        if solid.status() != m3d.Error.NoError or solid.is_empty():
            raise RuntimeError('B0 marker subtraction produced an invalid shell.')
        marked.append((label, solid))
    return marked
