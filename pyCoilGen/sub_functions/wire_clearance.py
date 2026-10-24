"""Bounded separation of neighbouring turns, preserving cylindrical layers."""

from __future__ import annotations

import time

import numpy as np
from scipy import sparse
from scipy.interpolate import BSpline
from scipy.optimize import linprog
from scipy.spatial import cKDTree
import trimesh

from pyCoilGen.helpers.wire_geometry import closed_wire_path, segment_closest, wire_contact_pairs
from .calc_3d_rotation_matrix_by_vector import calc_3d_rotation_matrix_by_vector


def separate_cylindrical_path(path, diameter, z_bounds, *, max_iterations=24,
                              max_seconds=20., max_displacement=None):
    """Return a fully checked path or the untouched input with a diagnosis.

    Smooth repulsion is applied in the tangent plane of each wire layer.
    Point radii, axial bounds, point order and the number of turns are fixed.
    Never return a partially repaired conductor as a successful result.
    """
    original = np.array(path, dtype=float, copy=True)
    closed = np.linalg.norm(original[0] - original[-1]) <= diameter
    i, j, distances, _ = wire_contact_pairs(original, diameter, closed=closed)
    report = dict(status='unchanged', algorithm='cylindrical_turn_separation_v2',
                  initial_contact_pairs=len(i), remaining_contact_pairs=len(i),
                  initial_minimum_mm=float(distances.min()*1000) if len(i) else None,
                  required_mm=float(diameter*1000), iterations=0,
                  max_displacement_mm=0.)
    if not len(i):
        return original, report
    report['status'] = 'unresolved'
    # Intersecting centerlines need a different layer assignment/topology.
    if distances.min() < .1 * diameter:
        report['reason'] = 'crossing_requires_different_routing'
        return original, report
    radii = np.linalg.norm(original[:, :2], axis=1)
    if (np.any(radii <= 0) or not z_bounds[0] <= z_bounds[1]
            or original[:, 2].min() < z_bounds[0]-1e-10
            or original[:, 2].max() > z_bounds[1]+1e-10):
        report['reason'] = 'unsupported_cylinder'
        return original, report
    limit = diameter / 2 if max_displacement is None else float(max_displacement)
    target = diameter * 1.05
    positions = np.r_[0., np.cumsum(np.linalg.norm(np.diff(original, axis=0), axis=1))]
    current = original.copy()
    start = time.monotonic()
    deadline = start + max_seconds
    # Reserve time/iterations for a joint solution when repulsion through a
    # chain of crowded turns stalls. Local recovery still handles small edits.
    for iteration in range(max_iterations // 2):
        if time.monotonic() - start > max_seconds / 2:
            break
        i, j, distances, _ = wire_contact_pairs(current, target, closed=closed, local_diameter=diameter)
        if not len(i) or distances.min() >= diameter * 1.01:
            report.update(status='repaired', remaining_contact_pairs=0,
                          method='local_repulsion',
                          max_displacement_mm=float(np.linalg.norm(
                              current-original, axis=1).max()*1000),
                          minimum_mm=float(distances.min()*1000) if len(i) else None)
            return current, report
        if len(i) > 20000:
            report['reason'] = 'too_many_contacts'
            break
        _, vectors = segment_closest(current[i], current[i+1], current[j], current[j+1])
        forces, weights = np.zeros_like(current), np.zeros(len(current))
        for a, b, distance, vector in zip(i, j, distances, vectors):
            if distance < 1e-12:
                continue
            movement = vector / distance * (target-distance) * .7
            for index, sign in ((a, -1), (b, 1)):
                middle = (positions[index] + positions[index+1]) / 2
                arc = np.abs(positions-middle)
                if closed:
                    arc = np.minimum(arc, positions[-1]-arc)
                selected = np.flatnonzero(arc < 6*diameter)
                weight = np.exp(-.5*(arc[selected]/(2*diameter))**2)
                forces[selected] += weight[:, None] * movement * sign
                weights[selected] += weight
        forces /= np.maximum(weights, 1)[:, None]
        radial = np.column_stack((current[:, :2] /
                                  np.linalg.norm(current[:, :2], axis=1)[:, None],
                                  np.zeros(len(current))))
        tangent = np.gradient(current, axis=0)
        tangent /= np.maximum(np.linalg.norm(tangent, axis=1), 1e-20)[:, None]
        forces -= np.sum(forces*radial, axis=1)[:, None]*radial
        forces -= np.sum(forces*tangent, axis=1)[:, None]*tangent
        candidate = current + forces
        delta = candidate - original
        delta *= np.minimum(1., limit/np.maximum(np.linalg.norm(delta, axis=1), 1e-20))[:, None]
        candidate = original + delta
        candidate[:, :2] *= radii[:, None] / np.linalg.norm(candidate[:, :2], axis=1)[:, None]
        candidate[:, 2] = np.clip(candidate[:, 2], *z_bounds)
        if np.array_equal(original[0], original[-1]):
            candidate[-1] = candidate[0]
        current = candidate
        report['iterations'] = iteration + 1
    # Explicit final check covers success on the last allowed iteration too.
    i, j, distances, _ = wire_contact_pairs(current, diameter*1.01, closed=closed,
                                           local_diameter=diameter)
    report['best_minimum_mm'] = float(distances.min()*1000) if len(i) else None
    if not len(i):
        report.update(status='repaired', remaining_contact_pairs=0,
                      method='local_repulsion',
                      max_displacement_mm=float(np.linalg.norm(current-original, axis=1).max()*1000))
        return current, report
    # Local forces can cancel in a chain of consecutive crowded turns. Solve
    # their constraints together with one smooth monotone map of axial height.
    # The shared map also moves nearby turns that are currently clear, so a
    # correction cannot simply squeeze the next turn that was left stationary.
    remaining = min(4, max_iterations - report['iterations'])
    axial_limit = 2*diameter if max_displacement is None else float(max_displacement)
    if remaining > 0 and time.monotonic() < deadline:
        candidate, attempt = _redistribute_axially(
            original, diameter, z_bounds, axial_limit, remaining, deadline)
        report['iterations'] += attempt['iterations']
        report['axial_recovery'] = attempt
        if attempt['status'] == 'repaired':
            report.update(status='repaired', method='axial_turn_redistribution',
                          remaining_contact_pairs=0, minimum_mm=attempt['minimum_mm'],
                          max_displacement_mm=float(np.linalg.norm(
                              candidate-original, axis=1).max()*1000))
            return candidate, report
    report.setdefault('reason', 'clearance_not_reached_within_limits')
    return original, report


def _redistribute_axially(original, diameter, z_bounds, limit, max_iterations, deadline):
    """Fit a bounded cubic height map using all neighbouring turn constraints.

    The map has derivative in [0.5,1.5], preserves XY exactly, cannot fold the
    path or reverse its height order, and maps the cylinder into its bounds.
    Linearized segment constraints are rechecked with exact 3D distances after
    every solve. Only a completely cleared path is returned to the caller.
    """
    attempt = dict(status='unresolved', iterations=0, limit_mm=float(limit*1000))
    if not np.isfinite(limit) or limit <= 0 or z_bounds[0] == z_bounds[1]:
        attempt['reason'] = 'no_axial_displacement_available'
        return original, attempt
    closed = np.linalg.norm(original[0]-original[-1]) <= diameter
    # A cubic spline keeps the displacement smooth between constraint points.
    stations = max(4, int(np.ceil(np.ptp(z_bounds)/diameter)))
    knots = np.r_[[z_bounds[0]]*3, np.linspace(*z_bounds, stations), [z_bounds[1]]*3]
    basis = sparse.csr_matrix(BSpline.design_matrix(np.clip(original[:, 2], *z_bounds), knots, 3))
    count = basis.shape[1]
    coefficients, current = np.zeros(count), original.copy()
    identity = sparse.eye(count, format='csr')
    zero = sparse.csr_matrix((count, count))
    ones = sparse.csr_matrix(-np.ones((count, 1)))
    # Minimize maximum displacement, then weakly prefer zero elsewhere.
    amplitude = sparse.vstack((sparse.hstack((identity, zero, ones)),
                               sparse.hstack((-identity, zero, ones))))
    absolute = sparse.vstack((
        sparse.hstack((identity, -identity, sparse.csr_matrix((count, 1)))),
        sparse.hstack((-identity, -identity, sparse.csr_matrix((count, 1))))))
    greville = np.array([knots[k+1:k+4].mean() for k in range(count)])
    difference = sparse.diags([-np.ones(count-1), np.ones(count-1)],
                             [0, 1], shape=(count-1, count))
    derivative = sparse.hstack((sparse.vstack((difference, -difference)),
                                sparse.csr_matrix((2*(count-1), count+1))))
    derivative_bounds = np.tile(.5*np.diff(greville), 2)
    bounds = [(-limit, limit)]*count + [(0, limit)]*count + [(0, limit)]
    bounds[0], bounds[count-1] = (0, limit), (-limit, 0)
    for iteration in range(max_iterations):
        if time.monotonic() >= deadline:
            attempt['reason'] = 'time_budget_exhausted'
            break
        i, j, distances, _ = wire_contact_pairs(
            current, diameter*2.1, closed=closed, local_diameter=diameter)
        if not len(i) or distances.min() >= diameter*1.01:
            break
        if len(i) > 200000:
            attempt['reason'] = 'too_many_neighbour_constraints'
            break
        _, vectors, a, b = segment_closest(current[i], current[i+1],
                                           current[j], current[j+1], return_parameters=True)
        axial_normal = vectors[:, 2]/np.maximum(distances, 1e-20)
        jacobian = sparse.csr_matrix((len(i), count))
        for indices, weight in ((i, -(1-a)), (i+1, -a), (j, 1-b), (j+1, b)):
            jacobian += basis[indices].multiply((axial_normal*weight)[:, None])
        rhs = diameter*1.025 - distances + jacobian @ coefficients
        contact = sparse.hstack((-jacobian, sparse.csr_matrix((len(i), count+1))))
        available = deadline-time.monotonic()
        if available <= 0:
            attempt['reason'] = 'time_budget_exhausted'
            break
        result = linprog(
            np.r_[np.zeros(count), np.full(count, .001/count), 1.],
            A_ub=sparse.vstack((contact, amplitude, absolute, derivative)),
            b_ub=np.r_[-rhs, np.zeros(4*count), derivative_bounds],
            bounds=bounds, method='highs',
            options={'time_limit': available, 'primal_feasibility_tolerance': 1e-9})
        attempt['iterations'] = iteration+1
        if not result.success:
            attempt['reason'] = ('time_budget_exhausted' if result.status == 1
                                 else 'no_feasible_axial_map_within_limits')
            break
        coefficients = result.x[:count]
        current = original.copy()
        current[:, 2] += basis @ coefficients
    _, _, distances, _ = wire_contact_pairs(current, diameter*1.01,
                                            closed=closed, local_diameter=diameter)
    if (not len(distances) and current[:, 2].min() >= z_bounds[0]-1e-10
            and current[:, 2].max() <= z_bounds[1]+1e-10
            and np.abs(current[:, 2]-original[:, 2]).max() <= limit+1e-10):
        _, _, near_distances, _ = wire_contact_pairs(current, diameter*1.05,
                                                    closed=closed, local_diameter=diameter)
        attempt.update(status='repaired', minimum_mm=float(near_distances.min()*1000)
                       if len(near_distances) else None)
        attempt.pop('reason', None)
        return current, attempt
    attempt.setdefault('reason', 'clearance_not_reached_within_limits')
    return original, attempt


def _updated_uv(mesh, path_local, rotation, selected, diameter):
    """Project changed stations onto actual cylinder triangles for sweep normals."""
    local_vertices = mesh.get_vertices() @ rotation.T
    radius = np.median(np.linalg.norm(local_vertices[:, :2], axis=1))
    projected = path_local[selected].copy()
    projected[:, :2] *= radius/np.linalg.norm(projected[:, :2], axis=1)[:, None]
    projected = projected @ rotation
    triangles = mesh.get_vertices()[mesh.get_faces()]
    candidates = cKDTree(triangles.mean(axis=1)).query(
        projected, k=min(32, len(triangles)))[1]
    candidates = np.asarray(candidates).reshape(len(projected), -1)
    repeated = np.repeat(projected, candidates.shape[1], axis=0)
    closest = trimesh.triangles.closest_point(triangles[candidates.ravel()], repeated)
    distances = np.linalg.norm(closest-repeated, axis=1).reshape(candidates.shape)
    best = distances.argmin(axis=1)
    if np.any(distances[np.arange(len(best)), best] > diameter*.05):
        raise ValueError('Cannot project repaired turns onto the cylinder mesh.')
    faces = candidates[np.arange(len(best)), best]
    closest = closest.reshape(*candidates.shape, 3)[np.arange(len(best)), best]
    barycentric = trimesh.triangles.points_to_barycentric(triangles[faces], closest)
    return np.einsum('ij,ijk->ik', barycentric, mesh.uv[mesh.get_faces()[faces]])


def separate_crossing_branches(path, diameter, z_bounds, *, max_iterations=240,
                               max_seconds=12., smoothing_width=1.):
    """Resolve close crossings in the existing radial envelope, then verify all.

    Unlike tangent-only turn separation this recovery can move branches between
    the available radial layers. It never widens their envelope or the cylinder.
    Each exact distance probe includes every segment changed so far; success
    additionally requires an independent full-path clearance check.
    """
    original = np.array(path, dtype=float, copy=True)
    closed = np.linalg.norm(original[0]-original[-1]) <= diameter
    i, j, distances, positions = wire_contact_pairs(original, diameter, closed=closed)
    report = dict(status='unresolved', method='spatial_crossing_separation', iterations=0,
                  initial_contact_pairs=len(i), remaining_contact_pairs=len(i),
                  initial_minimum_mm=float(distances.min()*1000) if len(i) else None,
                  required_mm=float(diameter*1000), max_displacement_mm=0.)
    if not len(i):
        report.update(status='unchanged', remaining_contact_pairs=0)
        return original, report
    radii = np.linalg.norm(original[:, :2], axis=1)
    lower, upper = radii.min(), radii.max()
    if (lower <= 0 or upper-lower < diameter or not z_bounds[0] <= z_bounds[1]
            or original[:, 2].min() < z_bounds[0]-1e-10
            or original[:, 2].max() > z_bounds[1]+1e-10):
        report['reason'] = 'insufficient_radial_range_for_crossing'
        return original, report
    current = original.copy()
    active_nodes = np.zeros(len(original), dtype=bool)
    active_nodes[np.unique(np.r_[i, i+1, j, j+1])] = True
    target, width = diameter*1.03, diameter*smoothing_width
    start = time.monotonic()
    for iteration in range(max_iterations):
        if time.monotonic()-start >= max_seconds:
            break
        active = np.flatnonzero(active_nodes[:-1] | active_nodes[1:])
        i, j, distances, _ = wire_contact_pairs(
            current, target, closed=closed, local_diameter=diameter, active_segments=active)
        if not len(i) or distances.min() >= diameter*1.01:
            # An active set accelerates iterations; it does not certify success.
            full_i, full_j, full_distances, _ = wire_contact_pairs(
                current, diameter*1.01, closed=closed, local_diameter=diameter)
            if not len(full_i):
                _, _, near, _ = wire_contact_pairs(current, target, closed=closed,
                                                   local_diameter=diameter)
                report.update(status='repaired', remaining_contact_pairs=0,
                              minimum_mm=float(near.min()*1000) if len(near) else None,
                              max_displacement_mm=float(np.linalg.norm(
                                  current-original, axis=1).max()*1000))
                return current, report
            active_nodes[np.unique(np.r_[full_i, full_i+1, full_j, full_j+1])] = True
            continue
        _, vectors = segment_closest(current[i], current[i+1], current[j], current[j+1])
        forces, weights = np.zeros_like(current), np.zeros(len(current))
        for a, b, distance, vector in zip(i, j, distances, vectors):
            if distance <= 1e-12:
                # Coincident stations have no distance gradient. Seed a radial
                # separation in a deterministic direction within the same bounds.
                vector = np.r_[current[a, :2]/np.linalg.norm(current[a, :2]), 0.]
            else:
                vector = vector/distance
            movement = vector*(target-distance)*.8
            for index, sign in ((a, -1), (b, 1)):
                middle = (positions[index]+positions[index+1])/2
                arc = np.abs(positions-middle)
                if closed:
                    arc = np.minimum(arc, positions[-1]-arc)
                selected = np.flatnonzero(arc < 3*width)
                weight = np.exp(-.5*(arc[selected]/width)**2)
                forces[selected] += weight[:, None]*movement*sign
                weights[selected] += weight
        forces /= np.maximum(weights, 1)[:, None]
        tangent = np.gradient(current, axis=0)
        tangent /= np.maximum(np.linalg.norm(tangent, axis=1), 1e-20)[:, None]
        forces -= np.sum(forces*tangent, axis=1)[:, None]*tangent
        candidate = current+forces
        delta = candidate-original
        delta *= np.minimum(1., 3*diameter/np.maximum(np.linalg.norm(delta, axis=1), 1e-20))[:, None]
        candidate = original+delta
        radius = np.linalg.norm(candidate[:, :2], axis=1)
        candidate[:, :2] *= np.clip(radius, lower, upper)[:, None]/radius[:, None]
        candidate[:, 2] = np.clip(candidate[:, 2], *z_bounds)
        if np.array_equal(original[0], original[-1]):
            candidate[-1] = candidate[0]
        active_nodes |= np.linalg.norm(candidate-original, axis=1) > 1e-12
        current = candidate
        report['iterations'] = iteration+1
    report['reason'] = 'crossing_recovery_limits_reached'
    return original, report


def ensure_wire_clearance(part, input_args):
    """Opt-in application step, after path pruning and before sweep/field evaluation."""
    if not getattr(input_args, 'auto_wire_clearance', False):
        return
    parameters = getattr(input_args, 'cylinder_mesh_parameter_list', [])
    if not getattr(input_args, 'surface_is_cylinder_flag', False) or len(parameters) != 8:
        part.clearance_report = dict(status='unsupported', reason='requires_generated_cylinder')
        return
    rotation = calc_3d_rotation_matrix_by_vector(np.asarray(parameters[4:7]), parameters[7])
    local = part.wire_path.v.T @ rotation.T
    # The sweep always connects the last ring to the first. Repair that same
    # loop, including a closing edge longer than the conductor diameter.
    working = closed_wire_path(local)
    vertices = part.coil_mesh.get_vertices() @ rotation.T
    repaired, report = separate_cylindrical_path(
        working, float(input_args.conductor_thickness),
        (float(vertices[:, 2].min()), float(vertices[:, 2].max())))
    if report.get('reason') == 'crossing_requires_different_routing':
        initial = report
        for width in (1., .5):
            repaired, report = separate_crossing_branches(
                working, float(input_args.conductor_thickness),
                (float(vertices[:, 2].min()), float(vertices[:, 2].max())),
                max_seconds=12., smoothing_width=width)
            if report['status'] == 'repaired':
                report['algorithm'] = 'bounded_spatial_crossing_recovery_v1'
                report['smoothing_width_diameters'] = width
                break
        else:
            initial['spatial_recovery'] = report
            report = initial
    report['closed_loop'] = True
    if report['status'] == 'repaired':
        # Keep the original path/ring correspondence. The sweep itself creates
        # the validated closing edge; it needs no extra coincident section.
        repaired = repaired[:len(local)]
        selected = np.flatnonzero(np.linalg.norm(repaired-local, axis=1) > 1e-12)
        try:
            uv = _updated_uv(part.coil_mesh, repaired, rotation, selected,
                             float(input_args.conductor_thickness))
        except ValueError as exc:
            report.update(status='unresolved', reason=str(exc), max_displacement_mm=0.,
                          remaining_contact_pairs=report['initial_contact_pairs'])
        else:
            part.wire_path.v = (repaired @ rotation).T
            part.wire_path.uv[:, selected] = uv.T
    part.clearance_report = report
