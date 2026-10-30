"""Editable defaults and cleared fields keep the interface usable."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'halbach_coils'))


@pytest.fixture
def app():
    from halbach_coils.gui.main_window import CoilGenApp
    root = CoilGenApp()
    root.withdraw()
    root.update()
    yield root
    root.destroy()


def test_default_designs_are_valid_and_cleared_fields_are_neutral(app):
    pipeline, batch, sweep = app.pipeline_panel, app.batch_panel, app.sweep_panel
    assert pipeline.radius_var.get() == '50' and pipeline.height_var.get() == '200'
    assert pipeline._build_cfg().target.rx == .02
    assert batch._build_cfg().anchor_radius == .05
    assert sweep.radius_var.get() == '50' and sweep.height_var.get() == '200'
    assert sweep.tk_min_var.get() == '1000' and sweep.tk_max_var.get() == '100000'
    assert pipeline.coilgen_advanced.variables['cylinder.n_circ'].get() == '40'
    pipeline.radius_var.set('')
    batch.anchor_radius_var.set('')
    batch._redraw_preview()
    assert str(batch.preview_notice.cget('foreground')) == '#666666'
    assert 'Enter the design values' in batch.preview_notice.cget('text')
    assert any('Enter the design values' in item.get_text() for item in pipeline.cyl_ax.texts)
    with pytest.raises(ValueError, match='Complete the required'):
        pipeline._build_cfg()
    with pytest.raises(ValueError, match='Complete the required'):
        batch._build_cfg()


def test_completing_inputs_reactivates_pipeline_and_batch_previews(app):
    pipeline = app.pipeline_panel
    values = {'radius_var':'39', 'height_var':'170', 'roi_var':'20',
              'tikhonov_var':'2500', 'levels_var':'12', 'cw_var':'2',
              'a_var':'4', 'b_var':'2', 'n_var':'16', 'margin_var':'50', 'layer_gap_var':'0'}
    pipeline.material_var.set('Cu')
    pipeline._on_material_changed()
    for name, value in values.items():
        getattr(pipeline, name).set(value)
    pipeline._redraw_previews()
    assert pipeline._build_cfg().cylinder.height == .17
    assert not any('Enter the design values' in item.get_text() for item in pipeline.cyl_ax.texts)
    batch = app.batch_panel
    for name, value in {'height_var':'170', 'anchor_radius_var':'55', 'radial_gap_var':'.3',
                        'a_var':'2', 'b_var':'1', 'key_length_var':'4', 'key_width_var':'4',
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
    batch._redraw_preview()
    assert batch._build_cfg().anchor_radius == .055
    assert batch._last_layers is not None
    assert 'Enter the design values' not in batch.preview_notice.cget('text')
