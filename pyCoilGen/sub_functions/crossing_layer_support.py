"""Joint two-layer assignment with the exact support of the smoothing kernel."""
import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp


def exact_support_shift_points(segment_pairs, previous_points, kernel):
    """Place descent seeds jointly instead of forcing nearby branches together.

    Each crossed segment has an original/return-layer color. Its two smoothed
    endpoints must be zero or fully saturated according to that color. Across
    a crossing colors are opposite. Binary seed locations may move within the
    existing kernel support; no mesh, shift depth or smoothing setting changes.

    The objective first preserves historical colors and then uses fewer seeds.
    This is NOT a bend-radius or 3D-clearance optimizer. Both need later checks.
    A node budget bounds the discrete solve, without wall-clock-dependent plans.
    """
    pairs = np.asarray(segment_pairs, dtype=int).reshape(-1, 2)
    previous, kernel = np.asarray(previous_points, float), np.asarray(kernel, float)
    if not len(pairs):
        return previous.copy(), dict(status='no_crossings')
    segments = np.unique(pairs)
    endpoints = np.unique(np.r_[segments, segments+1])
    offset = (len(kernel)-1)//2
    seeds = np.unique(np.concatenate([
        np.arange(max(0, endpoint+offset-len(kernel)+1), min(len(previous), endpoint+offset+1))
        for endpoint in endpoints]))
    rows, cols, values, lower, upper = [], [], [], [], []

    def add(indices, coefficients, low, high):
        row = len(lower)
        rows.extend([row]*len(indices))
        cols.extend(indices)
        values.extend(coefficients)
        lower.append(low)
        upper.append(high)

    for index, segment in enumerate(segments):
        color = len(seeds)+index
        for endpoint in (segment, segment+1):
            kernel_ids = endpoint-seeds+offset
            selected = np.flatnonzero((kernel_ids >= 0) & (kernel_ids < len(kernel)))
            weights = kernel[kernel_ids[selected]]
            # color=0 -> sum=0; color=1 -> sum>=1 (convolution clips to 1).
            add(np.r_[selected, color], np.r_[weights, -1.], 0., np.inf)
            add(np.r_[selected, color], np.r_[weights, -weights.sum()], -np.inf, 0.)
    for pair in pairs:
        add(len(seeds)+np.searchsorted(segments, pair), [1., 1.], 1., 1.)
    count = len(seeds)+len(segments)
    matrix = sparse.csc_matrix((values, (rows, cols)), shape=(len(lower), count))
    cost = np.r_[1.+np.arange(len(seeds))/max(len(seeds),1)**2,
                 (1.-2.*previous[segments])*(len(seeds)+1.)]
    result = milp(cost, integrality=np.ones(count), bounds=Bounds(0., 1.),
        constraints=LinearConstraint(matrix, lower, upper), options={'node_limit': 4096})
    report = dict(status={0:'optimal', 1:'node_budget_reached', 2:'infeasible',
                          3:'unbounded', 4:'solver_error'}.get(result.status, 'solver_error'),
                  seed_candidates=len(seeds), branch_variables=len(segments), node_limit=4096,
                  nodes=int(getattr(result, 'mip_node_count', 0) or 0))
    if result.x is None:
        return None, report
    points = np.zeros_like(previous)
    points[seeds] = np.rint(result.x[:len(seeds)])
    shift = np.minimum(np.convolve(points, kernel, mode='full')[offset:offset+len(points)], 1.)
    endpoints = np.r_[pairs, pairs+1]
    if not np.all(np.abs(shift[endpoints[:,0]]-shift[endpoints[:,1]]) >= 1.-1e-9):
        report['status'] = 'candidate_failed_exact_check'
        return None, report
    report['full_opposite_layers_verified'] = True
    return points, report
