"""The actual 22-level GY crossing must be recovered before routing retries."""

from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from pyCoilGen.helpers.wire_geometry import closed_wire_path, wire_contact_pairs
from pyCoilGen.sub_functions import wire_clearance as recovery
from pyCoilGen.sub_functions.data_structures import Mesh, Shape3D


def actual_gy():
    with np.load(Path(__file__).parent/'test_data'/'gy_crossing_22_levels.npz') as data:
        return data['path']


def test_exact_failed_gy_recovers_within_its_existing_radial_envelope():
    original = actual_gy()
    path, report = recovery.separate_crossing_branches(
        original, .0015, (-.08075, .08075), max_seconds=30)
    assert report['status'] == 'repaired'
    assert report['initial_contact_pairs'] == 38
    assert report['initial_minimum_mm'] == pytest.approx(.000535163118391119)
    assert report['minimum_mm'] >= 1.515
    assert not len(wire_contact_pairs(path, .0015, closed=False)[0])
    before, after = np.linalg.norm(original[:, :2], axis=1), np.linalg.norm(path[:, :2], axis=1)
    assert after.min() >= before.min()-1e-14 and after.max() <= before.max()+1e-14
    assert path[:, 2].min() >= -.08075 and path[:, 2].max() <= .08075
    assert path.shape == original.shape
    assert report['max_displacement_mm'] <= 4.5


def test_active_segment_checks_match_the_same_subset_of_the_full_exact_check():
    path = actual_gy()
    i, j, d, _ = wire_contact_pairs(path, .0015, closed=False)
    active = np.array([5393, 9225, 10454])
    selected = np.isin(i, active) | np.isin(j, active)
    a, b, distances, _ = wire_contact_pairs(path, .0015, closed=False, active_segments=active)
    np.testing.assert_array_equal(np.column_stack((a, b)), np.column_stack((i[selected], j[selected])))
    np.testing.assert_allclose(distances, d[selected], atol=1e-15)


def test_exhausted_spatial_recovery_keeps_the_original_path():
    path = actual_gy()
    result, report = recovery.separate_crossing_branches(
        path, .0015, (-.08075, .08075), max_seconds=0.)
    np.testing.assert_array_equal(result, path)
    assert report['status'] == 'unresolved'
    assert report['max_displacement_mm'] == 0.


def test_application_step_applies_the_recovery_and_updates_mesh_coordinates():
    path = actual_gy()
    with np.load(Path(__file__).parent/'test_data'/'gx_crossing_ramps.npz') as data:
        vertices = data['vertices'].copy()
        vertices[:, :2] *= .0658/.0673
        mesh = Mesh(vertices=vertices, faces=data['faces'])
        mesh.uv = data['mesh_uv']
    uv = recovery._updated_uv(mesh, path, np.eye(3), np.arange(len(path)), .0015)
    part = NS(coil_mesh=mesh, wire_path=Shape3D(v=path.T.copy(), uv=uv.T))
    args = NS(auto_wire_clearance=True, surface_is_cylinder_flag=True,
              cylinder_mesh_parameter_list=[.1615,.0658,200,10,0,1,0,0],
              conductor_thickness=.0015)
    recovery.ensure_wire_clearance(part, args)
    assert part.clearance_report['status'] == 'repaired'
    assert part.clearance_report['method'] == 'spatial_crossing_separation'
    assert part.clearance_report['closed_loop']
    assert part.wire_path.v.shape == path.T.shape
    assert np.isfinite(part.wire_path.uv).all()
    assert not len(wire_contact_pairs(closed_wire_path(part.wire_path.v.T), .0015, closed=True)[0])
