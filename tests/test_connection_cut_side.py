"""Single global cut-side requests must reach the chosen geometric cut."""
from types import SimpleNamespace as NS
import importlib
import numpy as np
import pytest

module = importlib.import_module('pyCoilGen.sub_functions.interconnect_within_groups')


@pytest.mark.parametrize('selection,expected', [([], [1,2,3]),
                                               (['high'],[1,2,3]),
                                               (['low'],[-1,-2,-3])])
def test_global_cut_side_reaches_the_actual_loop_opening(monkeypatch,selection,expected):
    high,low = np.array([1.,2,3]),np.array([-1.,-2,-3])
    loop = NS(v=np.array([[0.,1,0],[0.,0,1],[0.,0,0]]))
    part = NS(groups=[NS(loops=[loop,loop])],loop_groups=[0],
              coil_mesh=object(),group_centers=NS(v=np.zeros((3,1))))
    inputs = NS(force_cut_selection=selection,cut_plane_definition='nearest',
                b_0_direction=[0,1,0],interconnection_cut_width=.003)
    monkeypatch.setattr(module,'find_group_cut_position',lambda *_:[
        NS(high_cut=NS(v=high),low_cut=NS(v=low)) for _ in range(2)])
    class CutReached(Exception):
        pass
    def opening(_loop,center,width):
        np.testing.assert_array_equal(np.asarray(center).ravel(),expected)
        assert width == .003
        raise CutReached
    monkeypatch.setattr(module,'open_loop_with_3d_sphere',opening)
    with pytest.raises(CutReached):
        module.interconnect_within_groups([part],inputs)
