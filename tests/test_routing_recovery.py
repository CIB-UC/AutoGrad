"""A failed route retries from clean contours without rerunning optimization."""

from types import SimpleNamespace as NS

import numpy as np

from pyCoilGen.sub_functions import routing_recovery as recovery


def inputs(**changes):
    return NS(**dict(auto_wire_clearance=True, skip_sweep=False,
                     conductor_thickness=.0015, interconnection_cut_width=.001,
                     force_cut_selection=[], **changes))


def test_interference_retries_from_independent_groups_and_keeps_selected_parts(monkeypatch):
    original = [NS(groups=[['original contour']], wire_path=NS(v=np.zeros((3, 2))),
                   clearance_report={'status': 'unresolved'})]
    args = inputs()
    seed = recovery.capture_routing_inputs(original, args)
    visited = []

    def status(parts, diameter):
        assert diameter == .0015
        clear = parts[0].groups[0][-1] == 'low'
        return (0, None) if clear else (2, .0005)

    def rebuild(parts, variant):
        assert parts[0].groups == [['original contour']]
        visited.append((variant.interconnection_cut_width, variant.force_cut_selection))
        parts[0].groups[0].append('low' if variant.force_cut_selection else 'high')
        parts[0].clearance_report = {'status': 'unchanged'}
        return parts

    monkeypatch.setattr(recovery, '_physical_status', status)
    finalized = []
    def finish(parts, variant):
        assert variant.force_cut_selection == ['low']
        finalized.append(parts)
        return parts
    selected = recovery.recover_routing(seed, original, args, (rebuild,), finalize=finish)
    assert visited == [(.001, ['low'])]
    assert selected is not original
    assert finalized == [selected]
    assert original[0].groups == seed[0].groups == [['original contour']]
    assert args.force_cut_selection == [] and args.interconnection_cut_width == .001
    report = selected[0].clearance_report['routing_recovery']
    assert report['status'] == 'recovered'
    assert report['effective_cut_side'] == ['low']


def test_all_rejected_alternatives_preserve_original_and_record_attempts(monkeypatch):
    original = [NS(groups=[['contour']], clearance_report={'status': 'unresolved'})]
    args = inputs()
    seed = recovery.capture_routing_inputs(original, args)
    monkeypatch.setattr(recovery, '_physical_status', lambda *_: (2, .0005))

    def rejected(parts, variant):
        assert parts[0].groups == [['contour']]
        parts[0].groups[0].append('mutated')
        raise ValueError('Cut cannot open here')

    assert recovery.recover_routing(seed, original, args, (rejected,)) is original
    history = original[0].clearance_report['routing_recovery']
    assert history['status'] == 'unresolved' and len(history['attempts']) == 5
    assert original[0].groups == seed[0].groups == [['contour']]


def test_valid_geometry_is_unchanged_and_explicit_cut_side_is_respected(monkeypatch):
    original = [NS(groups=[])]
    args = inputs()
    monkeypatch.setattr(recovery, '_physical_status', lambda *_: (0, None))
    assert recovery.recover_routing(original, original, args, ()) is original
    args.force_cut_selection = ['high']
    variants = list(recovery._routing_variants(args, .0015))
    assert len(variants) == 2
    assert all(item.force_cut_selection == ['high'] for item in variants)
