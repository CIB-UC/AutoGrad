"""Exercise the batch form's units, shared physics and process dispatch."""

from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'halbach_coils'))


@pytest.fixture
def app(fill_gui_design):
    import tkinter as tk
    from halbach_coils.gui.main_window import CoilGenApp

    try:
        root = CoilGenApp()
    except tk.TclError as exc:
        if 'display' in str(exc).lower():
            pytest.skip(str(exc))
        raise
    root.withdraw()
    root.update()
    fill_gui_design(root)
    yield root
    root.destroy()


def test_batch_replaces_standalone_and_preserves_physical_axes(app):
    from halbach_coils.coilgen.batch import BatchConfig, build_layer_configs

    assert not hasattr(app, 'standalone_panel')
    assert [app.notebook.tab(tab, 'text') for tab in app.notebook.tabs()] == [
        'Pipeline', 'Batch design', 'Tikhonov sweep']
    app.b0_var.set('-x')
    batch = app.batch_panel._build_cfg()
    assert batch.fit_clearance == BatchConfig().fit_clearance == .0003
    layers = build_layer_configs(batch)
    assert [cfg.gradient_axis for cfg in layers] == ['z', 'x', 'y']
    assert all(cfg.b0_direction == '-x' for cfg in layers)
    for cfg in layers:
        np.testing.assert_allclose(cfg.rotated_cylinder_axis, [0, 0, 1])
    app.localizer.set_language('es')
    app._refresh_language()
    assert app.notebook.tab(app.batch_panel, 'text') == 'Diseño en lote'
    assert 'Radio máximo del molde' in app.batch_panel.total_radius_label.cget('text')
    assert 'Holgura del encaje: 0.30 mm' in app.batch_panel.preview_notice.cget('text')


def test_batch_converts_mm_and_keeps_per_axis_values_when_reordered(app):
    from halbach_coils.coilgen.batch import build_layer_configs

    panel = app.batch_panel
    for axis, radius in zip('xyz', ('50', '38', '65')):
        panel.outer_radius_vars[axis].set(radius)
    for axis, length in zip('xyz', ('200', '160', '180')):
        panel.length_vars[axis].set(length)
    panel.key_length_var.set('6')
    panel.key_width_var.set('5')
    panel.fit_clearance_var.set('0.2')
    for axis, factor, levels in zip('xyz', [1000, 2000, 3000], [8, 10, 12]):
        panel.tikhonov_vars[axis].set(str(factor))
        panel.levels_vars[axis].set(str(levels))
    for axis, diameter, gap in zip('xyz', ['1.5', '2', '2.5'], ['0.25', '0.5', '0.75']):
        panel.cable_vars[axis].set(diameter)
        panel.layer_gap_vars[axis].set(gap)
    for axis, height, width in zip('xyz', ('3', '5', '4'), ('2.5', '3', '2')):
        panel.groove_height_vars[axis].set(height)
        panel.groove_width_vars[axis].set(width)
    panel.coilgen_advanced.variables['cylinder.n_circ'].set('64')
    batch = panel._build_cfg()
    assert batch.outer_radii == (.05, .038, .065)
    assert batch.axis_order == ('y', 'x', 'z')
    assert batch.conductor_widths == (.0015, .002, .0025)
    assert batch.groove_dimensions == ((.003, .0025), (.005, .003), (.004, .002))
    assert batch.layer_gaps == (.00025, .0005, .00075)
    assert batch.gradient_lengths == (.2, .16, .18)
    assert (batch.key_length, batch.key_width, batch.fit_clearance) == (.006, .005, .0002)
    assert batch.tikhonov_factors == (1000, 2000, 3000)
    assert batch.num_levels == (8, 10, 12)
    layers = build_layer_configs(batch)
    assert [(cfg.gradient_axis, cfg.tikhonov_factor, cfg.num_levels) for cfg in layers] == [
        ('y', 2000, 10), ('x', 1000, 8), ('z', 3000, 12)]
    assert [cfg.cylinder.height for cfg in layers] == [.2, .2, .2]
    assert [cfg.shell_outer_radius for cfg in layers] == [.038, .05, .065]
    assert all(cfg.cylinder.n_circ == 64 for cfg in layers)
    assert [cfg.shell_wall_thickness for cfg in layers] == pytest.approx([.0055, .00325, .00475])
    assert [cfg.groove_radial_height for cfg in layers] == [.005, .003, .004]
    assert [cfg.groove_tangential_width for cfg in layers] == [.003, .0025, .002]
    panel._redraw_preview()
    assert 'Shared mold length: 200.00 mm.' in panel.preview_notice.cget('text')
    assert 'Mold gaps: GY → GX 8.75 mm · GX → GZ 10.25 mm' in panel.preview_notice.cget('text')
    assert 'Real cable Ø 2.00 mm · Groove 5.00 × 3.00 mm' in panel.radius_labels['y'].cget('text')
    winding_ends = [line.get_data_3d()[2][0] for line in panel.ax3d.lines
                    if line.get_linestyle() == ':']
    assert winding_ends == pytest.approx([-76, 76, -95, 95, -85.5, 85.5])
    panel.enabled_vars['x'].set(False)
    panel.length_vars['x'].set('')
    panel.outer_radius_vars['x'].set('')
    panel.groove_height_vars['x'].set('')
    panel._redraw_preview()
    assert 'Shared mold length: 180.00 mm.' in panel.preview_notice.cget('text')
    assert panel._build_cfg().outer_radii == (None, .038, .065)
    assert [cfg.shell_outer_radius for cfg in panel._last_layers] == [.038, .065]


def test_outer_radius_stays_fixed_when_wall_dimensions_change(app):
    from halbach_coils.coilgen.batch import build_layer_configs

    panel = app.batch_panel
    for axis, radius in zip('xyz', ('38', '45', '31')):
        panel.outer_radius_vars[axis].set(radius)
    for variable in panel.cable_vars.values():
        variable.set('1.5')
    for variable in panel.groove_height_vars.values():
        variable.set('3')
    panel._redraw_preview()
    inner_layers = build_layer_configs(panel._build_cfg())
    assert [(cfg.estimated_wire_inner_radius*1000, cfg.estimated_wire_outer_radius*1000) for cfg in inner_layers] == pytest.approx(
        np.array([[26.5, 32.5], [33.5, 39.5], [40.5, 46.5]]))
    panel.groove_height_vars['y'].set('4')
    panel._redraw_preview()
    assert [cfg.shell_outer_radius for cfg in panel._last_layers] == [.031, .038, .045]
    assert 'GX → GY 3.00 mm' in panel.preview_notice.cget('text')
    panel.outer_radius_vars['y'].set('40')
    panel._redraw_preview()
    assert panel._last_layers is None
    assert 'Adjacent mold walls overlap' in panel.preview_notice.cget('text')


def test_batch_run_dispatches_one_process_job_with_shared_config(app, monkeypatch, tmp_path):
    panel = app.batch_panel
    app._set_output_dir(str(tmp_path))
    captured = {}

    def run(kind, cfg, **kwargs):
        captured.update(kind=kind, cfg=cfg, kwargs=kwargs)
        return True

    monkeypatch.setattr(panel.runner, 'run_job', run)
    panel._on_run()
    assert captured['kind'] == 'batch'
    assert captured['cfg'].output_dir == str(tmp_path)
    assert captured['cfg'].include_keys
    assert captured['kwargs']['ask_user'] == panel._ask_user
    assert captured['kwargs']['on_progress'] == panel._on_progress
    assert captured['kwargs']['extra']['question_language'] == app.language_var.get()
    panel._on_progress('batch', 1, 'complete', {'axis': 'z'})
    assert panel.progress['value'] == pytest.approx(30)
    assert 'GZ' in panel.phase_var.get()


@pytest.mark.parametrize('changed_parameter', ['b0', 'material', 'resistivity'])
def test_final_key_preview_is_used_only_for_the_parameters_that_generated_it(app, monkeypatch, changed_parameter):
    from halbach_coils.coilgen import assembly

    panel = app.batch_panel
    panel._running_signature = panel._preview_signature()
    panel._actual_interfaces = [
        {'inner_axis': 'z', 'outer_axis': 'x', 'angle_deg': 90},
        {'inner_axis': 'x', 'outer_axis': 'y', 'angle_deg': 150},
    ]
    actual = assembly.key_pair_meshes
    angles = []

    def meshes(batch, inner, outer, angle):
        angles.append(angle)
        return actual(batch, inner, outer, angle)

    monkeypatch.setattr(assembly, 'key_pair_meshes', meshes)
    panel._redraw_preview()
    assert angles == [90, 150]
    assert 'Final key positions' in panel.preview_notice.cget('text')
    angles.clear()
    if changed_parameter == 'b0':
        app.b0_var.set('-z')
    elif changed_parameter == 'material':
        panel.material_var.set('Al')
        panel._on_material_changed()
        panel._redraw_preview()
    else:
        panel.resistivity_var.set('2.1e-8')
        panel._redraw_preview()
    assert angles == list(assembly.PREFERRED_ANGLES)
    assert 'Key positions are preliminary' in panel.preview_notice.cget('text')


def test_disabled_keys_do_not_block_design_with_inactive_values(app):
    panel = app.batch_panel
    panel.key_length_var.set('invalid')
    panel.keys_var.set(False)
    panel._redraw_preview()
    assert not panel._build_cfg().include_keys
    assert all(str(widget.cget('state')) == 'disabled' for widget in panel.key_dimensions.winfo_children())


def test_batch_marker_checkbox_controls_all_three_preview_marks(app):
    panel = app.batch_panel
    assert panel._build_cfg().include_b0_markers is True
    panel._redraw_preview()
    patches = [patch for patch in panel.radial_ax.patches if (patch.get_gid() or '').startswith('b0-marker-')]
    assert {patch.get_gid() for patch in patches} == {'b0-marker-x', 'b0-marker-y', 'b0-marker-z'}
    for patch in patches:
        center = np.mean(patch.get_xy()[:4], axis=0)
        assert center[0] == pytest.approx(0, abs=1e-10)
        assert center[1] > 0
    signature = panel._preview_signature()
    panel.b0_markers_var.set(False)
    panel._redraw_preview()
    assert panel._preview_signature() != signature
    assert panel._build_cfg().include_b0_markers is False
    assert not any((patch.get_gid() or '').startswith('b0-marker-') for patch in panel.radial_ax.patches)


def test_final_batch_marker_preview_uses_common_selected_side(app):
    panel = app.batch_panel
    panel._running_signature = panel._preview_signature()
    panel._actual_b0_markers = {'enabled': True, 'radial_direction': [0, -1, 0]}
    panel._redraw_preview()
    patches = [patch for patch in panel.radial_ax.patches if (patch.get_gid() or '').startswith('b0-marker-')]
    assert len(patches) == 3
    assert all(np.mean(patch.get_xy()[:4], axis=0)[1] < 0 for patch in patches)
    app.b0_var.set('+x')
    panel._redraw_preview()
    patches = [patch for patch in panel.radial_ax.patches if (patch.get_gid() or '').startswith('b0-marker-')]
    assert all(np.mean(patch.get_xy()[:4], axis=0)[0] > 0 for patch in patches)


def test_per_gradient_roi_and_spherical_checkbox(app):
    from halbach_coils.coilgen.batch import build_layer_configs

    panel = app.batch_panel
    for axis, radius in zip('xyz', ('50', '38', '65')):
        panel.outer_radius_vars[axis].set(radius)
    for axis, values in {'x': ('10', '11', '12'), 'y': ('13', '14', '15'),
                         'z': ('16', '17', '18')}.items():
        for dim, value in zip('xyz', values):
            panel.roi_vars[axis][dim].set(value)
    panel.roi_spherical_vars['y'].set(True)
    panel._update_roi_entries()
    panel.roi_vars['y']['y'].set('')
    assert str(panel.roi_entries['y']['y'].cget('state')) == 'disabled'
    layers = build_layer_configs(panel._build_cfg())
    assert [(c.gradient_axis, c.target.rx, c.target.ry, c.target.rz) for c in layers] == [
        ('y', .013, .013, .013), ('x', .01, .011, .012), ('z', .016, .017, .018)]
    panel.roi_spherical_vars['y'].set(False)
    panel._update_roi_entries()
    assert str(panel.roi_entries['y']['y'].cget('state')) == 'normal'
    assert panel._missing_main_values()


def test_preview_accepts_different_spherical_rois(app):
    from halbach_coils.coilgen.batch import build_layer_configs

    panel = app.batch_panel
    for axis in 'xyz':
        panel.roi_spherical_vars[axis].set(True)
    panel.roi_vars['x']['x'].set('30')
    gy = build_layer_configs(panel._build_cfg())[-1]
    gy_roi_mm = gy.shell_inner_radius * 1000 - 1.5
    assert gy.estimated_wire_inner_radius * 1000 < gy_roi_mm
    panel.roi_vars['y']['x'].set(str(gy_roi_mm))
    panel._redraw_preview()
    assert panel._last_layers is not None
    assert 'must share' not in panel.preview_notice.cget('text')
    assert {cfg.gradient_axis: cfg.target.rx for cfg in panel._last_layers} == pytest.approx({
        'x': .03, 'y': gy_roi_mm / 1000, 'z': .02})


def test_roi_visibility_controls_preview_without_changing_design(app):
    panel = app.batch_panel
    panel._redraw_preview()
    def roi_ids():
        return {item.get_gid() for item in panel.ax3d.collections
                if (item.get_gid() or '').startswith('roi-')}
    assert roi_ids() == {'roi-x', 'roi-y', 'roi-z'}
    signature = panel._preview_signature()
    panel.roi_visible_vars['x'].set(False)
    panel._redraw_preview()
    assert roi_ids() == {'roi-y', 'roi-z'}
    assert panel._preview_signature() == signature
    panel.roi_visible_vars['x'].set(True)
    panel._redraw_preview()
    assert roi_ids() == {'roi-x', 'roi-y', 'roi-z'}
