"""Crossing ramps must not send both branches into the same radial layer."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from halbach_coils.coilgen.overlap import wire_contact_pairs
from pyCoilGen.sub_functions.data_structures import Mesh, Shape3D

module = importlib.import_module('pyCoilGen.sub_functions.shift_return_paths')


def test_neighbouring_crossings_keep_opposite_layers_after_smoothing():
    # One branch encounters two other branches within a smoothing window.
    # Independent choices select one point on each side, so their ramps merge.
    pairs = np.array([[30, 100], [31, 160]])
    previous = np.zeros(200)
    previous[[31, 32, 100, 101]] = 1
    kernel = np.r_[np.arange(1, 8), np.full(7, 7), np.arange(6, 0, -1)] / 7
    old = np.minimum(np.convolve(previous, kernel, mode='same'), 1)
    assert abs(old[30] - old[100]) * .004 < .002

    points = module.crossing_shift_points(pairs, previous, len(kernel))
    shifted = np.minimum(np.convolve(points, kernel, mode='same'), 1)
    # Both ends of every crossed segment must remain fully separated.
    for left, right in pairs:
        for endpoint in (0, 1):
            assert abs(shifted[left + endpoint] - shifted[right + endpoint]) == 1


def test_three_competing_branches_do_not_get_an_invented_third_layer():
    pairs = np.array([[10, 60], [12, 110], [62, 112]])
    previous = np.zeros(150)
    assert module.crossing_shift_points(pairs, previous, 20) is None
    np.testing.assert_array_equal(previous, np.zeros(150))


def test_original_gx_parameters_clear_the_real_two_mm_wire():
    # Geometry just before return-path shifting: Gx, 12 levels, Tk=20000,
    # cylinder R=67.3 mm / L=170 mm, ROI radii=50 mm, 1 mm cuts.
    # No optimizer, machine paths or pickled Python objects are needed.
    filename = Path(__file__).parent / 'test_data' / 'gx_crossing_ramps.npz'
    with np.load(filename, allow_pickle=False) as saved:
        mesh = Mesh(vertices=saved['vertices'], faces=saved['faces'])
        mesh.uv = saved['mesh_uv']
        path = Shape3D(v=saved['wire_v'], uv=saved['wire_uv'])
        legacy = saved['legacy_path']
    assert wire_contact_pairs(legacy, .002, closed=True)[2].min() < 1e-6
    part = SimpleNamespace(coil_mesh=mesh, wire_path=path)
    args = SimpleNamespace(skip_normal_shift=False, normal_shift_smooth_factors=[7, 7, 7],
                           normal_shift_length=-.004, smooth_factor=3,
                           conductor_thickness=.002)

    module.shift_return_paths([part], args)

    assert not len(wire_contact_pairs(part.wire_path.v.T, .002, closed=True)[0])
    radii = np.linalg.norm(part.wire_path.v[:2], axis=0)
    assert radii.min() >= .06325 and radii.max() <= .06735
    np.testing.assert_allclose(np.abs(np.diff(part.crossing_layer_factors, axis=1)), 1)


def test_already_separated_route_keeps_its_original_layer_selection(monkeypatch):
    # A single isolated crossing is already resolved by the original logic.
    mesh = Mesh(vertices=np.array([[-1., -1., 0.], [1., -1., 0.],
                                   [1., 1., 0.], [-1., 1., 0.]]),
                faces=np.array([[0, 1, 2], [0, 2, 3]]))
    mesh.uv = mesh.get_vertices()[:, :2]
    anchors = np.array([[-.5, 0, 0], [.5, 0, 0], [.5, .5, 0],
                        [0, .5, 0], [0, -.5, 0]])
    path = np.vstack([np.linspace(a, b, 25, endpoint=False)
                      for a, b in zip(anchors[:-1], anchors[1:])] + [anchors[-1:]])
    part = SimpleNamespace(coil_mesh=mesh, wire_path=Shape3D(v=path.T, uv=path[:, :2].T))
    args = SimpleNamespace(skip_normal_shift=False, normal_shift_smooth_factors=[7, 7, 7],
                           normal_shift_length=-.004, smooth_factor=1,
                           conductor_thickness=.002)

    def unexpected_repair(*_):
        raise AssertionError('An already separated crossing must retain its original route')

    monkeypatch.setattr(module, 'crossing_shift_points', unexpected_repair)
    module.shift_return_paths([part], args)
    assert not len(wire_contact_pairs(part.wire_path.v.T, .002, closed=False)[0])
