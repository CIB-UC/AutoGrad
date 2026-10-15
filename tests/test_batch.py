"""Concentric spacing and partial batch outcomes, without three costly solves."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from halbach_coils.coilgen.batch import BatchConfig, build_layer_configs, run_batch
from halbach_coils.coilgen.config import Config, preset_for
from halbach_coils.run_pipeline import PipelineResult
from halbach_coils.coilgen import batch as batch_module


def _batch(tmp_path=None, **changes):
    base = Config()
    base.target.rx = base.target.ry = base.target.rz = .02
    base.cylinder.height = .17
    batch = BatchConfig(base=base, anchor_radius=.035, output_dir=str(tmp_path) if tmp_path else '',
                        include_keys=False)
    for key, value in changes.items():
        setattr(batch, key, value)
    return batch


def _run_batch(batch, **kwargs):
    kwargs.setdefault('finalize', lambda *args: {'verified': True})
    return run_batch(batch, **kwargs)


def test_anchor_and_safe_default_gap_protect_wire_envelopes_and_preserve_base():
    batch = _batch(tikhonov_factors=(20000, 10000, 30000), num_levels=(12, 14, 16))
    original = deepcopy(batch.base)
    z, x, y = build_layer_configs(batch)
    assert (z.gradient_axis, x.gradient_axis, y.gradient_axis) == ('z', 'x', 'y')
    # Default 4 mm wall and 2 mm protrusion per face: the shells themselves
    # need 4.3 mm clearance to leave 0.3 mm between conductors.
    assert z.shell_inner_radius == pytest.approx(.035)
    assert z.shell_outer_radius == pytest.approx(.039)
    assert z.estimated_wire_inner_radius == pytest.approx(.033)
    assert x.shell_inner_radius - z.shell_outer_radius == pytest.approx(.0043)
    for inner, outer in ((z, x), (x, y)):
        assert outer.estimated_wire_inner_radius - inner.estimated_wire_outer_radius == pytest.approx(.0003)
    assert [cfg.tikhonov_factor for cfg in (z, x, y)] == [30000, 20000, 10000]
    assert [cfg.num_levels for cfg in (z, x, y)] == [16, 12, 14]
    for cfg in (z, x, y):
        assert cfg.b0_direction == batch.base.b0_direction
        np.testing.assert_allclose(cfg.leads.preset.sector_ref_dir,
                                   preset_for(cfg.gradient_axis).sector_ref_dir)
    x.target.rx = .001
    assert z.target.rx == y.target.rx == batch.base.target.rx == original.target.rx
    assert batch.base.cylinder.radius == original.cylinder.radius
    assert batch.base.gradient_axis == original.gradient_axis


def test_outer_anchor_preserves_total_radius_with_individual_wall_thicknesses():
    batch = _batch(radius_mode='outer', anchor_radius=.055,
                   conductor_widths=(.0015, .0025, .002),
                   layer_gaps=(.0002, .0004, .0001))
    z, x, y = build_layer_configs(batch)
    assert [cfg.shell_wall_thickness for cfg in (z, x, y)] == pytest.approx([.0041, .0032, .0054])
    assert y.shell_outer_radius == pytest.approx(.055)
    assert z.shell_inner_radius == pytest.approx(.0337)
    for inner, outer in ((z, x), (x, y)):
        assert outer.shell_inner_radius - inner.shell_outer_radius == pytest.approx(batch.radial_gap)
    equivalent_inner = deepcopy(batch)
    equivalent_inner.radius_mode = 'inner'
    equivalent_inner.anchor_radius = z.shell_inner_radius
    from_inner = build_layer_configs(equivalent_inner)
    assert [cfg.shell_outer_radius for cfg in from_inner] == pytest.approx(
        [cfg.shell_outer_radius for cfg in (z, x, y)])
    assert [cfg.wire.conductor_width for cfg in from_inner] == [.002, .0015, .0025]
    assert [cfg.winding.layer_gap_mm for cfg in from_inner] == [.0001, .0002, .0004]
    batch.anchor_radius = .03
    with pytest.raises(ValueError, match='ROI must fit'):
        build_layer_configs(batch)


def test_nondefault_crossing_shift_uses_actual_derived_wire_envelopes():
    batch = _batch()
    batch.base.winding.normal_shift = -.006
    batch.radial_gap = .0063
    configs = build_layer_configs(batch)
    assert configs[0].estimated_wire_inner_radius == pytest.approx(.031)
    for inner, outer in zip(configs, configs[1:]):
        assert outer.estimated_wire_inner_radius - inner.estimated_wire_outer_radius == pytest.approx(.0003)
        assert outer.shell_inner_radius - inner.shell_outer_radius == pytest.approx(.0063)


def test_reference_shell_dimensions_follow_wire_wall_formula():
    batch = _batch(anchor_radius=.0265, radial_gap=.001,
                   conductor_widths=(.0015, .0015, .0015), layer_gaps=(0, 0, 0))
    configs = build_layer_configs(batch)
    # Measured Fusion examples: Z inside, then X, then Y. Their close radial
    # envelopes are accepted here and must pass the actual assembly CAD check.
    assert [cfg.shell_inner_radius for cfg in configs] == pytest.approx([.0265, .0305, .0345])
    assert [cfg.shell_outer_radius for cfg in configs] == pytest.approx([.0295, .0335, .0375])
    assert configs[1].estimated_wire_inner_radius < configs[0].estimated_wire_outer_radius


@pytest.mark.parametrize('field,value,match', [
    ('anchor_radius', -1, 'Anchor radius'),
    ('radius_mode', 'manual', 'Radius mode'),
    ('radial_gap', float('nan'), 'shell gap'),
    ('axis_order', ('z', 'z', 'x'), 'exactly once'),
    ('tikhonov_factors', (1, 2, float('inf')), 'Tikhonov'),
    ('num_levels', (1, 12, 16), 'level count'),
    ('conductor_widths', (.002, 0, .002), 'Wire diameter'),
    ('layer_gaps', (0, 0), 'three wire diameters'),
    ('key_length', float('nan'), 'Key axial length'),
    ('fit_clearance', .004, 'smaller than'),
])
def test_invalid_batch_dimensions_fail_before_outputs(tmp_path, field, value, match):
    batch = _batch(tmp_path)
    setattr(batch, field, value)
    with pytest.raises(ValueError, match=match):
        _run_batch(batch)
    assert not (tmp_path / 'lote.json').exists()


def test_custom_shell_and_non_longitudinal_bore_rejected():
    batch = _batch()
    batch.base.shell.use_custom_stl = True
    with pytest.raises(ValueError, match='custom STL'):
        build_layer_configs(batch)
    batch.base.shell.use_custom_stl = False
    batch.base.cylinder.rot_angle = np.pi / 2
    with pytest.raises(ValueError, match=r'longitudinal \+Z'):
        build_layer_configs(batch)


def _fake_pipeline(calls, *, fail_axis=None, discard_axis=None, stop_axis=None, state=None):
    def run(cfg, **kwargs):
        calls.append(cfg.gradient_axis)
        root = Path(cfg.output_dir)
        (root / 'Molde').mkdir(parents=True)
        (root / 'Molde' / f'{cfg.axis_label}_shell_0.stl').write_bytes(b'validated by pipeline')
        metrics = root / 'Leads' / 'final_metrics.json'
        metrics.parent.mkdir()
        metrics.write_text('{}', encoding='utf-8')
        if cfg.gradient_axis == fail_axis:
            raise RuntimeError('the leads route failed')
        if cfg.gradient_axis == stop_axis:
            state['stop'] = True
        return PipelineResult(str(root), discarded=(cfg.gradient_axis == discard_axis),
                              field_plots={'plot': str(root / 'field.png')}, metrics_path=str(metrics))
    return run


def test_all_axes_finish_before_single_assembly_finalizer(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', _fake_pipeline(calls))
    batch = _batch(tmp_path, include_keys=True)
    def finalize(batch_cfg, configs, results):
        assert calls == ['z', 'x', 'y']
        assert len(configs) == len(results) == 3
        assert Path(batch_cfg.output_dir) == tmp_path
        calls.append('assembly')
        return {'report': 'Ensamble/ensamble.json'}
    result = _run_batch(batch, finalize=finalize)
    assert result.completed
    assert calls == ['z', 'x', 'y', 'assembly']
    assert result.assembly == {'report': 'Ensamble/ensamble.json'}
    document = json.loads(Path(result.manifest_path).read_text(encoding='utf-8'))
    assert document['status'] == 'complete'
    assert all(layer['status'] == 'complete' for layer in document['layers'])
    assert 'Estado: complete' in Path(result.summary_path).read_text(encoding='utf-8')
    # Source config can be reused and still points to its original output dir.
    assert batch.base.output_dir == ''


def test_assembly_verification_still_runs_when_keys_are_disabled(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', _fake_pipeline(calls))
    def finalize(batch, configs, results):
        assert not batch.include_keys
        calls.append('verify_without_keys')
        return {'verified': True}
    result = _run_batch(_batch(tmp_path, include_keys=False), finalize=finalize)
    assert calls == ['z', 'x', 'y', 'verify_without_keys']
    assert result.completed


def test_second_axis_failure_preserves_first_and_never_runs_third_or_assembly(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline',
                        _fake_pipeline(calls, fail_axis='x'))
    def finalize(*args):
        pytest.fail('Assembly cannot run after a failed layer.')
    with pytest.raises(RuntimeError, match='leads route failed'):
        _run_batch(_batch(tmp_path, include_keys=True), finalize=finalize)
    assert calls == ['z', 'x']
    document = json.loads((tmp_path / 'lote.json').read_text(encoding='utf-8'))
    assert document['status'] == 'failed'
    assert [layer['status'] for layer in document['layers']] == ['complete', 'failed', 'pending']
    assert 'incompleto' in (tmp_path / 'Resumen_lote.txt').read_text(encoding='utf-8')


@pytest.mark.parametrize('mode', ['stop', 'discard'])
def test_early_pipeline_return_never_claims_complete(tmp_path, monkeypatch, mode):
    calls = []
    state = {'stop': False}
    options = {'stop_axis': 'z', 'state': state} if mode == 'stop' else {'discard_axis': 'z'}
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', _fake_pipeline(calls, **options))
    result = _run_batch(_batch(tmp_path), should_stop=lambda: state['stop'])
    assert not result.completed
    assert calls == ['z']
    document = json.loads(Path(result.manifest_path).read_text(encoding='utf-8'))
    assert document['status'] == ('cancelled' if mode == 'stop' else 'discarded')


def test_missing_final_outputs_and_finalizer_errors_are_incomplete(tmp_path, monkeypatch):
    def early_return(cfg, **kwargs):
        return PipelineResult(cfg.output_dir)
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', early_return)
    with pytest.raises(RuntimeError, match='completed shell'):
        _run_batch(_batch(tmp_path / 'no_shell'))
    calls = []
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', _fake_pipeline(calls))
    def finalize(*args):
        raise RuntimeError('the key crosses a groove')
    with pytest.raises(RuntimeError, match='crosses a groove'):
        _run_batch(_batch(tmp_path / 'bad_keys', include_keys=True), finalize=finalize)
    manifest = json.loads((tmp_path / 'bad_keys' / 'lote.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'failed'
    assert manifest['error'].startswith('Assembly:')


def test_output_folder_is_not_overwritten(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', _fake_pipeline(calls))
    _run_batch(_batch(tmp_path))
    before = (tmp_path / 'lote.json').read_bytes()
    with pytest.raises(FileExistsError, match='new folder'):
        _run_batch(_batch(tmp_path))
    assert (tmp_path / 'lote.json').read_bytes() == before
    assert calls == ['z', 'x', 'y']


def test_smaller_shell_gap_requires_actual_3d_verification(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', _fake_pipeline(calls))
    def verify(batch, configs, results):
        assert len(results) == 3
        raise RuntimeError('The actual outer lead interferes with the inner layer.')
    with pytest.raises(RuntimeError, match='actual outer lead interferes'):
        _run_batch(_batch(tmp_path, radial_gap=.001), finalize=verify)
    assert calls == ['z', 'x', 'y']
    document = json.loads((tmp_path / 'lote.json').read_text(encoding='utf-8'))
    assert document['requires_interference_check']
    assert document['status'] == 'failed'


def _report_document():
    return {'status': 'complete', 'layers': [], 'b0_direction': '+y',
            'radius_mode': 'inner', 'anchor_radius_m': .035,
            'shell_inner_radius_m': .035, 'shell_outer_radius_m': .0556,
            'wire_inner_radius_m': .033, 'radial_gap_m': .0043}


@pytest.mark.parametrize('winerror', [5, 32, 33])
def test_report_atomic_replace_recovers_from_brief_windows_lock(tmp_path, monkeypatch, winerror):
    native_replace = batch_module.os.replace
    calls, sleeps = [], []
    def replace(source, destination):
        calls.append((source, destination))
        if len(calls) <= 2:
            error = PermissionError('Temporary Windows file lock')
            error.winerror = winerror
            raise error
        native_replace(source, destination)
    # Replace this module's namespace, never global os.name/replace used by
    # pathlib, pytest, or other application modules in the same process.
    monkeypatch.setattr(batch_module, 'os', SimpleNamespace(name='nt', replace=replace))
    monkeypatch.setattr(batch_module, 'time', SimpleNamespace(sleep=sleeps.append))
    summary, manifest = batch_module._write_report(tmp_path, _report_document())
    assert len(calls) == 3
    assert sleeps == pytest.approx([.02, .04])
    assert json.loads(Path(manifest).read_text(encoding='utf-8')) == _report_document()
    assert Path(summary).is_file()
    assert not (tmp_path / 'lote.json.tmp').exists()


def test_report_persistent_windows_lock_propagates_after_six_attempts(tmp_path, monkeypatch):
    calls, sleeps = [], []
    error = PermissionError('Persistent Windows file lock')
    error.winerror = 5
    def replace(*args):
        calls.append(args)
        raise error
    original = b'{"status":"previous"}\n'
    (tmp_path / 'lote.json').write_bytes(original)
    monkeypatch.setattr(batch_module, 'os', SimpleNamespace(name='nt', replace=replace))
    monkeypatch.setattr(batch_module, 'time', SimpleNamespace(sleep=sleeps.append))
    with pytest.raises(PermissionError) as raised:
        batch_module._write_report(tmp_path, _report_document())
    assert raised.value is error
    assert len(calls) == 6
    assert sleeps == pytest.approx([.02, .04, .06, .08, .1])
    assert (tmp_path / 'lote.json').read_bytes() == original
    assert not (tmp_path / 'Resumen_lote.txt').exists()


@pytest.mark.parametrize('platform,winerror', [('posix', 5), ('nt', 2), ('nt', None)])
def test_report_other_permission_errors_propagate_immediately(tmp_path, monkeypatch, platform, winerror):
    calls, sleeps = [], []
    error = PermissionError('Not a transient Windows sharing lock')
    if winerror is not None:
        error.winerror = winerror
    def replace(*args):
        calls.append(args)
        raise error
    monkeypatch.setattr(batch_module, 'os', SimpleNamespace(name=platform, replace=replace))
    monkeypatch.setattr(batch_module, 'time', SimpleNamespace(sleep=sleeps.append))
    with pytest.raises(PermissionError) as raised:
        batch_module._write_report(tmp_path, _report_document())
    assert raised.value is error
    assert len(calls) == 1
    assert sleeps == []
