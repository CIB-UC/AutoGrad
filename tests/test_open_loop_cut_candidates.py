"""One-station cut candidates must not be silently discarded as empty."""

import numpy as np

from pyCoilGen.sub_functions.open_loop_with_3d_sphere import open_loop_with_3d_sphere
from pyCoilGen.sub_functions.data_structures import Shape3D


def test_single_station_inside_a_cut_sphere_is_a_valid_candidate():
    xy = np.array([[-.01, 0., .01, .01, 0., -.01, -.01, .01, -.01],
                   [0., 0., 0., .0008, .0008, .0008, .01, .01, 0.]])
    path = Shape3D(v=np.vstack((xy, np.zeros(xy.shape[1]))), uv=xy)
    with np.errstate(invalid='raise', divide='raise'):
        opened, _, cuts = open_loop_with_3d_sphere(path, np.zeros((3, 1)), .002)
    assert cuts.v.shape == (3, 2)
    assert np.isfinite(opened.v).all()
    np.testing.assert_allclose(np.linalg.norm(opened.v[:, [0, -1]], axis=0), .001)
