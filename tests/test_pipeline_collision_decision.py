from halbach_coils.coilgen.config import Config
from halbach_coils.coilgen.overlap import CollisionSite, OverlapReport
from halbach_coils import run_pipeline as pipeline_module
import pytest


def _collision_report():
    return OverlapReport(sites=[CollisionSite(
        part_index=0,
        location_uv=(0.0, 0.0),
        cable_count=3,
        crossing_count=3,
        segment_indices=(10, 100, 200),
    )])


def test_rejecting_collision_result_stops_before_leads_and_shell(tmp_path, monkeypatch):
    cfg = Config(show_plots=False)
    cfg.output_dir = str(tmp_path)
    calls = []
    questions = []

    monkeypatch.setattr(
        pipeline_module, 'run_gradient',
        lambda *args, **kwargs: (object(), {}, _collision_report()),
    )
    monkeypatch.setattr(pipeline_module, 'run_leads',
                        lambda *args, **kwargs: calls.append('leads'))
    monkeypatch.setattr(pipeline_module, 'run_shell',
                        lambda *args, **kwargs: calls.append('shell'))

    def reject(question):
        questions.append(question)
        return False

    result = pipeline_module.run_pipeline(cfg, ask_user=reject)

    assert result.discarded is True
    assert calls == []
    assert len(questions) == 1
    assert "3 cables are trying to pass through the same location" in questions[0]


def test_accepting_collision_result_continues_with_leads_and_shell(tmp_path, monkeypatch):
    cfg = Config(show_plots=False)
    cfg.output_dir = str(tmp_path)
    calls = []

    monkeypatch.setattr(
        pipeline_module, 'run_gradient',
        lambda *args, **kwargs: (object(), {}, _collision_report()),
    )
    monkeypatch.setattr(pipeline_module, '_ensure_wire_exists',
                        lambda *args, **kwargs: str(tmp_path / 'wire.stl'))
    monkeypatch.setattr(pipeline_module, 'run_leads',
                        lambda *args, **kwargs: calls.append('leads'))
    monkeypatch.setattr(pipeline_module, 'run_shell',
                        lambda *args, **kwargs: calls.append('shell'))

    result = pipeline_module.run_pipeline(cfg, ask_user=lambda _question: True)

    assert result.discarded is False
    assert calls == ['leads', 'shell']


@pytest.mark.parametrize('language,description', [
    ('en', 'stopped before leads and shell'),
    ('es', 'se detuvo antes de los terminales y el molde'),
])
def test_measured_interference_stops_before_an_unfulfillable_continue_prompt(
        tmp_path, monkeypatch, language, description):
    cfg = Config(show_plots=False, output_language=language)
    cfg.output_dir = str(tmp_path)
    report = OverlapReport(sites=[CollisionSite(
        part_index=0, location_uv=(0., 0.), cable_count=2,
        crossing_count=1, segment_indices=(10, 100),
        minimum_distance_m=.0015, required_separation_m=.002)])
    calls = []
    monkeypatch.setattr(pipeline_module, 'run_gradient',
                        lambda *a, **kw: (object(), {}, report))
    monkeypatch.setattr(pipeline_module, 'run_leads',
                        lambda *a, **kw: calls.append('leads'))
    monkeypatch.setattr(pipeline_module, 'run_shell',
                        lambda *a, **kw: calls.append('shell'))

    result = pipeline_module.run_pipeline(
        cfg, ask_user=lambda _: calls.append('question') or True,
        question_language=language)
    assert result.needs_revision
    assert description in result.message
    assert result.metrics_path is None
    from halbach_coils.coilgen.output_layout import name
    summary = (tmp_path / name('summary', language)).read_text(encoding='utf-8')
    assert ('Incomplete run' if language == 'en' else 'Ejecución incompleta') in summary
    assert calls == []
    assert '1.5 mm' in report.user_question(language)
    assert '2 mm' in report.user_question(language)


def test_terminal_geometry_rejection_returns_diagnostics_instead_of_a_worker_error(tmp_path, monkeypatch):
    cfg = Config(show_plots=False); cfg.output_dir = str(tmp_path)
    monkeypatch.setattr(pipeline_module, 'run_gradient', lambda *a, **kw: (object(), {}, OverlapReport()))
    monkeypatch.setattr(pipeline_module, '_ensure_wire_exists', lambda *a, **kw: str(tmp_path/'wire.stl'))
    def leads(*a, **kw):
        raise pipeline_module.GeometryRejected('No terminal route with sufficient clearance.')
    monkeypatch.setattr(pipeline_module, 'run_leads', leads)
    monkeypatch.setattr(pipeline_module, 'run_shell', lambda *a, **kw: pytest.fail('Invalid leads cannot be carved'))
    result = pipeline_module.run_pipeline(cfg)
    assert result.needs_revision and 'No terminal route' in result.message
    assert result.metrics_path is None
