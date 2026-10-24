"""Cuts through mesh vertices must not create a zero high/low direction."""

from types import SimpleNamespace as NS
import importlib

import numpy as np
import pytest

module = importlib.import_module('pyCoilGen.sub_functions.find_group_cut_position')


@pytest.mark.parametrize('start', range(4))
def test_plane_through_vertices_keeps_two_distinct_cuts(monkeypatch, start):
    vertices = np.array([[0., 1., 0., -1.], [1., 0., -1., 0.], [0., 0., 0., 0.]])
    vertices = np.roll(vertices, start, axis=1)
    vertices = np.column_stack((vertices, vertices[:, 0]))
    loop = NS(v=vertices, uv=vertices[:2])
    monkeypatch.setattr(module, 'calc_mean_loop_normal', lambda *_: np.array([0., 0., 1.]))
    with np.errstate(invalid='raise', divide='raise'):
        cuts = module.find_group_cut_position(NS(loops=[loop, loop]), np.zeros(3),
                                              None, np.array([0., 1., 0.]), 'B0')
    for cut in cuts:
        assert cut.cut_point.v.shape == (2, 3)
        assert cut.cut_point.uv.shape == (2, 2)
        assert np.linalg.norm(cut.high_cut.v - cut.low_cut.v) == pytest.approx(2.)
        np.testing.assert_array_equal(cut.high_cut.v, [0., -1., 0.])
        np.testing.assert_array_equal(cut.low_cut.v, [0., 1., 0.])
        assert len(cut.cut_point.segment_ind) == 2
