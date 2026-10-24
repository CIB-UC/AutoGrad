"""Retry physically rejected interconnections without repeating optimization."""

from copy import copy, deepcopy
import logging

import numpy as np

from pyCoilGen.helpers.wire_geometry import closed_wire_path, wire_contact_pairs

log = logging.getLogger(__name__)


def capture_routing_inputs(parts, args):
    """Keep independent contour groups, sharing the large read-only operators."""
    if not getattr(args, 'auto_wire_clearance', False):
        return None
    return _fresh_parts(parts)


def _fresh_parts(parts):
    fresh = []
    for part in parts:
        candidate = copy(part)
        candidate.groups = deepcopy(part.groups)
        fresh.append(candidate)
    return fresh


def _physical_status(parts, diameter):
    contacts, minimum = 0, None
    for part in parts:
        # These are pre-lead sweeps: their last and first rings are connected.
        path = closed_wire_path(np.asarray(part.wire_path.v).T)
        _, _, distances, _ = wire_contact_pairs(path, diameter, closed=True)
        contacts += len(distances)
        if len(distances):
            value = float(distances.min()*1000)
            minimum = value if minimum is None else min(minimum, value)
    return contacts, minimum


def _routing_variants(args, diameter):
    requested = list(getattr(args, 'force_cut_selection', []))
    # Respect an explicitly requested side. Automatic selection currently uses
    # high cuts; the opposite side is another candidate only in automatic mode.
    sides = [requested] if requested else [[], ['low']]
    original_width = float(args.interconnection_cut_width)
    seen = {(original_width, tuple(requested))}
    for width in (original_width, max(original_width, 2*diameter),
                  max(original_width, 3*diameter)):
        for side in sides:
            key = (width, tuple(side))
            if key in seen:
                continue
            seen.add(key)
            candidate = copy(args)
            candidate.interconnection_cut_width = width
            candidate.force_cut_selection = list(side)
            yield candidate


def recover_routing(seed, original, args, steps, *, finalize=None):
    """Keep the first fully cleared candidate, or the original rejected result.

    ``steps`` rebuilds interconnections, shifts, optional PCB data and the
    sweep. Each attempt starts with independent groups from the same contours.
    Field evaluation/export happen later on the selected parts only.
    """
    if seed is None or getattr(args, 'skip_sweep', False):
        return original
    diameter = float(args.conductor_thickness)
    contacts, minimum = _physical_status(original, diameter)
    if not contacts:
        return original
    history = dict(status='unresolved', initial_contact_pairs=contacts,
                   initial_minimum_mm=minimum,
                   requested_cut_width_mm=float(args.interconnection_cut_width*1000),
                   requested_cut_side=list(getattr(args, 'force_cut_selection', [])),
                   attempts=[])
    for number, variant in enumerate(_routing_variants(args, diameter), 1):
        attempt = dict(cut_width_mm=float(variant.interconnection_cut_width*1000),
                       cut_side=list(variant.force_cut_selection))
        history['attempts'].append(attempt)
        log.info('Retrying interconnection routing %d: cut %.4g mm, side %s.',
                 number, attempt['cut_width_mm'], attempt['cut_side'] or 'auto')
        candidate = _fresh_parts(seed)
        try:
            for step in steps:
                candidate = step(candidate, variant)
            remaining, candidate_minimum = _physical_status(candidate, diameter)
            if not remaining and finalize is not None:
                candidate = finalize(candidate, variant)
                remaining, candidate_minimum = _physical_status(candidate, diameter)
        except (ValueError, RuntimeError, IndexError, FloatingPointError) as exc:
            # An optional alternative must not replace the original diagnosis
            # when its cut cannot be opened or produces invalid geometry.
            attempt.update(status='rejected', error=f'{type(exc).__name__}: {exc}')
            log.warning('Alternative interconnection rejected: %s', exc)
            continue
        attempt.update(status='valid' if not remaining else 'interference',
                       contact_pairs=remaining, minimum_mm=candidate_minimum)
        if remaining:
            continue
        history.update(status='recovered', selected_attempt=number,
                       effective_cut_width_mm=attempt['cut_width_mm'],
                       effective_cut_side=attempt['cut_side'])
        for part in candidate:
            report = dict(getattr(part, 'clearance_report', {}) or {})
            report['routing_recovery'] = deepcopy(history)
            part.clearance_report = report
        log.info('Recovered interconnections: all wire paths pass the physical clearance check.')
        return candidate
    for part in original:
        report = dict(getattr(part, 'clearance_report', {}) or {})
        report['routing_recovery'] = deepcopy(history)
        part.clearance_report = report
    return original
