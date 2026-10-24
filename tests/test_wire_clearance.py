"""Physical separation, bounded recovery and cylinder/UV preservation."""

from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from pyCoilGen.helpers.wire_geometry import wire_contact_pairs
from pyCoilGen.sub_functions import wire_clearance as repair
from pyCoilGen.sub_functions.data_structures import Mesh, Shape3D
from pyCoilGen.sub_functions.calc_3d_rotation_matrix_by_vector import calc_3d_rotation_matrix_by_vector


def dense_gy():
    with np.load(Path(__file__).parent/'test_data'/'gy_dense_turns.npz', allow_pickle=False) as data:
        return data['path']


def test_real_twenty_level_gy_is_separated_without_changing_layers_or_turns():
    original = dense_gy()
    fixed, report = repair.separate_cylindrical_path(original, .002, (-.08075, .08075), max_seconds=60)
    assert report['status'] == 'repaired'
    assert report['initial_contact_pairs'] == 38
    assert report['initial_minimum_mm'] == pytest.approx(1.8709831676334943)
    assert fixed.shape == original.shape
    assert not len(wire_contact_pairs(fixed, .002, closed=True)[0])
    np.testing.assert_allclose(np.linalg.norm(fixed[:, :2], axis=1),
                               np.linalg.norm(original[:, :2], axis=1), atol=1e-15)
    assert fixed[:, 2].min() >= -.08075 and fixed[:, 2].max() <= .08075
    assert 0 < report['max_displacement_mm'] < 1
    assert report['iterations'] <= 24
    # A feasible result is stable: another call must not keep moving its turns.
    repeated, again = repair.separate_cylindrical_path(fixed, .002, (-.08075, .08075))
    np.testing.assert_array_equal(repeated, fixed)
    assert again['status'] == 'unchanged'


@pytest.mark.parametrize('limits', [{'max_iterations': 0}, {'max_seconds': 0.},
                                  {'max_displacement': .000001, 'max_iterations': 3}])
def test_exhausted_limits_roll_back_instead_of_accepting_a_partial_repair(limits):
    original = dense_gy()
    fixed, report = repair.separate_cylindrical_path(original, .002, (-.08075, .08075), **limits)
    np.testing.assert_array_equal(fixed, original)
    assert report['status'] == 'unresolved'
    assert report['remaining_contact_pairs'] > 0


def test_an_actual_crossing_requires_a_different_route():
    path = np.array([[-.01,0,0],[.01,0,0],[.01,.02,0],[0,.02,0],[0,-.01,0]])
    fixed, report = repair.separate_cylindrical_path(path, .002, (-.04, .04))
    np.testing.assert_array_equal(fixed, path)
    assert report['status'] == 'unresolved'
    assert report['reason'] == 'crossing_requires_different_routing'


def test_a_real_chain_of_crowded_turns_is_redistributed_jointly():
    with np.load(Path(__file__).parent/'test_data'/'gy_crowded_chain.npz') as data:
        original = data['path']
    fixed, report = repair.separate_cylindrical_path(
        original, .002, (-.08075, .08075), max_seconds=60)
    assert report['status'] == 'repaired'
    assert report['method'] == 'axial_turn_redistribution'
    assert report['initial_contact_pairs'] == 1990
    assert report['initial_minimum_mm'] == pytest.approx(1.7186196930238236)
    assert report['minimum_mm'] >= 2.02
    assert not len(wire_contact_pairs(fixed, .002, closed=False)[0])
    np.testing.assert_array_equal(fixed[:, :2], original[:, :2])
    assert fixed[:, 2].min() >= -.08075 and fixed[:, 2].max() <= .08075
    assert 1 < report['max_displacement_mm'] <= 4
    # One monotone smooth height map preserves every branch's axial ordering.
    order = np.argsort(original[:, 2])
    dz = np.diff(original[order, 2])
    mapped_dz = np.diff(fixed[order, 2])
    assert np.all(mapped_dz >= .5*dz-1e-12)
    assert np.all(mapped_dz <= 1.5*dz+1e-12)
    repeated, again = repair.separate_cylindrical_path(fixed, .002, (-.08075, .08075))
    np.testing.assert_array_equal(repeated, fixed)
    assert again['status'] == 'unchanged'


def test_joint_recovery_respects_explicit_displacement_and_time_limits():
    with np.load(Path(__file__).parent/'test_data'/'gy_crowded_chain.npz') as data:
        original = data['path']
    fixed, attempt = repair._redistribute_axially(
        original, .002, (-.08075, .08075), .0001, 4, repair.time.monotonic()+10)
    np.testing.assert_array_equal(fixed, original)
    assert attempt['status'] == 'unresolved'
    assert attempt['reason'] == 'no_feasible_axial_map_within_limits'
    fixed, attempt = repair._redistribute_axially(
        original, .002, (-.08075, .08075), .004, 4, repair.time.monotonic()-1)
    np.testing.assert_array_equal(fixed, original)
    assert attempt['status'] == 'unresolved'
    assert attempt['reason'] == 'time_budget_exhausted'


def test_closest_segment_parameters_reconstruct_the_distance():
    a = np.array([[0., 0., 0.], [0., 0., 0.], [0., 0., 0.]])
    b = np.array([[1., 0., 0.], [1., 0., 0.], [0., 0., 0.]])
    c = np.array([[.5, -1., 1.], [2., 1., 0.], [1., 1., 0.]])
    d = np.array([[.5, 1., 1.], [2., 2., 0.], [2., 1., 0.]])
    distance, vector, s, t = repair.segment_closest(a, b, c, d, return_parameters=True)
    assert np.all((s >= 0) & (s <= 1) & (t >= 0) & (t <= 1))
    np.testing.assert_allclose(c+t[:, None]*(d-c)-a-s[:, None]*(b-a), vector)
    np.testing.assert_allclose(np.linalg.norm(vector, axis=1), distance)
    np.testing.assert_allclose(distance, [1., np.sqrt(2), np.sqrt(2)])


def test_clearance_margin_keeps_the_physical_arc_exclusion_fixed():
    path = np.array([[.02,0,0],[.03,0,0],[.03,.0023,0],
                     [.03,.0005,0],[.02,.0005,0]])
    i, j, *_ = wire_contact_pairs(path, .002, closed=False)
    assert (0, 3) in set(zip(i, j))
    i, j, *_ = wire_contact_pairs(path, .0021, closed=False, local_diameter=.002)
    assert (0, 3) in set(zip(i, j))


@pytest.mark.parametrize('angle', [0., np.pi/4])
def test_sweep_repair_updates_uv_and_preserves_a_rotated_cylinder(angle):
    path = dense_gy()
    with np.load(Path(__file__).parent/'test_data'/'gx_crossing_ramps.npz', allow_pickle=False) as data:
        vertices = data['vertices'].copy()
        vertices[:, :2] *= .0776/.0673
        rotation = calc_3d_rotation_matrix_by_vector(np.array([0, 1, 0]), angle)
        mesh = Mesh(vertices=vertices @ rotation, faces=data['faces'])
        mesh.uv = data['mesh_uv']
    part = NS(coil_mesh=mesh, wire_path=Shape3D(v=(path @ rotation).T,
                                              uv=np.zeros((2, len(path)))))
    args = NS(auto_wire_clearance=True, surface_is_cylinder_flag=True,
              cylinder_mesh_parameter_list=[.1615,.0776,200,10,0,1,0,angle],
              conductor_thickness=.002)
    repair.ensure_wire_clearance(part, args)
    assert part.clearance_report['status'] == 'repaired'
    local = part.wire_path.v.T @ rotation.T
    np.testing.assert_allclose(np.linalg.norm(local[:, :2], axis=1),
                               np.linalg.norm(path[:, :2], axis=1), atol=1e-14)
    assert not len(wire_contact_pairs(local, .002, closed=True)[0])
    assert np.isfinite(part.wire_path.uv).all()
    assert np.any(part.wire_path.uv != 0)


def test_uv_projection_failure_preserves_the_actual_conductor(monkeypatch):
    path = dense_gy()
    with np.load(Path(__file__).parent/'test_data'/'gx_crossing_ramps.npz', allow_pickle=False) as data:
        vertices = data['vertices'].copy(); vertices[:, :2] *= .0776/.0673
        mesh = Mesh(vertices=vertices, faces=data['faces']); mesh.uv = data['mesh_uv']
    part = NS(coil_mesh=mesh, wire_path=Shape3D(v=path.T.copy(), uv=np.zeros((2, len(path)))))
    args = NS(auto_wire_clearance=True, surface_is_cylinder_flag=True,
              cylinder_mesh_parameter_list=[.1615,.0776,200,10,0,1,0,0], conductor_thickness=.002)
    def fail(*_):
        raise ValueError('projection failed')
    monkeypatch.setattr(repair, '_updated_uv', fail)
    repair.ensure_wire_clearance(part, args)
    np.testing.assert_array_equal(part.wire_path.v.T, path)
    assert part.clearance_report['status'] == 'unresolved'
    assert part.clearance_report['remaining_contact_pairs'] == 38
