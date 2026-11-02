"""Constructive assignment and final-path checks, independent of planner metadata."""
from pathlib import Path
from types import SimpleNamespace as NS
import json
import numpy as np
import pytest

from pyCoilGen.sub_functions.crossing_layer_support import exact_support_shift_points
from pyCoilGen.sub_functions.shift_return_paths import crossing_shift_points,plan_return_path_layers
from pyCoilGen.sub_functions.return_path_trace import save_return_path_traces,replay_return_path_trace
from pyCoilGen.helpers.return_path_distribution import cylindrical_layer_distribution
from pyCoilGen.helpers.wire_geometry import closed_wire_path,wire_contact_pairs
from halbach_coils import run_pipeline as pipeline
from halbach_coils.coilgen.config import Config
from halbach_coils.coilgen.overlap import OverlapReport

KERNEL=np.r_[np.arange(1,8),np.full(7,7),np.arange(6,0,-1)]/7


def test_actual_support_separates_branches_that_the_old_grouping_declared_incompatible():
    pairs=np.array([[10,100],[21,200],[111,211]])
    previous=np.zeros(250)
    assert crossing_shift_points(pairs,previous,len(KERNEL)) is None
    points,report=exact_support_shift_points(pairs,previous,KERNEL)
    assert report['status']=='optimal'
    shift=np.minimum(np.convolve(points,KERNEL,mode='same'),1.)
    for a,b in pairs:
        np.testing.assert_allclose(np.abs(shift[a:a+2]-shift[b:b+2]),1.,atol=1e-12)
    # The neighboring branches were NOT forced into a common layer.
    assert shift[10]!=shift[21] or shift[100]!=shift[111] or shift[200]!=shift[211]
    np.testing.assert_array_equal(previous,np.zeros(250))


def test_same_segment_triangle_cannot_use_two_full_layers_with_this_kernel():
    data=np.load(Path(__file__).parent/'test_data/gy20_reference_layer_conflict.npz')
    points,report=exact_support_shift_points(data['crossing_segments'],data['historical_points'],KERNEL)
    assert points is None
    assert report['status']=='infeasible'


def test_constructive_closed_wire_gets_parallel_underpasses_and_real_clearance():
    data=np.load(Path(__file__).parent/'test_data/return_paths_false_grouping.npz')
    plan=plan_return_path_layers(data['surface_uv'],data['pairs'],[7,7,7],-.003,.0015)
    assert plan['report']['status']=='joint_exact_support_applied'
    path=data['surface_v']+data['effective_normals']*plan['shift'][:,None]*-.003
    # Test the requested geometry, not an arbitrary tie between optimal seeds.
    repeated=plan_return_path_layers(data['surface_uv'],data['pairs'],[7,7,7],-.003,.0015)
    np.testing.assert_array_equal(plan['shift'],repeated['shift'])
    assert len(wire_contact_pairs(closed_wire_path(data['previous']),.0015,closed=True)[0])>0
    assert len(wire_contact_pairs(closed_wire_path(path),.0015,closed=True)[0])==0
    report=cylindrical_layer_distribution(path,.1,-.003,.0015)
    assert report['status']=='satisfied'
    assert report['classes']['inner+outer']==4


def test_recovered_gy_is_not_mistaken_for_the_gx_return_distribution():
    path=np.load(Path(__file__).parent/'test_data/gy20_recovered_return_crossings.npz')['path']
    assert len(wire_contact_pairs(closed_wire_path(path),.0015,closed=True)[0])==0
    report=cylindrical_layer_distribution(path,.0656,-.003,.0015)
    assert report['status']=='unresolved'
    assert report['unresolved_crossing_count']==3
    assert report['classes']['inner+transition']==2
    assert report['classes']['transition+transition']==1


def test_exact_support_assignment_is_archived_and_replayed_without_changing_its_decisions(tmp_path):
    data=np.load(Path(__file__).parent/'test_data/return_paths_false_grouping.npz')
    plan=plan_return_path_layers(data['surface_uv'],data['pairs'],[7,7,7],-.003,.0015)
    path=data['surface_v']+data['effective_normals']*plan['shift'][:,None]*-.003
    trace=dict(surface_v=data['surface_v'].T,surface_uv=data['surface_uv'],
        effective_normals=data['effective_normals'].T,crossing_segments=data['pairs'],
        historical_points=plan['historical_points'],historical_shift=plan['historical_shift'],
        selected_points=plan['points'],selected_shift=plan['shift'],selected_factors=plan['factors'],
        kernel=plan['kernel'],shifted_v=path.T)
    args=NS(save_return_path_trace=True,output_directory=str(tmp_path),project_name='support',
        normal_shift_smooth_factors=[7,7,7],normal_shift_length=-.003,conductor_thickness=.0015,
        reassign_crossing_layers=True)
    part=NS(return_path_trace=trace,return_path_report=plan['report'],wire_path=NS(v=path.T,uv=data['surface_uv']))
    save_return_path_traces([part],args,stage='final')
    np.testing.assert_array_equal(replay_return_path_trace(tmp_path/'support_wire_0_return_paths.npz'),path)


def bowtie(first_radius,last_radius):
    angle=np.array([-.2,.2,-.2,.2])
    radius=np.array([first_radius,first_radius,last_radius,last_radius])
    return np.c_[radius*np.cos(angle),radius*np.sin(angle),[-.01,.01,.01,-.01]]


@pytest.mark.parametrize('first,last,accepted,key',[
    (.05,.05,False,'outer+outer'),(.047,.047,False,'inner+inner'),
    (.05,.047,True,'inner+outer'),(.05,.048,True,'outer+transition'),
    (.0495,.0476,False,'transition+transition'),
])
def test_final_projection_checks_the_actual_curve(first,last,accepted,key):
    report=cylindrical_layer_distribution(bowtie(first,last),.05,-.003,.0015)
    assert report['crossing_count']==1
    assert report['classes'][key]==1
    assert (report['status']=='satisfied') is accepted


def test_two_inward_returns_can_be_physically_clear_and_still_fail_the_requested_distribution():
    path=bowtie(.0495,.0476)
    assert len(wire_contact_pairs(closed_wire_path(path),.0015,closed=True)[0])==0
    assert cylindrical_layer_distribution(path,.05,-.003,.0015)['unresolved_crossing_count']==1


def test_original_reference_has_only_mixed_crossings_without_using_decision_metadata():
    data=np.load(Path(__file__).parent/'test_data/gx20_reference_layer_plan.npz')
    report=cylindrical_layer_distribution(data['reference_v'].T,.0595,-.003,.0015)
    assert report['status']=='satisfied'
    assert report['classes']['inner+outer']==39
    assert report['unresolved_crossing_count']==0


def test_projection_does_not_hide_a_crossing_on_the_angular_seam():
    path=bowtie(.05,.047)
    path[:,:2]*=-1
    report=cylindrical_layer_distribution(path,.05,-.003,.0015)
    assert report['status']=='satisfied'
    assert report['crossing_count']==1


def test_outward_return_transition_uses_the_symmetric_original_layer_rule():
    report=cylindrical_layer_distribution(bowtie(.05,.052),.05,.003,.0015)
    assert report['status']=='satisfied'
    assert report['classes']['inner+transition']==1


def test_pipeline_does_not_accept_crossed_returns_only_because_real_wire_clearance_passed(tmp_path,monkeypatch):
    cfg=Config(show_plots=False,output_dir=str(tmp_path))
    calls=[]
    monkeypatch.setattr(pipeline,'run_gradient',lambda *a,**kw:(object(),dict(
        return_path_distribution=dict(status='unresolved',unresolved_crossing_count=1)),OverlapReport()))
    monkeypatch.setattr(pipeline,'run_leads',lambda *a,**kw:calls.append('leads'))
    monkeypatch.setattr(pipeline,'run_shell',lambda *a,**kw:calls.append('shell'))
    result=pipeline.run_pipeline(cfg,question_language='es',ask_user=lambda _:pytest.fail('This is the requested routing criterion, not an approval'))
    assert result.needs_revision
    assert 'ramas de retorno' in result.message
    assert not calls
