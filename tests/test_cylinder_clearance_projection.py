"""A coarse cylindrical mesh must retain a physically successful repair."""

from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from pyCoilGen.helpers.wire_geometry import closed_wire_path, wire_contact_pairs
from pyCoilGen.mesh_factory.build_cylinder_mesh import create_cylinder_mesh
from pyCoilGen.sub_functions.calc_3d_rotation_matrix_by_vector import calc_3d_rotation_matrix_by_vector
from pyCoilGen.sub_functions.data_structures import Shape3D
from pyCoilGen.sub_functions.parameterize_mesh import parameterize_mesh
from pyCoilGen.sub_functions import wire_clearance as repair


def cylinder(n_circ=40, n_long=40):
    args = NS(cylinder_mesh_parameter_list=[.114, .05, n_circ, n_long, 0, 1, 0, 0],
              surface_is_cylinder_flag=True, circular_diameter_factor=1., debug=0,
              auto_wire_clearance=True, conductor_thickness=.002)
    part = NS(coil_mesh=create_cylinder_mesh(args))
    parameterize_mesh([part], args)
    return part, args


@pytest.mark.parametrize('n_circ,n_long', [(200, 10), (40, 40), (16, 8)])
@pytest.mark.parametrize('angle', [0., .7])
def test_projection_uses_actual_facets_at_any_cylinder_resolution(n_circ, n_long, angle):
    part, _ = cylinder(n_circ, n_long)
    mesh = part.coil_mesh
    rotation = calc_3d_rotation_matrix_by_vector(np.array([0, 1, 0]), angle)
    mesh.trimesh_obj.vertices = mesh.get_vertices() @ rotation
    theta = np.pi/n_circ
    point = np.array([[.047*np.sin(theta), .047*np.cos(theta), 0.]])
    uv = repair._updated_uv(mesh, point, rotation, np.array([0]), .002)
    # At the midpoint of a facet the radial ray hits the midpoint of its edge.
    vertices = mesh.get_vertices() @ rotation.T
    edge = np.flatnonzero((np.abs(vertices[:, 2]) < 1e-12) &
                          (vertices[:, 0] >= -1e-12) &
                          (vertices[:, 0] <= .05*np.sin(2*np.pi/n_circ)+1e-12) &
                          (vertices[:, 1] >= .05*np.cos(2*np.pi/n_circ)-1e-12))
    assert len(edge) == 2
    np.testing.assert_allclose(uv[0], mesh.uv[edge].mean(axis=0), atol=1e-12)


def test_projection_rejects_stations_outside_the_axial_mesh():
    part, _ = cylinder()
    with pytest.raises(ValueError, match='Cannot project'):
        repair._updated_uv(part.coil_mesh, np.array([[0., .05, .06]]),
                           np.eye(3), np.array([0]), .002)


def test_reported_gx_keeps_successful_repair_on_the_40_by_40_mesh():
    with np.load(Path(__file__).parent/'test_data'/'gx_40x40_projection.npz') as data:
        original = data['path']
    part, args = cylinder()
    part.wire_path = Shape3D(v=original.T.copy(), uv=np.zeros((2, len(original))))
    repair.ensure_wire_clearance(part, args)
    report = part.clearance_report
    assert report['initial_contact_pairs'] == 1035
    assert report['status'] == 'repaired'
    assert report['remaining_contact_pairs'] == 0
    assert report['minimum_mm'] >= 2.02
    path = part.wire_path.v.T
    assert path.shape == original.shape
    assert np.isfinite(part.wire_path.uv).all()
    assert not len(wire_contact_pairs(closed_wire_path(path), .002, closed=True)[0])
    before, after = np.linalg.norm(original[:, :2], axis=1), np.linalg.norm(path[:, :2], axis=1)
    assert after.min() >= before.min()-1e-14
    assert after.max() <= before.max()+1e-14
    assert path[:, 2].min() >= -.057 and path[:, 2].max() <= .057
