"""Expected geometry failures remain useful, selectable GUI outcomes."""

from types import SimpleNamespace as NS

import pytest

from halbach_coils.gui.jobs import result_job_status
from halbach_coils.run_pipeline import PipelineResult


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
    root.withdraw(); root.update()
    fill_gui_design(root)
    yield root
    root.destroy()


def row(status='valid'):
    return dict(Fase='Grueso', Tikhonov=10000., Pendiente_mT_per_m_per_A=2.,
                Error_Medio_pct=1., RMSE_per_range_mT_per_m_per_A=.01,
                Wire_length_m=10., Geometry_status=status)


def test_sweep_displays_geometry_and_does_not_apply_a_failed_or_legacy_row(app, monkeypatch):
    from halbach_coils.gui import sweep_panel
    from halbach_coils.coilgen.config import Config
    warnings, applied = [], []
    monkeypatch.setattr(sweep_panel.messagebox, 'showwarning', lambda *a, **kw: warnings.append(a))
    monkeypatch.setattr(app.pipeline_panel, 'apply_config', lambda cfg: applied.append(cfg))
    panel = app.sweep_panel; panel._last_sweep_cfg = Config()
    for status in ('interference', 'unchecked', 'failed', 'valid'):
        panel._insert_result_row(row(status))
        item = panel.tree.get_children()[-1]; panel.tree.selection_set(item)
        assert panel.tree.set(item, 'geometry')
        panel._use_selected()
    assert len(warnings) == 3 and len(applied) == 1
    app.localizer.set_language('es'); app._refresh_language()
    assert panel.tree.set(item, 'geometry') == 'Cable sin interferencias'


def test_sweep_with_no_valid_winding_uses_a_warning_and_keeps_the_table(app, monkeypatch, tmp_path):
    from halbach_coils.gui import sweep_panel
    from halbach_coils.coilgen.sweep import SweepResult
    app._set_output_dir(str(tmp_path)); panel = app.sweep_panel
    warnings = []
    monkeypatch.setattr(sweep_panel.messagebox, 'showwarning', lambda *a, **kw: warnings.append(a))
    monkeypatch.setattr(sweep_panel.messagebox, 'showerror', lambda *a, **kw: pytest.fail('Expected geometry is not a crash'))
    def run(kind, cfg, **kwargs):
        kwargs['on_progress']('Grueso', 1, 'done', row('interference'))
        kwargs['on_done'](SweepResult(axis='x', rows=[row('interference')], csv_path='results.csv'), None)
    monkeypatch.setattr(panel.runner, 'run_job', run)
    panel._on_run()
    assert warnings and panel.tree.get_children()


def test_pipeline_needing_revision_shows_a_warning_and_job_stays_partial(app, monkeypatch, tmp_path):
    from halbach_coils.gui import pipeline_panel
    app._set_output_dir(str(tmp_path)); panel = app.pipeline_panel
    warnings = []
    monkeypatch.setattr(pipeline_panel.messagebox, 'showwarning', lambda *a, **kw: warnings.append(a))
    monkeypatch.setattr(pipeline_panel.messagebox, 'showerror', lambda *a, **kw: pytest.fail('Expected geometry is not a crash'))
    result = PipelineResult(str(tmp_path), needs_revision=True, message='Turns require more space.')
    monkeypatch.setattr(panel.runner, 'run_job', lambda kind, cfg, **kw: kw['on_done'](result, None))
    panel._on_run()
    assert warnings
    assert result_job_status('pipeline', result) == 'partial'
    assert result_job_status('sweep', NS(best_error=None)) == 'partial'
