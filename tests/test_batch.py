"""Concentric spacing and partial batch outcomes, without three costly solves."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from halbach_coils.coilgen.batch import BatchConfig, build_layer_configs, gradient_radial_bounds, run_batch
from halbach_coils.coilgen.config import Config, preset_for
from halbach_coils.run_pipeline import PipelineResult
from halbach_coils.coilgen import batch as batch_module


def _batch(tmp_path=None, **changes):
    base = Config(output_language='es')
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


def test_per_axis_connections_do_not_change_shared_inputs_or_radial_gap():
    batch = _batch(cut_widths=(.003,.003,.001),
                   shift_smooth_factors=((1,1,3),(1,1,3),(7,7,7)))
    original = deepcopy(batch.base)
    configs = build_layer_configs(batch)
    by_axis = {cfg.gradient_axis:cfg for cfg in configs}
    assert by_axis['x'].winding.cut_width == .003
    assert by_axis['z'].winding.cut_width == .001
    assert by_axis['x'].winding.normal_shift_smooth == [1,1,3]
    assert by_axis['z'].winding.normal_shift_smooth == [7,7,7]
    assert batch.base.winding == original.winding
    for left,right in zip(configs,configs[1:]):
        assert gradient_radial_bounds(right)[0]-gradient_radial_bounds(left)[1] == pytest.approx(batch.radial_gap)


@pytest.mark.parametrize('changes', [
    {'cut_widths':(.001,.002)}, {'cut_widths':(.001,0,.002)},
    {'shift_smooth_factors':((1,1,3),(7,7,7))},
    {'shift_smooth_factors':((1,0,3),(7,7,7),(7,7,7))},
    {'shift_smooth_factors':((1,1.5,3),(7,7,7),(7,7,7))},
])
def test_invalid_axis_connections_are_rejected(changes):
    with pytest.raises(ValueError):
        build_layer_configs(_batch(**changes))


def test_anchor_and_safe_default_gap_protect_wire_envelopes_and_preserve_base():
    batch = _batch(tikhonov_factors=(20000, 10000, 30000), num_levels=(12, 14, 16))
    original = deepcopy(batch.base)
    z, x, y = build_layer_configs(batch)
    assert (z.gradient_axis, x.gradient_axis, y.gradient_axis) == ('z', 'x', 'y')
    # The 35 mm anchor is a real free radius, including exposed cable.
    assert z.shell_inner_radius == pytest.approx(.037)
    assert z.shell_outer_radius == pytest.approx(.041)
    assert z.estimated_wire_inner_radius == pytest.approx(.035)
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
    assert gradient_radial_bounds(y)[1] == pytest.approx(.055)
    assert gradient_radial_bounds(z)[0] == pytest.approx(.0297)
    for inner, outer in ((z, x), (x, y)):
        assert gradient_radial_bounds(outer)[0] - gradient_radial_bounds(inner)[1] == pytest.approx(batch.radial_gap)
    equivalent_inner = deepcopy(batch)
    equivalent_inner.radius_mode = 'inner'
    equivalent_inner.anchor_radius = gradient_radial_bounds(z)[0]
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
    batch.radial_gap = .0003
    configs = build_layer_configs(batch)
    assert configs[0].estimated_wire_inner_radius == pytest.approx(.035)
    for inner, outer in zip(configs, configs[1:]):
        assert outer.estimated_wire_inner_radius - inner.estimated_wire_outer_radius == pytest.approx(.0003)
        assert outer.shell_inner_radius - inner.shell_outer_radius == pytest.approx(.0063)


def test_thinner_cable_uses_same_pipeline_wall_but_reserves_real_gradient_gap():
    batch = _batch(anchor_radius=.0265, radial_gap=.001,
                   conductor_widths=(.0015, .0015, .0015), layer_gaps=(0, 0, 0))
    configs = build_layer_configs(batch)
    assert [cfg.shell_wall_thickness for cfg in configs] == pytest.approx([.003]*3)
    assert [gradient_radial_bounds(cfg) for cfg in configs] == pytest.approx(
        np.array([[.0265, .0325], [.0335, .0395], [.0405, .0465]]))
    assert [cfg.shell_inner_radius for cfg in configs] == pytest.approx([.028, .035, .042])


@pytest.mark.parametrize('field,value,match', [
    ('anchor_radius', -1, 'Anchor radius'),
    ('radius_mode', 'manual', 'Radius mode'),
    ('radial_gap', float('nan'), 'Inter-gradient gap'),
    ('radial_gap', -.0001, 'Inter-gradient gap'),
    ('axis_order', ('z', 'z', 'x'), 'without duplicates'),
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


def test_batch_defers_marks_to_joint_assembly_and_saves_checkbox(tmp_path, monkeypatch):
    batch = _batch(tmp_path)
    batch.include_b0_markers = True
    batch.base.shell.b0_marker = True
    calls = []
    fake = _fake_pipeline(calls)
    def pipeline(cfg, **kwargs):
        assert cfg.shell.b0_marker is False
        return fake(cfg, **kwargs)
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', pipeline)
    def finalize(cfg, layers, results):
        assert cfg.include_b0_markers is True
        return {'b0_markers': {'enabled': True, 'angle_deg': 90}}
    output = _run_batch(batch, finalize=finalize)
    manifest = json.loads(Path(output.manifest_path).read_text(encoding='utf-8'))
    assert manifest['include_b0_markers'] is True
    assert manifest['assembly']['b0_markers']['enabled'] is True
    assert batch.base.shell.b0_marker is True


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


def test_geometric_infeasibility_keeps_other_axes_running_and_skips_assembly(tmp_path, monkeypatch):
    calls = []
    good = _fake_pipeline(calls)
    def pipeline(cfg, **kwargs):
        if cfg.gradient_axis == 'x':
            calls.append('x')
            root = Path(cfg.output_dir); root.mkdir(parents=True)
            return PipelineResult(str(root), needs_revision=True, message='Turns remain 1.8 mm apart.')
        return good(cfg, **kwargs)
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', pipeline)
    def finalize(*_):
        pytest.fail('An incomplete geometric set must never be assembled.')
    result = _run_batch(_batch(tmp_path), finalize=finalize)
    assert calls == ['z', 'x', 'y']
    assert not result.completed and result.assembly is None
    assert len(result.layers) == 3
    manifest = json.loads(Path(result.manifest_path).read_text(encoding='utf-8'))
    assert manifest['status'] == 'needs_revision'
    assert [layer['status'] for layer in manifest['layers']] == ['complete', 'needs_revision', 'complete']
    assert '1.8 mm' in Path(result.summary_path).read_text(encoding='utf-8')


def test_expected_assembly_interference_keeps_finished_axes_as_a_reviewable_result(tmp_path, monkeypatch):
    from halbach_coils.coilgen.assembly import AssemblyFeasibilityError
    calls = []
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', _fake_pipeline(calls))
    def finalize(*_):
        raise AssemblyFeasibilityError('Assembly interference: insufficient gap.')
    result = _run_batch(_batch(tmp_path), finalize=finalize)
    assert calls == ['z', 'x', 'y']
    assert not result.completed and result.assembly is None
    assert 'insufficient gap' in result.message
    document = json.loads(Path(result.manifest_path).read_text(encoding='utf-8'))
    assert document['status'] == 'needs_revision'
    assert all(layer['status'] == 'complete' for layer in document['layers'])


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


def test_actual_3d_verification_is_still_required_for_terminal_leads(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('halbach_coils.run_pipeline.run_pipeline', _fake_pipeline(calls))
    def verify(batch, configs, results):
        assert len(results) == 3
        raise RuntimeError('The actual outer lead interferes with the inner layer.')
    with pytest.raises(RuntimeError, match='actual outer lead interferes'):
        _run_batch(_batch(tmp_path, radial_gap=.001), finalize=verify)
    assert calls == ['z', 'x', 'y']
    document = json.loads((tmp_path / 'lote.json').read_text(encoding='utf-8'))
    assert not document['requires_interference_check']
    assert document['format_version'] == 2
    assert document['radial_gap_definition'].startswith('complete_gradient')
    assert document['status'] == 'failed'


@pytest.mark.parametrize('gap', [0, .002])
@pytest.mark.parametrize('mode', ['inner', 'outer'])
def test_reported_user_case_gap_separates_complete_gradients(gap, mode):
    batch = _batch(anchor_radius=.05, radial_gap=gap)
    batch.base.target.rx = batch.base.target.ry = batch.base.target.rz = .03
    layers = build_layer_configs(batch)
    if mode == 'outer':
        batch.radius_mode = 'outer'
        batch.anchor_radius = gradient_radial_bounds(layers[-1])[1]
        layers = build_layer_configs(batch)
    assert gradient_radial_bounds(layers[0])[0] == pytest.approx(.05)
    for inner, outer in zip(layers, layers[1:]):
        assert gradient_radial_bounds(outer)[0] - gradient_radial_bounds(inner)[1] == pytest.approx(gap)
        assert outer.shell_inner_radius - inner.shell_outer_radius == pytest.approx(.004 + gap)
    if gap == .002:
        assert [gradient_radial_bounds(cfg) for cfg in layers] == pytest.approx(
            np.array([[.05, .058], [.06, .068], [.07, .078]]))


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
