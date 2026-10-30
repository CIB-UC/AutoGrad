"""Reusable explicit form inputs for GUI tests that exercise valid designs."""

import pytest


@pytest.fixture
def fill_gui_design():
    def fill(app):
        from coilgen.config import Config
        cfg = Config(show_plots=False)
        cfg.cylinder.radius, cfg.cylinder.height = .039, .17
        cfg.target.rx = cfg.target.ry = cfg.target.rz = .02
        cfg.shell.b0_marker = True
        app.pipeline_panel.apply_config(cfg)
        batch = app.batch_panel
        for name, value in {'height_var':'170', 'anchor_radius_var':'26.5',
                            'radial_gap_var':'.3', 'a_var':'2', 'b_var':'1',
                            'key_length_var':'4', 'key_width_var':'4',
                            'fit_clearance_var':'.3'}.items():
            getattr(batch, name).set(value)
        batch.material_var.set('Cu')
        batch._on_material_changed()
        for var in batch.roi_vars.values():
            var.set('20')
        for group, value in ((batch.cable_vars,'2'), (batch.layer_gap_vars,'0'),
                             (batch.tikhonov_vars,'2500'), (batch.levels_vars,'12')):
            for var in group.values():
                var.set(value)
        sweep = app.sweep_panel
        for name, value in {'radius_var':'39', 'height_var':'170', 'roi_var':'20',
                            'levels_var':'12', 'tk_min_var':'1', 'tk_max_var':'1000000',
                            'n_coarse_var':'12', 'processes_var':'1'}.items():
            getattr(sweep, name).set(value)
        sweep.material_var.set('Cu')
        sweep._on_material_changed()
        app.update()
    return fill
