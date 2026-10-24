"""Output language changes presentation, never wire provenance or physics."""

import hashlib
import json
from pathlib import Path

import pytest

from halbach_coils.coilgen.config import Config
from halbach_coils.coilgen import paths, sweep
from halbach_coils.coilgen.batch import BatchConfig, run_batch, _write_report
from halbach_coils.coilgen.design_state import save_design_state, validate_design_state
from halbach_coils.coilgen.output_layout import name, locate, language_for
from halbach_coils.coilgen.output_layout import prepare_run_directory
from halbach_coils.coilgen.outputs import organize_outputs, write_result_summary
from halbach_coils.coilgen.presets import config_to_preset
from halbach_coils.gui.jobs import job_output_dir, write_job_status
from halbach_coils.run_pipeline import PipelineResult


@pytest.mark.parametrize('language', ['en', 'es'])
def test_language_layout_preserves_hashes_reuse_and_existing_run_names(tmp_path, language):
    cfg = Config(output_language=language)
    stem = 'Gradient_Gx_tk2500_lvl26'
    wire = tmp_path / (stem + '_wire_0.stl')
    wire.write_bytes(b'unchanged wire')
    save_design_state(wire, cfg)
    digest = hashlib.sha256(wire.read_bytes()).hexdigest()
    (tmp_path / (stem + '_shell_0.stl')).write_bytes(b'mold')
    (tmp_path / (stem + '_field_comparison.png')).write_bytes(b'plot')
    (tmp_path / (stem + '_geometry.json')).write_text(json.dumps(
        {'status': 'clear', 'parts': [{'max_displacement_mm': .2}]}))
    paths.write_active_stem(str(tmp_path), stem)
    organize_outputs(tmp_path, language=language)
    moved = tmp_path / name('coil', language) / wire.name
    assert hashlib.sha256(moved.read_bytes()).hexdigest() == digest
    cfg.output_language = 'es' if language == 'en' else 'en'
    validate_design_state(moved, cfg)
    assert paths.resolve_wire_stl_path(str(tmp_path), 'x', 2500, 26) == str(moved)
    assert paths.unique_stem(str(tmp_path), stem) == stem + '(2)'
    assert paths.unique_path(str(tmp_path / (stem + '_shell_0.stl'))).endswith('(2).stl')
    assert organize_outputs(tmp_path, language=cfg.output_language) == {}
    assert language_for(tmp_path) == language
    write_result_summary(tmp_path, language=cfg.output_language)
    summary = (tmp_path / name('summary', language)).read_text(encoding='utf-8')
    assert ('Winding geometry' if language == 'en' else 'Geometría del bobinado') in summary
    assert locate(tmp_path, 'mold') == tmp_path / name('mold', language)
    assert 'output_language' not in config_to_preset(cfg)['config']


@pytest.mark.parametrize('language', ['en', 'es'])
def test_batch_language_and_cancelled_manifest_stay_consistent(tmp_path, monkeypatch, language):
    cfg = Config(output_language=language)
    cfg.cylinder.height = .17
    cfg.target.rx = cfg.target.ry = cfg.target.rz = .015
    batch = BatchConfig(base=cfg, anchor_radius=.035, output_dir=str(tmp_path))
    def pipeline(layer, **kwargs):
        folder = Path(layer.output_dir)
        (folder / name('mold', layer.output_language)).mkdir(parents=True)
        (folder / name('mold', layer.output_language) / 'mold.stl').touch()
        metrics = folder / 'metrics.json'
        metrics.write_text('{}')
        assert layer.output_language == language
        return PipelineResult(str(folder), metrics_path=str(metrics))
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', pipeline)
    result = run_batch(batch, finalize=lambda *_: {'verified': True})
    assert result.completed
    assert Path(result.manifest_path).name == name('batch_manifest', language)
    assert Path(result.summary_path).name == name('batch_summary', language)
    document = json.loads(Path(result.manifest_path).read_text(encoding='utf-8'))
    document['status'] = 'running'
    document['layers'][0]['status'] = 'running'
    _write_report(tmp_path, document)
    write_job_status(str(tmp_path), 'cancelled', kind='batch')
    saved = json.loads(Path(result.manifest_path).read_text(encoding='utf-8'))
    assert saved['status'] == saved['layers'][0]['status'] == 'cancelled'
    summary = Path(result.summary_path).read_text(encoding='utf-8')
    assert ('The assembly is incomplete' if language == 'en' else 'El conjunto está incompleto') in summary


@pytest.mark.parametrize('language', ['en', 'es'])
def test_sweep_marker_and_summary_use_the_same_language(tmp_path, monkeypatch, language):
    cfg = Config(output_language=language)
    def phase(_cfg, values, folder, phase_name, processes, progress):
        assert _cfg.output_language == language
        return [{'Fase': phase_name, 'Tikhonov': value,
                 'Pendiente_mT_per_m_per_A': 2., 'Error_Medio_pct': 1.,
                 'RMSE_per_range_mT_per_m_per_A': .1, 'Geometry_status': 'valid', 'Wire_length_m': 1.}
                for value in values]
    monkeypatch.setattr(sweep, '_run_phase', phase)
    result = sweep.run_tikhonov_sweep(cfg, tk_min=1, tk_max=10, n_coarse=2,
                                    fine=False, output_base_dir=str(tmp_path))
    import csv
    from halbach_coils.gui.sweep_panel import SweepPanel
    with open(result.csv_path, encoding='utf-8', newline='') as stream:
        exported = list(csv.DictReader(stream))
    assert ('Phase' if language == 'en' else 'Fase') in exported[0]
    parsed = SweepPanel._parse_csv_row(exported[0])
    assert parsed['Pendiente_mT_per_m_per_A'] == 2.
    marker = job_output_dir('sweep', cfg, {'output_base_dir': str(tmp_path)})
    assert Path(result.csv_path).parent == Path(marker)
    assert Path(marker).name == name('axis', language) + '_' + cfg.axis_label
    assert ('Sweep_summary_Axis' if language == 'en' else 'Resumen_Completo_Eje') in Path(result.txt_path).name
    assert ('Tikhonov sweep summary' if language == 'en' else 'Resumen Barrido') in Path(result.txt_path).read_text(encoding='utf-8')


def test_english_is_the_default_and_invalid_languages_are_rejected():
    assert Config().output_language == 'en'
    with pytest.raises(ValueError, match='language'):
        Config(output_language='invalid')


@pytest.mark.parametrize('language', ['en', 'es'])
def test_new_design_in_another_language_does_not_mix_old_outputs(tmp_path, language):
    previous_language = 'es' if language == 'en' else 'en'
    old = tmp_path / name('coil', previous_language)
    old.mkdir()
    original = old / 'previous_wire_0.stl'
    original.write_bytes(b'keep previous geometry')
    cfg = Config(output_language=language, output_dir=str(tmp_path))
    prepare_run_directory(cfg)
    assert Path(cfg.output_dir) == tmp_path / name('results', language)
    assert original.read_bytes() == b'keep previous geometry'
    cfg.output_dir = str(tmp_path)
    cfg.control.run_gradient = False
    prepare_run_directory(cfg)
    assert cfg.output_dir == str(tmp_path)
