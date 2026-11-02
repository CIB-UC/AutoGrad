"""Causal regressions from the user's GX/GY reference, without an optimizer."""
from pathlib import Path
from types import SimpleNamespace
import json

import numpy as np
import pytest

from pyCoilGen.helpers.wire_geometry import closed_wire_path, wire_contact_pairs
from pyCoilGen.sub_functions.shift_return_paths import plan_return_path_layers
from pyCoilGen.sub_functions.return_path_trace import save_return_path_traces, replay_return_path_trace
from halbach_coils.coilgen.outputs import result_subfolder, write_result_summary

DATA = Path(__file__).parent/'test_data'


def gx():
    with np.load(DATA/'gx20_reference_layer_plan.npz', allow_pickle=False) as data:
        return dict(data)


def plan(data, enabled=True):
    return plan_return_path_layers(data['surface_uv'], data['crossing_segments'],
                                  [7,7,7], -.003, .0015, reassign=enabled)


def test_gx20_joint_plan_reproduces_the_winding_reference_exactly():
    data = gx()
    result = plan(data)
    assert result['report']['status'] == 'joint_applied'
    assert result['report']['historical_insufficient_crossings'] == [10]
    assert result['report']['changed_selection_stations'] == 30
    assert result['report']['residual_insufficient_crossings'] == []
    for saved, computed in [('historical_points','historical_points'), ('selected_points','points'),
                            ('selected_shift','shift'), ('selected_factors','factors')]:
        np.testing.assert_array_equal(data[saved], result[computed])
    reproduced = data['surface_v']+data['effective_normals']*result['shift'][None, :]*-.003
    np.testing.assert_array_equal(reproduced, data['shifted_v'])
    # Only pruning and current orientation follow; recovery moves zero stations.
    np.testing.assert_array_equal(data['pruned_v'], data['recovered_v'])
    np.testing.assert_array_equal(data['recovered_v'][:, ::-1], data['reference_v'])
    path = closed_wire_path(data['reference_v'].T)
    distances = wire_contact_pairs(path, .003, closed=True, local_diameter=.0015)[2]
    assert np.count_nonzero(distances < .0015) == 0
    assert distances.min()*1000 == pytest.approx(2.3928809458278577, abs=1e-10)


def test_historical_smoothed_gx_sends_both_branches_inside():
    data = gx()
    result = plan(data, enabled=False)
    np.testing.assert_array_equal(result['points'], data['historical_points'])
    np.testing.assert_array_equal(result['shift'], data['historical_shift'])
    np.testing.assert_array_equal(result['factors'][10], [1., 1.])
    assert result['report']['status'] == 'reassignment_disabled'
    assert not result['report']['joint_attempted']


def test_gy20_reports_the_grouping_conflict_and_keeps_the_historical_choice():
    with np.load(DATA/'gy20_reference_layer_conflict.npz', allow_pickle=False) as data:
        result = plan(data)
        np.testing.assert_array_equal(result['points'], data['historical_points'])
        np.testing.assert_array_equal(result['shift'], data['historical_shift'])
    assert result['report']['status'] == 'joint_incompatible'
    witness = result['report']['grouping_conflict']
    assert witness['crossing_indices'] == [3, 4, 5]
    assert len(witness['odd_cycle_group_ids']) == 3
    assert witness['scope'] == 'incompatible_with_this_sample_grouping_only'


def test_no_crossings_keep_short_tracks_at_their_original_station_count():
    result = plan_return_path_layers(np.array([[0.,1.,2.], [0.,0.,0.]]),
                                    np.empty((0,2), int), [7,7,7], -.003, .0015)
    np.testing.assert_array_equal(result['shift'], np.zeros(3))
    assert result['report']['status'] == 'no_crossings'


def archive(tmp_path, effective_cut_width=None):
    data = gx()
    result = plan(data)
    args = SimpleNamespace(save_return_path_trace=True, output_directory=str(tmp_path), project_name='GX',
        normal_shift_smooth_factors=[7,7,7], normal_shift_length=-.003, conductor_thickness=.0015,
        reassign_crossing_layers=True, interconnection_cut_width=.001, force_cut_selection=[])
    part = SimpleNamespace(return_path_trace=data, return_path_report=result['report'],
        wire_path=SimpleNamespace(v=data['reference_v'], uv=data['surface_uv']),
        clearance_report={'status':'unchanged', 'max_displacement_mm':0.})
    if effective_cut_width is not None:
        part.return_path_effective_args = dict(vars(args), interconnection_cut_width=effective_cut_width,
                                               force_cut_selection=['low'])
    save_return_path_traces([part], args, stage='final')
    return tmp_path/'GX_wire_0_return_paths.npz', data


def test_saved_plan_replays_shift_pruning_and_recorded_recovery_without_a_solve(tmp_path):
    filename, data = archive(tmp_path)
    for stage in ('shifted', 'pruned', 'recovered', 'final'):
        expected = data['reference_v'] if stage == 'final' else data[stage+'_v']
        np.testing.assert_array_equal(replay_return_path_trace(filename, stage=stage), expected.T)
    metadata = json.loads(filename.with_suffix('.json').read_text())
    assert metadata['source_sha256']['pyCoilGen/sub_functions/shift_return_paths.py']
    assert metadata['layer_plan']['joint_applied']
    assert result_subfolder(filename.name, 'es') == 'Diagnostico'
    assert result_subfolder(filename.with_suffix('.json').name, 'en') == 'Diagnostics'


def test_replay_rejects_a_changed_archive(tmp_path):
    filename, _ = archive(tmp_path)
    with filename.open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='changed return-path archive'):
        replay_return_path_trace(filename)


def test_selected_retry_keeps_its_own_effective_cut_arguments(tmp_path):
    filename, _ = archive(tmp_path, effective_cut_width=.0045)
    metadata = json.loads(filename.with_suffix('.json').read_text())
    assert metadata['effective_args']['interconnection_cut_width'] == .0045
    assert metadata['effective_args']['force_cut_selection'] == ['low']
    assert metadata['requested_args']['interconnection_cut_width'] == .001
    assert metadata['requested_args']['force_cut_selection'] == []
    replay_return_path_trace(filename)


def test_replay_rejects_a_different_smoothing_plan(tmp_path):
    filename, _ = archive(tmp_path)
    metadata_path = filename.with_suffix('.json')
    metadata = json.loads(metadata_path.read_text())
    metadata['effective_args']['normal_shift_smooth_factors'] = [3,3,3]
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='Planner no longer reproduces'):
        replay_return_path_trace(filename)


def test_original_version_one_archives_still_replay_the_original_planner(tmp_path):
    filename,data=archive(tmp_path)
    metadata_path=filename.with_suffix('.json')
    metadata=json.loads(metadata_path.read_text())
    metadata['layer_plan']['algorithm']='historical_then_joint_v1'
    metadata_path.write_text(json.dumps(metadata))
    np.testing.assert_array_equal(replay_return_path_trace(filename),data['shifted_v'].T)


def test_run_summary_explains_a_joint_fallback_separately_from_physical_validity(tmp_path):
    diagnostics = tmp_path/'Diagnostico'
    diagnostics.mkdir()
    (diagnostics/'GX_geometry.json').write_text(json.dumps(dict(status='valid', parts=[], return_paths=[dict(
        status='joint_incompatible', trace_file='GX_wire_0_return_paths.npz')])))
    write_result_summary(tmp_path, stem='GX', language='es')
    content = (tmp_path/'Resumen.txt').read_text(encoding='utf-8')
    assert 'agrupación incompatible; se conservó la selección histórica' in content
    assert 'GX_wire_0_return_paths.npz' in content
