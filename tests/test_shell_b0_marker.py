"""Physical orientation, rim clearance and actual STL export of B0 marks."""

import manifold3d as m3d
import numpy as np
import pytest
import trimesh

from halbach_coils.coilgen.config import Config
from halbach_coils.coilgen.geometry import b0_unit_vector, rodrigues_rotation_matrix
from halbach_coils.coilgen.presets import config_from_preset, config_to_preset
from halbach_coils.coilgen.shell import (
    export_validated_shell_stl, manifold_from_trimesh, run_shell, trimesh_from_manifold,
)
from halbach_coils.coilgen.shell_marker import mark_shell_b0


def _tube(scale=1, rotation=None, shift=0):
    tube = (m3d.Manifold.cylinder(.17, .039, circular_segments=128, center=True)
            - m3d.Manifold.cylinder(.18, .035, circular_segments=128, center=True))
    tube = tube.scale((scale, scale, scale)).translate((0, 0, shift))
    return tube if rotation is None else tube.transform(np.column_stack((rotation, np.zeros(3))))


def _cfg(direction='+y', gradient='x'):
    cfg = Config(gradient_axis=gradient, b0_direction=direction)
    cfg.shell.b0_marker = True
    return cfg


@pytest.mark.parametrize('direction', ['+x', '-x', '+y', '-y', '+z', '-z'])
@pytest.mark.parametrize('gradient', ['x', 'y', 'z'])
def test_marks_follow_b0_independently_of_gradient_and_export_closed(tmp_path, direction, gradient):
    original = _tube()
    marked = mark_shell_b0([('shell', original)], _cfg(direction, gradient))[0][1]
    removed = trimesh_from_manifold(original - marked)
    parts = removed.split()
    assert len(parts) == 2
    assert marked.volume() < original.volume()
    assert len(marked.decompose()) == 1
    for part in parts:
        if direction[-1] in 'xy':
            vector = b0_unit_vector('+' + direction[-1])
            np.testing.assert_allclose(part.center_mass[:2], (.037 * vector)[:2], atol=1e-10)
            assert abs(part.center_mass[2]) > .084
        else:
            assert part.center_mass[0] > .038
            assert abs(part.center_mass[2]) > .08
            # An axial mark's long dimension lies along B0.
            assert np.ptp(part.vertices[:, 2]) > 2 * np.ptp(part.vertices[:, 1])
    exported = trimesh_from_manifold(marked)
    exported.vertices *= 1000
    target = tmp_path / 'marked.stl'
    export_validated_shell_stl(exported, target)
    reloaded = trimesh.load_mesh(target)
    assert reloaded.is_watertight and reloaded.is_winding_consistent
    assert np.all(reloaded.nondegenerate_faces())
    np.testing.assert_allclose(reloaded.bounds, [[-39, -39, -85], [39, 39, 85]], atol=1e-5)


@pytest.mark.parametrize('axis', ['x', 'y', 'z'])
def test_both_polarities_produce_the_same_geometry(axis):
    original = _tube()
    positive = mark_shell_b0([('shell', original)], _cfg('+' + axis))[0][1]
    negative = mark_shell_b0([('shell', original)], _cfg('-' + axis))[0][1]
    assert (positive - negative).is_empty()
    assert (negative - positive).is_empty()


@pytest.mark.parametrize('angle,b0', [(np.pi / 2, '+y'), (np.pi / 2, '-z'), (.6, '+x')])
def test_rotation_uses_physical_b0_projection_and_actual_axial_bounds(angle, b0):
    cfg = _cfg(b0)
    cfg.cylinder.rot_angle = angle
    rotation = rodrigues_rotation_matrix(cfg.cylinder.rot_axis, angle)
    original = _tube(rotation=rotation, shift=.012)
    marked = mark_shell_b0([('shell', original)], cfg)[0][1]
    axis = cfg.rotated_cylinder_axis
    vector = b0_unit_vector('+' + b0[-1])
    projection = vector - (vector @ axis) * axis
    projection /= np.linalg.norm(projection)
    for part in trimesh_from_manifold(original - marked).split():
        center = part.center_mass
        np.testing.assert_allclose(center - (center @ axis) * axis, .037 * projection, atol=1e-10)
        assert abs((center @ axis) - .012) > .084


def test_dimensions_scale_with_finished_shell_instead_of_config_defaults():
    cfg = _cfg()
    removed_volumes = []
    for scale in [1, 2]:
        original = _tube(scale=scale)
        marked = mark_shell_b0([('shell', original)], cfg)[0][1]
        removed_volumes.append((original - marked).volume())
    assert removed_volumes[1] == pytest.approx(8 * removed_volumes[0])


def test_split_custom_halves_share_one_mark_even_when_it_crosses_the_seam():
    original = _tube(shift=.012)
    first = original ^ m3d.Manifold.cube((.1, .2, .4)).translate((0, -.1, -.2))
    second = original ^ m3d.Manifold.cube((.1, .2, .4)).translate((-.1, -.1, -.2))
    marked = mark_shell_b0([('a', first), ('b', second)], _cfg())
    whole = mark_shell_b0([('shell', original)], _cfg())[0][1]
    combined = marked[0][1] + marked[1][1]
    assert [label for label, _ in marked] == ['a', 'b']
    assert (combined - whole).is_empty() and (whole - combined).is_empty()
    assert all(solid.volume() < unmarked.volume()
               for (_, solid), unmarked in zip(marked, (first, second)))


def test_occupied_positive_rim_uses_opposite_side_of_same_b0_axis():
    notch = m3d.Manifold.cube((.003, .006, .004), center=True).translate((0, .037, .084))
    original = _tube() - notch
    marked = mark_shell_b0([('shell', original)], _cfg())[0][1]
    parts = trimesh_from_manifold(original - marked).split()
    assert len(parts) == 2
    for part in parts:
        assert abs(part.center_mass[0]) < 1e-10
        assert -.039 < part.center_mass[1] < -.035


def test_collision_is_reported_before_a_partly_missing_mark_is_published():
    notch = m3d.Manifold.cube((.003, .006, .004), center=True)
    original = _tube() - notch.translate((0, .037, .084)) - notch.translate((0, -.037, .084))
    with pytest.raises(RuntimeError, match='B0 marker overlaps'):
        mark_shell_b0([('shell', original)], _cfg())
    disabled = Config()
    results = [('shell', original)]
    assert mark_shell_b0(results, disabled) is results


@pytest.mark.parametrize('export_mm', [True, False])
def test_real_shell_stage_applies_toggle_before_export_and_unit_conversion(tmp_path, export_mm):
    cfg = _cfg('-y')
    cfg.cylinder.height = .17
    cfg.shell.output_in_mm = export_mm
    cfg.shell.leads_second_subtract = False
    wire = trimesh.creation.torus(major_radius=.037, minor_radius=.0008,
                                  major_sections=64, minor_sections=12)
    wire_path = tmp_path / 'Gradient_Gx_wire_0.stl'
    leads_path = tmp_path / 'Gradient_Gx_wire_0_with_leads.stl'
    wire.export(wire_path)
    wire.export(leads_path)
    cfg.shell.b0_marker = False
    _, unmarked_paths = run_shell(cfg, str(leads_path), align_wire_stl=str(wire_path),
                                 output_dir=str(tmp_path / 'unmarked'))
    cfg.shell.b0_marker = True
    _, marked_paths = run_shell(cfg, str(leads_path), align_wire_stl=str(wire_path),
                               output_dir=str(tmp_path / 'marked'))
    unmarked = trimesh.load_mesh(unmarked_paths[0])
    marked = trimesh.load_mesh(marked_paths[0])
    removed = manifold_from_trimesh(unmarked) - manifold_from_trimesh(marked)
    assert marked.is_watertight and marked.is_winding_consistent
    assert marked.volume < unmarked.volume
    np.testing.assert_allclose(marked.bounds, unmarked.bounds)
    parts = trimesh_from_manifold(removed).split()
    assert len(parts) == 2
    unit_scale = 1000 if export_mm else 1
    for part in parts:
        np.testing.assert_allclose(part.center_mass[:2], [0, .037 * unit_scale], atol=1e-5 * unit_scale)


@pytest.mark.parametrize('enabled', [True, False])
def test_marker_toggle_round_trips_in_presets(enabled):
    cfg = _cfg()
    cfg.shell.b0_marker = enabled
    loaded = config_from_preset(config_to_preset(cfg))
    assert loaded.shell.b0_marker is enabled


@pytest.mark.parametrize('arguments,enabled', [([], True), (['--no-b0-marker'], False)])
def test_pipeline_cli_enables_marks_unless_explicitly_disabled(monkeypatch, arguments, enabled):
    from halbach_coils import run_pipeline as pipeline
    configs = []
    monkeypatch.setattr(pipeline, 'run_pipeline', configs.append)
    monkeypatch.setattr('sys.argv', ['run_pipeline.py', *arguments])
    pipeline.main()
    assert configs[0].shell.b0_marker is enabled
