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
    panel.order_var.set('Y, X, Z')
    panel.anchor_radius_var.set('33')
    panel.height_var.set('200')
    panel.radial_gap_var.set('4.5')
    panel.key_length_var.set('6')
    panel.key_width_var.set('5')
    panel.fit_clearance_var.set('0.2')
    for axis, factor, levels in zip('xyz', [1000, 2000, 3000], [8, 10, 12]):
        panel.tikhonov_vars[axis].set(str(factor))
        panel.levels_vars[axis].set(str(levels))
    for axis, diameter, gap in zip('xyz', ['1.5', '2', '2.5'], ['0.25', '0.5', '0.75']):
        panel.cable_vars[axis].set(diameter)
        panel.layer_gap_vars[axis].set(gap)
    panel.coilgen_advanced.variables['cylinder.n_circ'].set('64')
    batch = panel._build_cfg()
    assert batch.anchor_radius == .033
    assert batch.radial_gap == .0045
    assert batch.conductor_widths == (.0015, .002, .0025)
    assert batch.layer_gaps == (.00025, .0005, .00075)
    assert batch.base.cylinder.height == .2
    assert (batch.key_length, batch.key_width, batch.fit_clearance) == (.006, .005, .0002)
    assert batch.tikhonov_factors == (1000, 2000, 3000)
    assert batch.num_levels == (8, 10, 12)
    layers = build_layer_configs(batch)
    assert [(cfg.gradient_axis, cfg.tikhonov_factor, cfg.num_levels) for cfg in layers] == [
        ('y', 2000, 10), ('x', 1000, 8), ('z', 3000, 12)]
    assert all(cfg.cylinder.n_circ == 64 for cfg in layers)
    assert [cfg.shell_wall_thickness for cfg in layers] == pytest.approx([.0045, .00325, .00575])
    assert [cfg.groove_radial_height for cfg in layers] == [.004, .003, .005]


def test_one_inner_or_outer_anchor_keeps_same_complete_gradient_dimensions(app):
    from halbach_coils.coilgen.batch import build_layer_configs

    panel = app.batch_panel
    panel.anchor_radius_var.set('26.5')
    panel.radial_gap_var.set('1')
    for variable in panel.cable_vars.values():
        variable.set('1.5')
    panel._redraw_preview()
    inner_layers = build_layer_configs(panel._build_cfg())
    assert [(cfg.estimated_wire_inner_radius*1000, cfg.estimated_wire_outer_radius*1000) for cfg in inner_layers] == pytest.approx(
        np.array([[26.5, 32.5], [33.5, 39.5], [40.5, 46.5]]))
    # Switching references preserves the same assembly before another edit.
    panel.radius_mode_var.set('outer')
    assert float(panel.anchor_radius_var.get()) == pytest.approx(46.5)
    batch = panel._build_cfg()
    assert batch.radius_mode == 'outer'
    assert batch.anchor_radius == .0465
    layers = build_layer_configs(batch)
    np.testing.assert_allclose([(cfg.shell_inner_radius, cfg.shell_outer_radius) for cfg in layers],
                               [(cfg.shell_inner_radius, cfg.shell_outer_radius) for cfg in inner_layers])
    assert 'gradient' in panel.radius_labels['z'].cget('text').lower()


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
