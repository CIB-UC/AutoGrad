"""Validate and assemble selected concentric formers without moving their coils.

Pipeline conductor STLs use metres; former STLs follow ``output_in_mm``.
All CAD booleans here use millimetres. Final STL files use millimetres and the
GLB scene uses metres, keeping the physical XYZ frame and longitudinal Z.
"""

from __future__ import annotations

from itertools import combinations
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile

import manifold3d as m3d
import numpy as np
import trimesh

from .shell import export_validated_shell_stl, load_shell_stl
from .paths import infer_gradient_axis


VOLUME_TOL_MM3 = 1e-6
PREFERRED_ANGLES = (202.5, 180.0)
PART_COLORS = {'x': [180, 110, 215, 255], 'y': [220, 190, 70, 255],
               'z': [80, 185, 210, 255]}


class AssemblyFeasibilityError(RuntimeError):
    """The calculated parts cannot form a validated assembly as configured."""


def trimesh_from_manifold(solid):
    """Keep double precision until the explicitly validated STL serialization."""
    mesh = solid.to_mesh64()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3],
                           faces=np.asarray(mesh.tri_verts, dtype=np.int64), process=False)


def _positive(value, name):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f'{name} must be finite and positive.')
    return number


def _configuration(batch, configs=None):
    if configs is None:
        from .batch import build_layer_configs
        configs = build_layer_configs(batch)
    configs = tuple(configs)
    axes = tuple(cfg.gradient_axis for cfg in configs)
    selected = tuple(str(axis).lower() for axis in batch.axis_order)
    if (not axes or len(set(axes)) != len(axes) or not set(axes) <= {'x', 'y', 'z'}
            or axes != selected):
        raise ValueError('Assembly configurations must match the selected gradients in layer order.')
    height = _positive(configs[0].cylinder.height, 'Cylinder height')
    roi = np.array([configs[0].target.rx, configs[0].target.ry, configs[0].target.rz])
    if not np.all(np.isfinite(roi)) or np.any(roi <= 0):
        raise ValueError('Assembly ROI semi-axes must be finite and positive.')
    for cfg in configs:
        if (not np.allclose(cfg.rotated_cylinder_axis, [0, 0, 1], atol=1e-10)
                or not math.isclose(cfg.cylinder.height, height, abs_tol=1e-10)
                or cfg.b0_direction != configs[0].b0_direction
                or not np.allclose([cfg.target.rx, cfg.target.ry, cfg.target.rz], roi,
                                   atol=1e-12, rtol=0)):
            raise ValueError('Assembly layers must share longitudinal Z, height, B0 and ROI.')
        if cfg.shell.use_custom_stl or cfg.shell_inner_radius <= 0:
            raise ValueError('Assembly requires generated cylindrical formers with a positive bore.')
    for inner, outer in zip(configs, configs[1:]):
        if outer.shell_inner_radius < inner.shell_outer_radius - 1e-10:
            raise ValueError('Former walls overlap or are not ordered inside to outside.')
    if batch.include_keys and len(configs) > 1:
        length = _positive(batch.key_length, 'Key length')
        width = _positive(batch.key_width, 'Key width')
        clearance = _positive(batch.fit_clearance, 'Key fit clearance')
        if length + clearance >= height or clearance >= min(length, width):
            raise ValueError('Key dimensions or fit clearance do not fit the cylinder.')
    return configs


def _radial_box(r_min, r_max, width, z_min, z_max, angle_deg):
    angle = np.deg2rad(angle_deg)
    c, s = float(np.cos(angle)), float(np.sin(angle))
    transform = np.array([[c, -s, 0, c * (r_min + r_max) / 2],
                          [s, c, 0, s * (r_min + r_max) / 2],
                          [0, 0, 1, (z_min + z_max) / 2]])
    return m3d.Manifold.cube([r_max - r_min, width, z_max - z_min], center=True).transform(transform)


def _key_manifolds(batch, inner, outer, angle_deg):
    width, length, clearance = (1000 * float(value) for value in
                                (batch.key_width, batch.key_length, batch.fit_clearance))
    z_start = -500 * float(inner.cylinder.height)
    host_outer = 1000 * inner.shell_outer_radius
    host_wall = 1000 * inner.shell_wall_thickness
    r_start = host_outer - min(1.0, host_wall / 2)
    tip = 1000 * outer.shell_outer_radius
    if r_start <= 0 or width >= 2 * r_start:
        raise ValueError('Key width does not fit the inner former radius.')
    # The annular tip is flush with the receiving former's outer cylinder.
    segments = max(256, int(inner.shell.circular_segments), int(outer.shell.circular_segments))
    cylinder = m3d.Manifold.cylinder(length, tip, circular_segments=segments,
                                    center=True).translate([0, 0, z_start + length / 2])
    male = cylinder ^ _radial_box(r_start, tip + 1, width, z_start,
                                  z_start + length, angle_deg)
    # Extend beyond the end and both radial faces so the slot remains open.
    female = _radial_box(1000 * outer.shell_inner_radius - clearance - .1,
                         tip + clearance + .1, width + 2 * clearance,
                         z_start - clearance, z_start + length + clearance, angle_deg)
    return male, female


def key_pair_meshes(batch, inner_cfg, outer_cfg, angle_deg):
    """Return the male and female preview meshes in mm for an actual angle."""
    male, female = _key_manifolds(batch, inner_cfg, outer_cfg, angle_deg)
    return trimesh_from_manifold(male), trimesh_from_manifold(female)


def nominal_key_pairs(batch, configs=None):
    """Nominal preview only; final azimuths are selected against real conductors."""
    if not batch.include_keys:
        return []
    configs = _configuration(batch, configs)
    result = []
    for index, (inner, outer) in enumerate(zip(configs, configs[1:])):
        male, female = key_pair_meshes(batch, inner, outer, PREFERRED_ANGLES[index])
        result.append({'inner_axis': inner.gradient_axis, 'outer_axis': outer.gradient_axis,
                       'angle_deg': PREFERRED_ANGLES[index], 'male_mm': male, 'female_mm': female})
    return result


def _solid(mesh, label, *, one_part=False):
    if (not len(mesh.faces) or not np.all(np.isfinite(mesh.vertices))
            or not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0):
        raise RuntimeError(f'{label}: mesh is not a closed, consistently oriented solid.')
    solid = m3d.Manifold(m3d.Mesh64(
        np.require(mesh.vertices, dtype=np.float64, requirements=['C', 'W']),
        np.require(mesh.faces, dtype=np.uint64, requirements=['C', 'W'])))
    if solid.status() != m3d.Error.NoError or solid.is_empty() or solid.volume() <= 0:
        raise RuntimeError(f'{label}: invalid CAD solid ({solid.status()}).')
    if one_part and len(solid.decompose()) != 1:
        raise RuntimeError(f'{label}: the former must be one connected printable part.')
    return solid


def _intersection_volume(first, second):
    a, b = np.asarray(first.bounding_box()), np.asarray(second.bounding_box())
    if np.any(a[3:] <= b[:3]) or np.any(b[3:] <= a[:3]):
        return 0.0
    intersection = first ^ second
    if intersection.status() != m3d.Error.NoError:
        raise RuntimeError(f'CAD intersection failed: {intersection.status()}.')
    volume = max(0.0, float(intersection.volume()))
    return 0.0 if volume <= VOLUME_TOL_MM3 else volume


def _check_pair(first, second, kind, axes, checks):
    volume = _intersection_volume(first, second)
    if volume:
        labels = ' / '.join('G' + axis.upper() if axis in 'xyz' else axis for axis in axes)
        raise AssemblyFeasibilityError(f'Assembly interference: {kind} {labels} overlap by {volume:.6g} mm³. '
                           'Individual designs were kept; no complete assembly was published.')
    checks.append({'kind': kind, 'axes': list(axes), 'intersection_mm3': 0.0})


def _roi_solid(cfg):
    # Scaling by the smallest face-plane distance makes the polyhedron contain
    # the analytic unit sphere. The subsequent affine scale contains the exact
    # ellipsoid, unlike an inscribed triangulation which could miss an intrusion.
    sphere = m3d.Manifold.sphere(1, circular_segments=128)
    mesh = trimesh_from_manifold(sphere)
    triangles = mesh.triangles
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    distance = np.abs(np.einsum('ij,ij->i', normals, triangles[:, 0]))
    inflation = 1 / float(distance.min())
    radii = 1000 * np.array([cfg.target.rx, cfg.target.ry, cfg.target.rz])
    return sphere.scale(radii * inflation), inflation


def _one_output(root, group, pattern, label):
    from .output_layout import locate
    folder = locate(root, group)
    candidates = sorted(folder.glob(pattern)) if folder.is_dir() else sorted(root.glob(pattern))
    if len(candidates) != 1:
        raise RuntimeError(f'{label}: expected one {pattern} in {folder}; found {len(candidates)}.')
    return candidates[0]


def _load_layer(cfg, result):
    root = Path(result.output_dir).resolve()
    if getattr(result, 'discarded', False):
        raise RuntimeError(f'G{cfg.gradient_axis.upper()} was discarded; assembly cannot be completed.')
    conductor_path = _one_output(root, 'leads', '*_with_leads*.stl', 'Final conductor')
    former_path = _one_output(root, 'mold', '*.stl', 'Former')
    if any(infer_gradient_axis(str(path)) not in (None, cfg.gradient_axis)
           for path in (conductor_path, former_path)):
        raise RuntimeError(f'G{cfg.gradient_axis.upper()}: output filenames belong to a different gradient axis.')
    conductor = load_shell_stl(conductor_path, units='m')
    conductor.vertices *= 1000
    former = load_shell_stl(former_path, units='mm' if cfg.shell.output_in_mm else 'm')
    if not cfg.shell.output_in_mm:
        former.vertices *= 1000
    axial = former.bounds[:, 2]
    if not np.allclose(axial, [-500 * cfg.cylinder.height, 500 * cfg.cylinder.height],
                       atol=.02, rtol=0):
        raise RuntimeError(f'G{cfg.gradient_axis.upper()}: former height/frame does not match its configuration.')
    source = {'axis': cfg.gradient_axis, 'conductor_path': str(conductor_path),
              'conductor_sha256': hashlib.sha256(conductor_path.read_bytes()).hexdigest(),
              'former_path': str(former_path),
              'former_sha256': hashlib.sha256(former_path.read_bytes()).hexdigest()}
    return (_solid(former, f'G{cfg.gradient_axis.upper()} former', one_part=True),
            _solid(conductor, f'G{cfg.gradient_axis.upper()} final conductor'), source)


def _current_path(cfg, source):
    """Use the same hash-bound real current path as field/FastHenry checks."""
    from .leads import current_path_path
    filename = Path(current_path_path(source['conductor_path']))
    if not filename.exists():
        return None  # Older inputs retain the conservative groove-solid check.
    with np.load(filename, allow_pickle=False) as saved:
        if (str(saved['with_leads_sha256'].item()) != source['conductor_sha256']
                or str(saved['units'].item()) != 'm'
                or str(saved['coordinate_frame'].item()) != 'physical_xyz'
                or str(saved['gradient_axis'].item()) != cfg.gradient_axis
                or str(saved['b0_direction'].item()) != cfg.b0_direction):
            raise RuntimeError('Final current path does not match the assembly conductor or physical coordinates.')
        path = np.asarray(saved['path'], dtype=float) * 1000
    if path.ndim != 2 or path.shape[1] != 3 or len(path) < 2 or not np.all(np.isfinite(path)):
        raise RuntimeError('Final conductor path must contain finite XYZ points.')
    return path


def _check_conductors(configs, conductors, roi, current_paths=None):
    from .lead_surface import near_segment_pairs
    checks = []
    for i, j in combinations(range(len(configs)), 2):
        if current_paths is not None and current_paths[i] is not None and current_paths[j] is not None:
            # The with_leads STL is the deformed groove subtraction tool, not
            # the round electrical cable. Segment capsules bound the real
            # round-wire surface, including every retained winding and lead.
            radius_sum = 500 * (configs[i].wire.conductor_width + configs[j].wire.conductor_width)
            _a, _b, distances = near_segment_pairs(current_paths[i], current_paths[j], radius_sum)
            clearance = float(distances.min() - radius_sum) if len(distances) else 0.0
            axes = [configs[i].gradient_axis, configs[j].gradient_axis]
            if clearance < -1e-6:
                raise AssemblyFeasibilityError(f'Assembly interference: round conductor / conductor '
                                   f'G{axes[0].upper()} / G{axes[1].upper()} have '
                                   f'{-clearance:.6g} mm of surface overlap. Individual designs were kept.')
            checks.append({'kind': 'conductor / conductor', 'axes': axes,
                           'model': 'round_wire_segment_capsules', 'intersection_mm3': 0.0,
                           'surface_clearance_lower_bound_mm': max(0.0, clearance)})
        else:
            _check_pair(conductors[i], conductors[j], 'conductor / conductor',
                        (configs[i].gradient_axis, configs[j].gradient_axis), checks)
    for cfg, conductor in zip(configs, conductors):
        _check_pair(conductor, roi, 'conductor / ROI', (cfg.gradient_axis, 'ROI'), checks)
    return checks


def _check_formers(configs, formers, conductors, roi):
    checks = []
    for i, j in combinations(range(len(configs)), 2):
        _check_pair(formers[i], formers[j], 'former / former',
                    (configs[i].gradient_axis, configs[j].gradient_axis), checks)
    for i, cfg in enumerate(configs):
        _check_pair(formers[i], roi, 'former / ROI', (cfg.gradient_axis, 'ROI'), checks)
        for j, other in enumerate(configs):
            if i != j:
                _check_pair(conductors[i], formers[j], 'conductor / other former',
                            (cfg.gradient_axis, other.gradient_axis), checks)
    return checks


def _candidate_angles(preferred):
    yield preferred
    for step in range(1, 24):
        yield (preferred + 7.5 * step) % 360
        yield (preferred - 7.5 * step) % 360
    yield (preferred + 180) % 360


def _interface_record(batch, inner, outer, angle):
    return {'inner_axis': inner.gradient_axis, 'outer_axis': outer.gradient_axis,
            'angle_deg': float(angle), 'male_width_mm': 1000 * batch.key_width,
            'female_width_mm': 1000 * (batch.key_width + 2 * batch.fit_clearance),
            'male_length_mm': 1000 * batch.key_length,
            'female_length_mm': 1000 * (batch.key_length + batch.fit_clearance),
            'side_clearance_mm': 1000 * batch.fit_clearance,
            'axial_clearance_mm': 1000 * batch.fit_clearance,
            'z_start_mm': -500 * inner.cylinder.height,
            'inner_radius_mm': 1000 * inner.shell_outer_radius,
            'outer_radius_mm': 1000 * outer.shell_outer_radius,
            'embed_radius_mm': 1000 * inner.shell_outer_radius -
                               min(1.0, 500 * inner.shell_wall_thickness)}


def _mark_formers(batch, configs, formers):
    """Choose one B0 side for selected layers and reserve it for key search."""
    if not batch.include_b0_markers:
        return formers, [], {'enabled': False}
    from .shell_marker import mark_shell_b0, marker_radial_direction, MarkerPlacementError

    radial, transverse = marker_radial_direction(configs[0])
    for side in (1, -1):
        marked, widths = [], []
        tangent = np.cross([0., 0., 1.], radial)
        try:
            for cfg, former in zip(configs, formers):
                marker_cfg = deepcopy(cfg)
                marker_cfg.shell.b0_marker = True
                # Reuse the pipeline's geometry, which expects metres.
                original_m = former.scale((.001, .001, .001))
                marked_m = mark_shell_b0([('shell', original_m)], marker_cfg, side=side)[0][1]
                removed = trimesh_from_manifold(original_m - marked_m)
                widths.append(float(np.ptp(removed.vertices @ tangent)) * 1000)
                marked.append(marked_m.scale((1000., 1000., 1000.)))
        except MarkerPlacementError:
            continue
        break
    else:
        raise MarkerPlacementError(
            'No common clear B0 marker position exists for the selected gradients. '
            'Disable the batch B0 marks or leave a clear rim on the same B0 side for all selected gradients.')

    direction = side * radial
    angle = float(np.rad2deg(np.arctan2(direction[1], direction[0])) % 360)
    # Reserve the whole radial line, including the receiving slots, with half
    # a marker width of clearance on each side. An actual cavity alone would
    # not catch an outer-edge key at the same azimuth as an end-face mark.
    width = max(widths)
    height = 1000 * configs[0].cylinder.height
    radius = 1000 * configs[-1].shell_outer_radius
    keepout = _radial_box(0, radius + width, 2 * width, -height/2 - width,
                          height/2 + width, angle)
    print(f'  Batch B0 marks aligned at {angle:.6g} degrees; reserving their azimuth for keys.', flush=True)
    return marked, [keepout], {
        'enabled': True, 'common_side': side, 'radial_direction': direction.tolist(),
        'angle_deg': angle, 'placement': 'end_faces' if transverse else 'outer_wall',
        'key_clearance_mm': width / 2, 'keepout_width_mm': 2 * width,
        'layer_axes': [cfg.gradient_axis for cfg in configs],
    }


def _choose_keys(batch, configs, formers, conductors, marker_keepouts=()):
    """Deterministic joint search; coil geometry and its azimuth stay unchanged."""
    def search(index, selected):
        if index == len(configs) - 1:
            return selected
        inner, outer = configs[index:index + 2]
        for angle in _candidate_angles(PREFERRED_ANGLES[index]):
            male, female = _key_manifolds(batch, inner, outer, angle)
            if any(_intersection_volume(feature, keepout)
                   for feature in (male, female) for keepout in marker_keepouts):
                continue
            if not _intersection_volume(male, formers[index]):
                continue
            if any(_intersection_volume(feature, conductor)
                   for feature in (male, female) for conductor in conductors):
                continue
            if any(_intersection_volume(feature, prior_feature)
                   for feature in (male, female) for prior in selected
                   for prior_feature in prior[:2]):
                continue
            choice = search(index + 1, selected + [(male, female, angle)])
            if choice is not None:
                return choice
        return None

    selected = search(0, [])
    if selected is None:
        raise AssemblyFeasibilityError('No safe key azimuth was found without crossing a conductor, B0 mark or another key. '
                           'Individual designs were kept; no complete assembly was published.')
    final = list(formers)
    interfaces = []
    for index, (male, female, angle) in enumerate(selected):
        final[index] = final[index] + male
        final[index + 1] = final[index + 1] - female
        interfaces.append(_interface_record(batch, configs[index], configs[index + 1], angle))
    for cfg, former in zip(configs, final):
        if (former.status() != m3d.Error.NoError or former.is_empty()
                or len(former.decompose()) != 1):
            raise RuntimeError(f'G{cfg.gradient_axis.upper()}: key operation did not leave one valid former.')
    return final, interfaces


def finalize_batch(batch, configs, results):
    """Publish ``Conjunto/`` only after validating the complete physical set.

    Individual pipeline files are read only. Failure leaves them available and
    removes this function's unpublished staging directory. The checks also run
    when keys are disabled.
    """
    configs = _configuration(batch, configs)
    if len(results) != len(configs):
        raise ValueError('Assembly requires a completed pipeline result for each selected gradient.')
    root = Path(batch.output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    from .output_layout import name, variants
    language = configs[0].output_language
    destination = root / name('assembly', language)
    if any((root / item).exists() for item in variants('assembly')):
        raise FileExistsError('Assembly already exists; refusing to overwrite.')
    if destination.exists():
        raise FileExistsError(f'Assembly already exists; refusing to overwrite: {destination}')
    loaded = [_load_layer(cfg, result) for cfg, result in zip(configs, results)]
    formers, conductors, sources = map(list, zip(*loaded))
    roi, roi_inflation = _roi_solid(configs[0])
    current_paths = [_current_path(cfg, source) for cfg, source in zip(configs, sources)]
    conductor_checks = _check_conductors(configs, conductors, roi, current_paths)
    _check_formers(configs, formers, conductors, roi)
    formers, marker_keepouts, marker_record = _mark_formers(batch, configs, formers)
    interfaces = []
    if batch.include_keys and len(configs) > 1:
        print('  Checking assembly key positions against all final conductors...', flush=True)
        formers, interfaces = _choose_keys(batch, configs, formers, conductors, marker_keepouts)

    staging = Path(tempfile.mkdtemp(prefix='.assembly-', dir=root))
    try:
        part_paths, exported, scene = {}, [], trimesh.Scene()
        for cfg, former in zip(configs, formers):
            filename = f"G{cfg.gradient_axis}_{'molde' if language == 'es' else 'mold'}.stl"
            mesh = export_validated_shell_stl(trimesh_from_manifold(former), staging / filename)
            exported.append(_solid(mesh, f'G{cfg.gradient_axis.upper()} exported former', one_part=True))
            part_paths[cfg.gradient_axis] = str(destination / filename)
            display = mesh.copy()
            display.vertices *= .001
            display.visual.face_colors = PART_COLORS[cfg.gradient_axis]
            scene.add_geometry(display, node_name=f'G{cfg.gradient_axis}', geom_name=f'G{cfg.gradient_axis}')
        checks = conductor_checks + _check_formers(configs, exported, conductors, roi)
        scene.metadata.update({'units': 'm', 'coordinate_frame': 'physical_xyz',
                               'longitudinal_axis': 'z'})
        scene.units = 'm'
        scene_name, report_name = name('scene', language), name('keys', language)
        (staging / scene_name).write_bytes(scene.export(file_type='glb'))
        reloaded = trimesh.load(staging / scene_name, force='scene')
        if len(reloaded.geometry) != len(configs) or not np.allclose(reloaded.bounds, scene.bounds, atol=1e-7):
            raise RuntimeError('Exported assembly GLB did not preserve the selected physical geometries.')
        report = {'format_version': 1, 'status': 'complete', 'units': 'mm',
                  'conductor_geometry_model': ('round_wire_segment_capsules'
                                               if all(path is not None for path in current_paths)
                                               else 'manufacturing_groove_envelope_legacy'),
                  'mold_and_key_clearance_model': 'manufacturing_groove_envelope',
                  'scene_units': 'm', 'coordinate_frame': 'physical_xyz',
                  'longitudinal_axis': 'z', 'angle_reference': '+X towards +Y about +Z',
                  'layer_order': [cfg.gradient_axis for cfg in configs],
                  'b0_direction': configs[0].b0_direction,
                  'roi_mm': [1000 * configs[0].target.rx, 1000 * configs[0].target.ry,
                             1000 * configs[0].target.rz],
                  'roi_conservative_scale': roi_inflation,
                  'intersection_tolerance_mm3': VOLUME_TOL_MM3,
                  'include_keys': bool(batch.include_keys), 'interfaces': interfaces,
                  'b0_markers': marker_record,
                  'checks': checks, 'sources': sources, 'part_paths': part_paths,
                  'scene_path': str(destination / scene_name),
                  'report_path': str(destination / report_name),
                  'assembly_direction': '+Z from the open slots at the negative Z end',
                  'retention': 'Axial stop towards +Z; withdrawal towards -Z remains possible.',
                  'antenna_slot': False}
        (staging / report_name).write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                                     allow_nan=False) + '\n', encoding='utf-8')
        staging.replace(destination)
        print(f'  Assembly validated: {len(configs)} formers, final conductors and shared ROI.', flush=True)
        return {'part_paths': part_paths, 'scene_path': report['scene_path'],
                'report_path': report['report_path'], 'interfaces': interfaces,
                'b0_markers': marker_record,
                'units': 'mm', 'scene_units': 'm', 'coordinate_frame': 'physical_xyz'}
    finally:
        if staging.exists():
            if staging.resolve().parent != root:
                raise RuntimeError('Refusing to remove staging outside the batch output folder.')
            shutil.rmtree(staging)
