"""Shared exact segment distances for routing and physical wire validation."""

import numpy as np
from scipy.spatial import cKDTree


class WireInterferenceError(ValueError):
    """A physically invalid conductor, rather than an unexpected program error."""


def closed_wire_path(path):
    """Represent the sweep's last-to-first edge explicitly, exactly once.

    A sweep joins its last section to its first even when their centres are
    farther apart than a wire diameter. Endpoint distance cannot infer that
    topology. Open terminal-to-terminal paths must not use this helper.
    """
    path = np.asarray(path, dtype=float)
    if len(path) and not np.array_equal(path[0], path[-1]):
        return np.vstack((path, path[0]))
    return path


def segment_closest(a, b, c, d, *, return_parameters=False):
    """Exact pair distances and vectors from the closest point on A to B."""
    u, v, w = b-a, d-c, a-c
    A, B, C = (u*u).sum(1), (u*v).sum(1), (v*v).sum(1)
    D, E = (u*w).sum(1), (v*w).sum(1)
    denom = A*C-B*B
    safe = denom > 1e-24
    s = np.divide(B*E-C*D, denom, out=np.zeros_like(A), where=safe)
    t = np.divide(A*E-B*D, denom, out=np.zeros_like(A), where=safe)
    interior = safe & (s >= 0) & (s <= 1) & (t >= 0) & (t <= 1)
    distances = np.full(len(a), np.inf)
    vectors = -w-s[:,None]*u+t[:,None]*v
    distances[interior] = np.linalg.norm(vectors[interior], axis=1)
    for endpoint, (point, start, edge, norm2, sign) in enumerate(
            ((a,c,v,C,1), (b,c,v,C,1), (c,a,u,A,-1), (d,a,u,A,-1))):
        f = np.clip(((point-start)*edge).sum(1)/np.maximum(norm2, 1e-30), 0, 1)
        candidate = sign*(start+f[:,None]*edge-point)
        new_distance = np.linalg.norm(candidate,axis=1)
        better = new_distance < distances
        vectors[better] = candidate[better]
        distances[better] = new_distance[better]
        if return_parameters:
            s[better] = (float(endpoint) if endpoint < 2 else f[better])
            t[better] = (f[better] if endpoint < 2 else float(endpoint-2))
    if return_parameters:
        return distances, vectors, s, t
    return distances, vectors


def segment_distances(a, b, c, d):
    return segment_closest(a,b,c,d)[0]


def near_segment_pairs(path_a, path_b, threshold):
    a, b = path_a[:-1], path_a[1:]
    c, d = path_b[:-1], path_b[1:]
    if not len(a) or not len(c):
        return np.empty(0, int), np.empty(0, int), np.empty(0)
    tree = cKDTree((c+d)/2)
    radius = threshold + np.linalg.norm(b-a, axis=1)/2 + np.linalg.norm(d-c, axis=1).max()/2
    lists = tree.query_ball_point((a+b)/2, radius)
    ia = np.repeat(np.arange(len(a)), [len(x) for x in lists])
    ib = np.array([j for group in lists for j in group], dtype=int)
    dist = segment_distances(a[ia], b[ia], c[ib], d[ib])
    return ia, ib, dist


def wire_contact_pairs(path, diameter: float, *, closed: bool, local_diameter=None,
                       active_segments=None):
    """Exact nonlocal 3D segment distances for a round conductor, in metres.

    Segment capsules of radius diameter/2 bound the real circular wire.
    Only the connected local arc within two diameters is excluded: adjacent
    capsules share their intended joint. Apply the same rule across a closed
    curve's seam. No projected crossing or manufacturing groove size enters
    the physical separation test.

    ``closed`` controls the connected arc exclusion across the seam; the
    closing edge must be present in ``path`` (see ``closed_wire_path``).
    """
    path = np.asarray(path, dtype=float)
    if (path.ndim != 2 or path.shape[1] != 3 or len(path) < 2
            or not np.all(np.isfinite(path)) or not np.isfinite(diameter) or diameter <= 0):
        raise ValueError('Expected a finite N x 3 wire path and positive wire diameter.')
    lengths = np.linalg.norm(np.diff(path, axis=0), axis=1)
    positions = np.r_[0., np.cumsum(lengths)]
    if active_segments is None:
        i, j, distances = near_segment_pairs(path, path, diameter)
    else:
        # During local recovery only pairs touching a changed segment can
        # become new contacts. Keep the exact same metric and arc exclusion.
        active = np.unique(np.asarray(active_segments, dtype=int))
        midpoints = (path[:-1]+path[1:])/2
        tree = cKDTree(midpoints)
        radius = diameter + lengths[active]/2 + lengths.max()/2
        neighbours = tree.query_ball_point(midpoints[active], radius)
        ia = np.repeat(active, [len(group) for group in neighbours])
        ib = np.array([index for group in neighbours for index in group], dtype=int)
        pairs = np.unique(np.column_stack((np.minimum(ia, ib), np.maximum(ia, ib))), axis=0)
        i, j = pairs.T
        distances = segment_distances(path[i], path[i+1], path[j], path[j+1])
    arc = np.maximum(0., positions[j] - positions[i+1])
    if closed:
        arc = np.minimum(arc, positions[-1] - positions[j+1] + positions[i])
    # Floating-point roundoff only, scaled to these SI coordinates.
    roundoff = 32*np.finfo(float).eps*max(float(np.abs(path).max()), diameter)
    # A routing margin may enlarge the search radius, but must never enlarge
    # the excluded connected neighbourhood of the real physical conductor.
    local = diameter if local_diameter is None else float(local_diameter)
    if not np.isfinite(local) or local <= 0:
        raise ValueError('Expected a positive finite local conductor diameter.')
    keep = (j > i) & (arc > 2 * local) & (distances < diameter - roundoff)
    return i[keep], j[keep], distances[keep], positions
