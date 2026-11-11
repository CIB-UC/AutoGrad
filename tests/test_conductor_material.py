from pathlib import Path
from types import SimpleNamespace
import math
import sys

import numpy as np
import pytest

# GUI modules are launched with ``halbach_coils`` on sys.path by run_gui.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'halbach_coils'))

from halbach_coils.coilgen.config import (
    CONDUCTOR_MATERIAL_RESISTIVITY,
    Config,
)
from halbach_coils.gui.pipeline_panel import PipelinePanel
from pyCoilGen.sub_functions import calculate_inductance_by_coil_layout as inductance
from pyCoilGen.sub_functions.create_sweep_along_surface import (
    electrical_cross_section_area,
)


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Root:
    @staticmethod
    def tr(text):
        return text


def test_default_material_is_copper_with_matching_resistivity():
    cfg = Config()

    assert cfg.fasthenry.material == 'Cu'
    assert cfg.fasthenry.specific_conductivity == pytest.approx(
        CONDUCTOR_MATERIAL_RESISTIVITY['Cu']
    )


def test_explicit_si_names_preserve_legacy_configuration():
    cfg = Config()
    cfg.fasthenry.resistivity_ohm_m = 2.82e-8
    assert cfg.fasthenry.specific_conductivity == 2.82e-8
    assert cfg.fasthenry.conductivity_s_per_m == pytest.approx(1 / 2.82e-8)
    params = cfg.to_params_dict()
    assert params['conductor_resistivity_ohm_m'] == 2.82e-8
    assert params['conductor_conductivity_S_per_m'] == pytest.approx(1 / 2.82e-8)


@pytest.mark.parametrize('groove_factor', [1., 2., 3.])
def test_real_surface_sweep_one_metre_wire_has_known_resistance(groove_factor):
    from pyCoilGen.sub_functions.create_sweep_along_surface import create_sweep_along_surface
    from pyCoilGen.sub_functions.data_structures import Mesh
    mesh = Mesh(vertices=np.array([[-1.,-1.,0.],[2.,-1.,0.],[-1.,2.,0.]]),
                faces=np.array([[0,1,2]]))
    mesh.uv = mesh.get_vertices()[:,:2]
    mesh.fn = np.array([[0.,0.,1.]])
    cfg = Config()
    cfg.wire.cross_section_a_frac = groove_factor
    args = SimpleNamespace(skip_sweep=False, cross_sectional_points=cfg.cross_sectional_points,
                           conductor_cross_section_area=math.pi*1e-6,
                           specific_conductivity_conductor=1.68e-8)
    part = SimpleNamespace(coil_mesh=mesh, wire_path=SimpleNamespace(
        v=np.array([[0.,.5,1.],[0.,0.,0.],[0.,0.,0.]]),
        uv=np.array([[0.,.5,1.],[0.,0.,0.]])))
    create_sweep_along_surface([part], args)
    assert part.ohmian_resistance == pytest.approx(0.005347606087887683)


def test_resistance_matrix_material_factor_is_rho_over_thickness():
    from pyCoilGen.sub_functions.calculate_resistance_matrix import calculate_resistance_matrix
    from pyCoilGen.sub_functions.data_structures import Mesh
    mesh = Mesh(vertices=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]),
                faces=np.array([[0,1,2]]))
    def matrix(rho, thickness):
        part = SimpleNamespace(coil_mesh=mesh, basis_elements=[SimpleNamespace(
            triangles=np.array([0]), area=np.array([.5]), current=np.array([current]))
            for current in ([1.,0,0],[0.,1,0],[-1.,-1,0])])
        args = SimpleNamespace(conductor_thickness=thickness,
                               specific_conductivity_conductor=rho)
        calculate_resistance_matrix([part],args)
        return part.resistance_matrix
    unit = matrix(1.,1.)
    copper = matrix(1.68e-8,.002)
    np.testing.assert_allclose(copper, unit * 1.68e-8/.002, rtol=1e-14,atol=0)
    np.testing.assert_allclose(matrix(2.82e-8,.002), copper*(2.82/1.68),rtol=1e-14,atol=0)


def test_material_and_resistivity_are_serialized_for_metrics():
    cfg = Config()
    cfg.fasthenry.material = 'Al'
    cfg.fasthenry.specific_conductivity = CONDUCTOR_MATERIAL_RESISTIVITY['Al']

    params = cfg.to_params_dict()

    assert params['conductor_material'] == 'Al'
    assert params['specific_conductivity_conductor_ohm_m'] == pytest.approx(2.82e-8)


def test_deformed_groove_does_not_change_real_circular_electrical_area():
    cfg = Config()
    cfg.wire.conductor_width = 0.002
    cfg.wire.cross_section_a_frac = 2.0
    cfg.wire.cross_section_b_frac = 1.0

    assert cfg.electrical_cross_section_area == pytest.approx(math.pi * 1e-6)
    assert cfg.groove_cross_section_area == pytest.approx(2 * math.pi * 1e-6)
    assert cfg.groove_area_ratio == pytest.approx(2.0)
    assert (cfg.fasthenry_conductor_width * cfg.fasthenry_conductor_height
            == pytest.approx(cfg.electrical_cross_section_area))
    params = cfg.to_params_dict()
    assert params['electrical_section_shape'] == 'circle'
    assert params['groove_to_electrical_area_ratio'] == pytest.approx(2.0)


def test_pycoilgen_resistance_area_prefers_real_area_over_swept_groove():
    args = SimpleNamespace(conductor_cross_section_area=3.14e-6)

    assert electrical_cross_section_area(args, swept_area=6.28e-6) == pytest.approx(3.14e-6)
    assert electrical_cross_section_area(
        SimpleNamespace(), swept_area=6.28e-6) == pytest.approx(6.28e-6)


def test_gui_material_selection_updates_pipeline_config():
    panel = object.__new__(PipelinePanel)
    panel.material_var = _Var('Al')
    panel.resistivity_var = _Var('2.82e-8')
    panel.root = _Root()
    cfg = Config()

    panel._apply_material(cfg)

    assert cfg.fasthenry.material == 'Al'
    assert cfg.fasthenry.specific_conductivity == pytest.approx(2.82e-8)


def test_gui_converts_real_and_groove_dimensions_to_deformation_factors():
    panel = object.__new__(PipelinePanel)
    panel.cw_var = _Var('2')
    panel.a_var = _Var('4')
    panel.b_var = _Var('2')
    panel.root = _Root()
    cfg = Config()

    panel._apply_wire_geometry(cfg)

    assert cfg.wire.conductor_width == pytest.approx(0.002)
    assert cfg.wire.cross_section_a_frac == pytest.approx(2.0)
    assert cfg.wire.cross_section_b_frac == pytest.approx(1.0)
    assert cfg.groove_radial_height == pytest.approx(0.004)
    assert cfg.groove_tangential_width == pytest.approx(0.002)


@pytest.mark.parametrize('value', ['0', '-1e-8', 'nan', 'inf'])
def test_gui_rejects_invalid_resistivity(value):
    panel = object.__new__(PipelinePanel)
    panel.material_var = _Var('Custom')
    panel.resistivity_var = _Var(value)
    panel.root = _Root()

    with pytest.raises(ValueError, match='positive number'):
        panel._apply_material(Config())


def test_fasthenry_receives_conductivity_derived_from_selected_resistivity(
        monkeypatch, tmp_path):
    captured = {}
    fake_bin = tmp_path / 'fasthenry.exe'
    fake_bin.touch()

    def fake_create(_path, _width, _height, _freq, conductivity, _downsample):
        captured['conductivity'] = conductivity
        return 'input.inp', 'suffix'

    result = SimpleNamespace(
        coil_resistance=1.0, coil_inductance=2.0, coil_cross_section=3.0)
    monkeypatch.setattr(inductance, 'create_fast_henry_file', fake_create)
    monkeypatch.setattr(inductance, 'execute_fast_henry_file_script_windows',
                        lambda *_args: result)
    monkeypatch.setattr(inductance.platform, 'system', lambda: 'Windows')

    coil_part = SimpleNamespace(
        wire_path=SimpleNamespace(v=np.array(
            [[0.0, 1.0], [0.0, 0.0], [0.0, 0.0]])))
    solution = SimpleNamespace(coil_parts=[coil_part])
    args = SimpleNamespace(
        skip_inductance_calculation=False,
        skip_postprocessing=False,
        conductor_cross_section_width=0.001,
        conductor_cross_section_height=0.001,
        fasthenry_bin=str(fake_bin),
        specific_conductivity_conductor=CONDUCTOR_MATERIAL_RESISTIVITY['Al'],
    )

    inductance.calculate_inductance_by_coil_layout(solution, args)

    assert captured['conductivity'] == pytest.approx(1.0 / 2.82e-8)
