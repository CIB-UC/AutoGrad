import numpy as np
from typing import List
from copy import deepcopy

# Logging
import logging

# Local imports
from .data_structures import CoilPart, Mesh
from .smooth_track_by_folding import smooth_track_by_folding
from .calc_3d_rotation_matrix_by_vector import calc_3d_rotation_matrix_by_vector

log = logging.getLogger(__name__)

LAYER_PLANNER_VERSION = 'joint_layers_exact_support_v2'
LAYER_PLANNER_VERSIONS = ('historical_then_joint_v1', LAYER_PLANNER_VERSION)


def plan_return_path_layers(track_uv, segment_pairs, smooth_factors,
                           normal_shift_length, diameter, *, reassign=True,
                           version=LAYER_PLANNER_VERSION):
    """Deterministic layer decisions, independent of displacement and recovery.

    Retain the historical selection and sample-based kernel exactly. The joint
    assignment only runs when that smoothed selection lacks radial separation.
    Return BOTH decisions so a caller can inspect/replay why each branch moved.
    This checks crossing factors, not finite-wire clearance or bend radii.
    """
    if version not in LAYER_PLANNER_VERSIONS:
        raise ValueError(f'Unknown return-path layer planner: {version}')
    pairs = np.asarray(segment_pairs, dtype=int).reshape(-1, 2)
    points = np.zeros(track_uv.shape[1])
    if len(pairs):
        segments = np.sort(pairs.ravel())
        weights = np.zeros(segments.shape)
        for index, segment in enumerate(segments):
            distances = np.abs(segments-segment)
            weights[index] = np.min(distances[distances != 0])
        selected = np.zeros(track_uv.shape[1]-1, dtype=bool)
        for left, right in pairs:
            ind1, ind2 = np.where(segments == left)[0], np.where(segments == right)[0]
            if ind1.size > 1 or ind2.size > 1:
                chosen = left if ind1.size > ind2.size else right
            else:
                chosen = left if weights[ind1] < weights[ind2] else right
            selected[chosen] = True
        shifted = np.flatnonzero(selected)
        points[np.unique(np.r_[shifted, shifted+1])] = 1
    plateau, slope = smooth_factors[:2]
    kernel = np.r_[np.arange(1, slope+1), np.full(plateau, slope), np.arange(slope-1, 0, -1)]/slope
    historical = points.copy()
    historical_shift = (np.minimum(np.convolve(points, kernel, mode='same'), 1.)
                        if len(pairs) else points.copy())
    crossings = intersection_points_for_pairs(track_uv, pairs)
    historical_factors = layer_factors_for_crossings(track_uv, pairs, crossings, historical_shift)
    insufficient = np.flatnonzero(np.abs(np.diff(historical_factors, axis=1)).ravel()*abs(normal_shift_length) < diameter)
    not_opposite = np.flatnonzero(~np.isclose(np.abs(np.diff(historical_factors, axis=1)).ravel(), 1., atol=1e-9, rtol=0.))
    needs_plan = insufficient if version == 'historical_then_joint_v1' else not_opposite
    attempted = bool(reassign and diameter > 0 and abs(normal_shift_length) >= diameter and len(needs_plan))
    candidate = None
    support_report = None
    status = 'historical_sufficient' if not len(insufficient) else 'historical_insufficient'
    if not reassign:
        status = 'reassignment_disabled'
    if not len(pairs):
        status = 'no_crossings'
    if attempted:
        candidate = crossing_shift_points(pairs, points, len(kernel))
        status = 'joint_incompatible' if candidate is None else 'joint_applied'
        if candidate is None and version != 'historical_then_joint_v1':
            from .crossing_layer_support import exact_support_shift_points
            candidate, support_report = exact_support_shift_points(pairs, points, kernel)
            if candidate is not None:
                status = 'joint_exact_support_applied'
        if candidate is not None:
            points = candidate
    shift = np.minimum(np.convolve(points, kernel, mode='same'), 1.) if len(pairs) else points.copy()
    factors = layer_factors_for_crossings(track_uv, pairs, crossings, shift)
    residual = np.flatnonzero(np.abs(np.diff(factors, axis=1)).ravel()*abs(normal_shift_length) < diameter)
    report = dict(algorithm=version, status=status, reassignment_enabled=bool(reassign),
        joint_attempted=attempted, joint_applied=candidate is not None,
        crossing_count=len(pairs), historical_insufficient_crossings=insufficient.tolist(),
        residual_insufficient_crossings=residual.tolist(),
        changed_selection_stations=int(np.count_nonzero(points != historical)),
        changed_shift_stations=int(np.count_nonzero(shift != historical_shift)),
        kernel_samples=len(kernel), smoothing_units='samples',
        normal_shift_length_m=float(normal_shift_length), real_wire_diameter_m=float(diameter))
    report['historical_nonopposite_crossings'] = not_opposite.tolist()
    report['residual_nonopposite_crossings'] = np.flatnonzero(~np.isclose(
        np.abs(np.diff(factors, axis=1)).ravel(), 1., atol=1e-9, rtol=0.)).tolist()
    if support_report is not None:
        report['exact_support_assignment'] = support_report
    if status == 'joint_incompatible':
        report['grouping_conflict'] = crossing_group_conflict(pairs, len(kernel))
    return dict(historical_points=historical, historical_shift=historical_shift,
        historical_factors=historical_factors, points=points, shift=shift, factors=factors,
        kernel=kernel, joint_points=np.array([]) if candidate is None else candidate,
        report=report)


def shift_return_paths(coil_parts: List[CoilPart], input_args):
    """
    Shifts and returns wire paths for coil parts while avoiding wire intersections.

    Initialises the following properties of a CoilPart:
        - shift_array
        - points_to_shift

    Depends on the following properties of the CoilParts:
        - coil_mesh
        - wire_path

    Depends on the following input_args:
        - skip_normal_shift
        - normal_shift_smooth_factors
        - normal_shift_length
        - smooth_factor

    Updates the following properties of a CoilPart:
        - wire_path

    Args:
        coil_parts (List[CoilPart]): List of CoilPart structures containing coil_mesh.
        input_args: Input arguments structure.

    Returns:
        List[CoilPart]: List of CoilPart structures with updated wire paths and shift information.
    """

    if not input_args.skip_normal_shift:
        smooth_factors = input_args.normal_shift_smooth_factors
        normal_shift_length = input_args.normal_shift_length
        for part_ind in range(len(coil_parts)):
            coil_part = coil_parts[part_ind]
            coil_mesh = coil_part.coil_mesh
            part_vertices = coil_mesh.get_vertices()  # part_mesh.vertices
            part_faces = coil_mesh.get_faces()  # part_mesh.faces
            wire_path_out = coil_part.wire_path
            trace = None
            if getattr(input_args, 'save_return_path_trace', False):
                # A routing retry has its own effective cut width/side. Keep
                # those arguments on the selected part, not the requested args
                # later passed to the outer pipeline's archive writer.
                coil_part.return_path_effective_args = deepcopy(vars(input_args))
                trace = dict(input_v=wire_path_out.v.copy(), input_uv=wire_path_out.uv.copy(),
                    mesh_vertices=part_vertices.copy(), mesh_faces=part_faces.copy(), mesh_uv=coil_mesh.uv.copy())
            # part_mesh = coil_mesh.trimesh_obj

            mesh_2d = Mesh(vertices=coil_mesh.uv, faces=part_faces)

            # Delete superimposing points
            diff = np.diff(wire_path_out.v, axis=1)
            points_to_delete = np.concatenate((np.linalg.norm(diff, axis=0), [1]))
            indices_to_delete = np.where(points_to_delete == 0)
            wire_path_out.uv = np.delete(wire_path_out.uv, indices_to_delete, axis=1)
            wire_path_out.v = np.delete(wire_path_out.v, indices_to_delete, axis=1)

            if input_args.smooth_factor > 1:
                # Apply smoothing to the wire path
                wire_path_out.uv = smooth_track_by_folding(wire_path_out.uv, input_args.smooth_factor)
                wire_path_out.v, wire_path_out.uv = coil_mesh.uv_to_xyz(wire_path_out.uv, coil_mesh.uv)

            if np.all(wire_path_out.uv[:, -1] == wire_path_out.uv[:, 0]):
                wire_path_out.add_uv(wire_path_out.uv[:, :1])
                wire_path_out.add_v(wire_path_out.v[:, :1])

            # Detect wire crossings
            cross_points, cross_segments = InterX(wire_path_out.uv)

            # Preserve a compact description of the crossings before later
            # steps delete path points.  The application uses this metadata to
            # identify three-or-more branches competing for the same location.
            cross_segments = np.asarray(cross_segments, dtype=int)
            if cross_segments.size == 0:
                cross_segments = np.empty((0, 2), dtype=int)
                coil_part.crossing_points_uv = np.empty((0, 2), dtype=float)
                coil_part.crossing_path_positions = np.empty((0, 2), dtype=float)
                coil_part.crossing_layer_factors = np.empty((0, 2), dtype=float)
            else:
                cross_segments = cross_segments.reshape(-1, 2)
                coil_part.crossing_points_uv = intersection_points_for_pairs(
                    wire_path_out.uv, cross_segments)
                segment_lengths = np.linalg.norm(np.diff(wire_path_out.v, axis=1), axis=0)
                point_positions = np.concatenate(([0.0], np.cumsum(segment_lengths)))
                segment_positions = 0.5 * (point_positions[:-1] + point_positions[1:])
                coil_part.crossing_path_positions = segment_positions[cross_segments]
            coil_part.crossing_segments = cross_segments

            plan = plan_return_path_layers(wire_path_out.uv, cross_segments, smooth_factors,
                normal_shift_length, float(getattr(input_args, 'conductor_thickness', 0.)),
                reassign=getattr(input_args, 'reassign_crossing_layers', True))
            coil_part.return_path_report = plan['report']
            coil_part.shift_array = plan['shift']
            coil_part.points_to_shift = plan['points'].astype(int)
            coil_part.crossing_layer_factors = plan['factors']
            if trace is not None:
                trace.update(surface_v=wire_path_out.v.copy(), surface_uv=wire_path_out.uv.copy(),
                    crossing_segments=cross_segments.copy(), crossing_points_uv=coil_part.crossing_points_uv.copy(),
                    historical_points=plan['historical_points'], historical_shift=plan['historical_shift'],
                    historical_factors=plan['historical_factors'], selected_points=plan['points'],
                    selected_shift=plan['shift'], selected_factors=plan['factors'],
                    joint_points=plan['joint_points'], kernel=plan['kernel'],
                    effective_normals=np.zeros_like(wire_path_out.v))

            if cross_segments.size != 0:
                points_to_shift, shift_array = plan['points'], plan['shift']

                vertex_normal = coil_mesh.vertex_normals()  # vertexNormal(part_faces, part_vertices)

                if np.mean(np.dot(vertex_normal.T, part_vertices - np.mean(part_vertices, axis=0))) < 0:
                    vertex_normal = -vertex_normal

                normal_vectors_wire_path = np.zeros((3, wire_path_out.uv.shape[1]))

                parameters = getattr(input_args, 'cylinder_mesh_parameter_list', [])
                if (getattr(input_args, 'surface_is_cylinder_flag', False)
                        and len(parameters) == 8):
                    # Generated cylinders have exact radial normals. Avoid a
                    # UV triangle search for every station on every retry.
                    rotation = calc_3d_rotation_matrix_by_vector(
                        np.asarray(parameters[4:7]), parameters[7])
                    local = wire_path_out.v.T @ rotation.T
                    local[:, 2] = 0.
                    local /= np.maximum(np.linalg.norm(local, axis=1), 1e-20)[:, None]
                    normal_vectors_wire_path = (local @ rotation).T
                else:
                    for point_ind in range(wire_path_out.uv.shape[1]):
                        point = wire_path_out.uv[:, point_ind]
                        face_index, barycentric = mesh_2d.get_face_index(point)

                        if face_index is not None and face_index >= 0:
                            nodes_target_triangle = part_faces[face_index]
                            node_normals_target_triangle = vertex_normal[nodes_target_triangle]
                            normal_vectors_wire_path[:, point_ind] = np.mean(node_normals_target_triangle, axis=0)
                        else:
                            if point_ind == 0:
                                normal_vectors_wire_path[:, point_ind] = normal_vectors_wire_path[:, point_ind + 1]
                            else:
                                normal_vectors_wire_path[:, point_ind] = normal_vectors_wire_path[:, point_ind - 1]

                if plan['report']['joint_applied']:
                    log.info('Reassigned neighbouring crossings to separate radial layers.')
                elif plan['report']['status'] == 'joint_incompatible':
                    log.warning('Crossing layer graph is incompatible with two layers at this sample grouping; '
                                'retaining historical selection. This is not a physical impossibility proof.')

                for point_ind in range(wire_path_out.uv.shape[1]):
                    if smooth_factors[2] < point_ind < wire_path_out.uv.shape[1] - smooth_factors[2]:
                        arr4 = normal_vectors_wire_path[:, point_ind -
                                                        smooth_factors[2] // 2: point_ind + smooth_factors[2] // 2 + 1]
                        effective_normal = np.mean(arr4, axis=1)
                    else:
                        effective_normal = normal_vectors_wire_path[:, point_ind]
                    shift_vec = effective_normal * shift_array[point_ind] * normal_shift_length
                    if trace is not None:
                        trace['effective_normals'][:, point_ind] = effective_normal

                    wire_path_out.v[:, point_ind] += shift_vec

                coil_part.shift_array = shift_array
                coil_part.points_to_shift = points_to_shift.astype(int)
                coil_part.wire_path.uv = wire_path_out.uv
                coil_part.wire_path.v = wire_path_out.v
            if trace is not None:
                trace['shifted_v'] = wire_path_out.v.copy()
                trace['shifted_uv'] = wire_path_out.uv.copy()
                coil_part.return_path_trace = trace

    else:
        for part_ind in range(len(coil_parts)):
            coil_part = coil_parts[part_ind]
            num_points = coil_part.wire_path.uv.shape[1]
            coil_part.shift_array = np.zeros(num_points)
            coil_part.points_to_shift = np.zeros(num_points)
            coil_part.return_path_report = dict(algorithm=LAYER_PLANNER_VERSION, status='normal_shift_skipped')

    return coil_parts


def _crossing_layer_graph(pairs, kernel_length):
    segments = np.unique(pairs)
    guard = kernel_length // 2 + 2
    groups = np.r_[0, np.cumsum(np.diff(segments) > guard)]
    pair_groups = groups[np.searchsorted(segments, pairs)]
    graph = [set() for _ in range(int(groups[-1])+1)]
    for left, right in pair_groups:
        graph[left].add(int(right))
        graph[right].add(int(left))
    return segments, groups, pair_groups, graph


def crossing_group_conflict(segment_pairs, kernel_length):
    """Give an odd-cycle witness for this grouping; not a space impossibility proof."""
    pairs = np.asarray(segment_pairs, dtype=int).reshape(-1, 2)
    if not len(pairs):
        return None
    segments, groups, edges, graph = _crossing_layer_graph(pairs, kernel_length)
    colors, parents = {}, {}
    for first in range(len(graph)):
        if first in colors:
            continue
        colors[first], parents[first] = 0, None
        queue = [first]
        for node in queue:
            for neighbor in sorted(graph[node]):
                if neighbor not in colors:
                    colors[neighbor], parents[neighbor] = 1-colors[node], node
                    queue.append(neighbor)
                elif colors[neighbor] == colors[node]:
                    def ancestry(start):
                        chain = []
                        while start is not None:
                            chain.append(start)
                            start = parents[start]
                        return chain
                    left, right = ancestry(node), ancestry(neighbor)
                    common = next(item for item in left if item in right)
                    cycle = left[:left.index(common)+1]+list(reversed(right[:right.index(common)]))
                    cycle_edges = {tuple(sorted((a,b))) for a,b in zip(cycle, cycle[1:]+cycle[:1])}
                    return dict(guard_samples=kernel_length//2+2, odd_cycle_group_ids=cycle,
                        crossing_indices=[i for i, edge in enumerate(edges) if tuple(sorted(edge)) in cycle_edges],
                        group_segments={str(group): segments[groups == group].tolist() for group in cycle},
                        scope='incompatible_with_this_sample_grouping_only')
    return None


def crossing_shift_points(segment_pairs: np.ndarray, previous_points: np.ndarray,
                          kernel_length: int) -> np.ndarray | None:
    """Separate crossing branches whose smoothing windows interact.

    Nearby crossing segments along the wire must share a layer, since a
    plateau or ramp selected at one of them also reaches its neighbours.
    Across each crossing the two branches must have opposite layers. Colour
    that graph jointly, choosing the orientation closest to the old routing.
    An odd cycle (including three competing branches) cannot use two layers;
    return None rather than inventing an additional layer or hiding a contact.
    The final 3-D conductor check still validates ramps and finite wire size.
    """
    pairs = np.asarray(segment_pairs, dtype=int).reshape(-1, 2)
    previous = np.asarray(previous_points, dtype=float)
    if not len(pairs):
        return previous.copy()
    # A selected segment sets both endpoints. Include the half-window's
    # asymmetric support for even kernels and one endpoint on either branch.
    segments, groups, _edges, graph = _crossing_layer_graph(pairs, kernel_length)

    colors = np.full(len(graph), -1, dtype=int)
    for first in range(len(graph)):
        if colors[first] != -1:
            continue
        colors[first] = 0
        pending = [first]
        component = []
        while pending:
            node = pending.pop()
            component.append(node)
            for neighbour in sorted(graph[node]):
                if colors[neighbour] == -1:
                    colors[neighbour] = 1 - colors[node]
                    pending.append(neighbour)
                elif colors[neighbour] == colors[node]:
                    return None
        selected = np.isin(groups, component)
        assigned = colors[groups[selected]]
        old = previous[segments[selected]]
        if np.sum(np.abs(1 - assigned - old)) < np.sum(np.abs(assigned - old)):
            colors[component] = 1 - colors[component]

    shifted = segments[colors[groups] == 1]
    points = np.zeros_like(previous)
    points[np.unique(np.r_[shifted, shifted + 1])] = 1.0
    return points


def intersection_points_for_pairs(track_uv: np.ndarray,
                                  segment_pairs: np.ndarray) -> np.ndarray:
    """Return the 2-D intersection point corresponding to every segment pair."""
    pairs = np.asarray(segment_pairs, dtype=int)
    if pairs.size == 0:
        return np.empty((0, 2), dtype=float)
    pairs = pairs.reshape(-1, 2)

    p = track_uv[:, pairs[:, 0]].T
    r = (track_uv[:, pairs[:, 0] + 1] - track_uv[:, pairs[:, 0]]).T
    q = track_uv[:, pairs[:, 1]].T
    s = (track_uv[:, pairs[:, 1] + 1] - track_uv[:, pairs[:, 1]]).T

    def cross_2d(a, b):
        return a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]

    denominator = cross_2d(r, s)
    if np.any(denominator == 0.0):
        raise ValueError("Crossing segment pair contains parallel segments")
    t = cross_2d(q - p, s) / denominator
    return p + t[:, np.newaxis] * r


def layer_factors_for_crossings(track_uv: np.ndarray,
                                segment_pairs: np.ndarray,
                                crossing_points: np.ndarray,
                                shift_array: np.ndarray) -> np.ndarray:
    """Interpolate each crossed branch's radial-layer factor at its crossing."""
    pairs = np.asarray(segment_pairs, dtype=int)
    if pairs.size == 0:
        return np.empty((0, 2), dtype=float)
    pairs = pairs.reshape(-1, 2)
    points = np.asarray(crossing_points, dtype=float).reshape(-1, 2)
    shifts = np.asarray(shift_array, dtype=float)
    factors = np.empty((len(pairs), 2), dtype=float)

    for pair_index, pair in enumerate(pairs):
        for branch_index, segment_index in enumerate(pair):
            start = track_uv[:, segment_index]
            delta = track_uv[:, segment_index + 1] - start
            denominator = float(np.dot(delta, delta))
            if denominator == 0.0:
                fraction = 0.5
            else:
                fraction = float(np.dot(points[pair_index] - start, delta) / denominator)
                fraction = float(np.clip(fraction, 0.0, 1.0))
            factors[pair_index, branch_index] = (
                (1.0 - fraction) * shifts[segment_index]
                + fraction * shifts[segment_index + 1]
            )
    return factors


def InterX(L1, *varargin, m_debug=None):
    if len(varargin) == 0:
        L2 = L1
        hF = np.less  # Avoid the inclusion of common points
    else:
        L2 = varargin[0]
        hF = np.less_equal

    # Preliminary calculations
    x1 = L1[0, :]
    x2 = L2[0, :]
    y1 = L1[1, :]
    y2 = L2[1, :]
    dx1 = np.diff(x1)
    dy1 = np.diff(y1)
    dx2 = np.diff(x2)
    dy2 = np.diff(y2)

    # Determine 'signed distances'
    S1 = dx1 * y1[:-1] - dy1 * x1[:-1]
    S2 = dx2 * y2[:-1] - dy2 * x2[:-1]

    P10 = np.multiply.outer(dx1, y2)
    P11 = np.multiply.outer(dy1, x2)
    if m_debug is not None:
        P12 = Diff(P10 - P11, S1, [m_debug.diff_x1, m_debug.diff_y1])
    else:
        P12 = Diff(P10 - P11, S1)

    P20 = np.multiply.outer(y1, dx2)
    P21 = np.multiply.outer(x1, dy2)
    if m_debug is not None:
        P22 = Diff((P20 - P21).T, S2.T, [m_debug.diff_x2, m_debug.diff_y2])
    else:
        P22 = Diff((P20 - P21).T, S2.T)

    C1 = hF(P12, 0).astype(int)
    C2 = hF(P22, 0).T.astype(int)

    # Obtain segments where an intersection is expected
    j, i = np.where(C1 & C2)

    if len(i) == 0:
        P = np.zeros((2, 0))
        intersect_edge_inds = []
        return P, intersect_edge_inds

    # Transpose and prepare for output
    # i = i.reshape(-1, 1)
    # dx2 = dx2.reshape(-1, 1); dy2 = dy2.reshape(-1, 1); S2 = S2.reshape(-1, 1)
    L = dy2[j] * dx1[i] - dy1[i] * dx2[j]

    # Filter out non-zero entries to avoid divisions by zero
    non_zero_indices = L.nonzero()
    i = i[non_zero_indices]
    j = j[non_zero_indices]
    L = L[non_zero_indices]

    # Find unique pairs of indices for intersected edges
    # axis 1 is out of bounds for array of dimension 1
    edges = np.vstack((i, j)).T
    sorted_edges = np.sort(edges, axis=1)

    # intersect_edge_inds = np.unique(np.sort(np.concatenate((i, j), axis=1)), axis=0)
    intersect_edge_inds = np.unique(sorted_edges, axis=0)

    # Solve system of equations to get the common points
    arr1 = (dx2[j] * S1[i] - dx1[i] * S2[j]) / L
    arr2 = (dy2[j] * S1[i] - dy1[i] * S2[j]) / L
    combined_arr = np.vstack((arr1, arr2)).T
    P = np.unique(combined_arr, axis=0).T

    return P, intersect_edge_inds


def Diff(x, y):
    """
    Calculate the element-wise differences and products of two input arrays.

    Parameters:
    x (ndarray): Input array with shape (N, M).
    y (ndarray): Input array with shape (N, M-1).

    Returns:
    ndarray: Array with shape (N, M-1) containing element-wise differences and products.
    """
    u = np.empty((x.shape[0], y.shape[0]))
    for i in range(u.shape[0]):
        diff_x = x[i, :-1] - y[i]
        diff_y = x[i, 1:] - y[i]

        u[i] = diff_x * diff_y
    return u
