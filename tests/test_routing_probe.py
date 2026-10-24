"""Candidate probes prune once and skip solid mesh construction."""

from types import SimpleNamespace as NS

import numpy as np

from pyCoilGen.sub_functions.create_sweep_along_surface import create_sweep_along_surface
from pyCoilGen.sub_functions.data_structures import Shape3D


def test_probe_needs_no_mesh_normals_and_prepared_path_is_not_pruned_twice():
    angle = np.linspace(0, 2*np.pi, 100)
    path = np.vstack((.03*np.cos(angle), .03*np.sin(angle), np.zeros(100)))
    section = np.linspace(0, 2*np.pi, 17)
    args = NS(skip_sweep=False, specific_conductivity_conductor=1.68e-8,
              conductor_thickness=.0015, auto_wire_clearance=False,
              cross_sectional_points=np.vstack((.0015*np.cos(section), .00075*np.sin(section))))
    # The probe must finish without reading UV triangles, normals or faces.
    part = NS(coil_mesh=object(), wire_path=Shape3D(v=path, uv=path[:2]))
    create_sweep_along_surface([part], args, validation_only=True)
    prepared = part.wire_path.v.copy()
    assert prepared.shape[1] < path.shape[1]
    assert not hasattr(part, 'layout_surface_mesh')
    create_sweep_along_surface([part], args, validation_only=True, prepared=True)
    np.testing.assert_array_equal(part.wire_path.v, prepared)
