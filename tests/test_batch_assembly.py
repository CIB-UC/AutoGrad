"""Physical CAD checks and short, open-ended anti-rotation keys."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import manifold3d as m3d
import numpy as np
import pytest
import trimesh

from halbach_coils.coilgen import assembly
from halbach_coils.coilgen.batch import BatchConfig, build_layer_configs
from halbach_coils.coilgen.config import Config
from halbach_coils.run_pipeline import PipelineResult


def _tube(inner, outer, height, segments=128):
    return assembly.trimesh_from_manifold(
        m3d.Manifold.cylinder(height, outer, circular_segments=segments, center=True) -
        m3d.Manifold.cylinder(height + 2, inner, circular_segments=segments, center=True))


def _conductor(center, radius=.0003):
    mesh = trimesh.creation.icosphere(subdivisions=1, radius=radius)
    mesh.apply_translation(center)
    return mesh


@pytest.fixture
def design(tmp_path):
    base = Config()
    base.cylinder.height = .17
    base.target.rx = base.target.ry = base.target.rz = .015
    base.wire.conductor_width = .0015
    batch = BatchConfig(base=base, anchor_radius=.0265, radial_gap=.001,
                        output_dir=str(tmp_path), include_keys=True)
    configs = build_layer_configs(batch)
    results = []
    for index, cfg in enumerate(configs):
        root = tmp_path / f'{index + 1:02d}_G{cfg.gradient_axis}'
        (root / 'Molde').mkdir(parents=True)
        (root / 'Leads').mkdir()
        _tube(cfg.shell_inner_radius * 1000, cfg.shell_outer_radius * 1000, 170).export(
            root / 'Molde' / f'Gradient_G{cfg.gradient_axis}_shell_0.stl')
        _conductor([(cfg.shell_inner_radius + cfg.shell_outer_radius) / 2, 0, 0]).export(
            root / 'Leads' / f'Gradient_G{cfg.gradient_axis}_wire_0_with_leads.stl')
        results.append(PipelineResult(str(root)))
    return batch, configs, results


def _wire(result):
    return next((Path(result.output_dir) / 'Leads').glob('*.stl'))


def _former(result):
    return next((Path(result.output_dir) / 'Molde').glob('*.stl'))


def _hashes(results):
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for result in results for path in (_wire(result), _former(result))}


@pytest.mark.parametrize('clearance_mm', [.1, .3, .5])
def test_nominal_keys_honor_printing_clearance_and_have_no_antenna_slot(design, clearance_mm):
    batch, configs, _ = design
    batch.fit_clearance = clearance_mm / 1000
    keys = assembly.nominal_key_pairs(batch, configs)
    assert [(key['inner_axis'], key['outer_axis'], key['angle_deg']) for key in keys] == [
        ('z', 'x', 202.5), ('x', 'y', 180)]
    for key in keys:
        male, female = key['male_mm'], key['female_mm']
        assert male.is_watertight and female.is_watertight
        tangent = np.array([-np.sin(np.deg2rad(key['angle_deg'])),
                            np.cos(np.deg2rad(key['angle_deg'])), 0])
        assert np.ptp(male.vertices @ tangent) == pytest.approx(4)
        assert np.ptp(female.vertices @ tangent) == pytest.approx(4 + 2 * clearance_mm)
        assert male.bounds[:, 2] == pytest.approx([-85, -81])
        assert female.bounds[:, 2] == pytest.approx([-85 - clearance_mm, -81 + clearance_mm])
    batch.include_keys = False
    assert assembly.nominal_key_pairs(batch, configs) == []


@pytest.mark.parametrize('include_keys', [True, False])
def test_complete_set_is_validated_and_published_together(design, include_keys):
    batch, configs, results = design
    batch.include_keys = include_keys
    previous = _hashes(results)
    result = assembly.finalize_batch(batch, configs, results)
    assert _hashes(results) == previous
    target = Path(batch.output_dir) / 'Conjunto'
    assert sorted(path.name for path in target.iterdir()) == [
        'Gradientes.glb', 'Gx_molde.stl', 'Gy_molde.stl', 'Gz_molde.stl', 'encajes.json']
    assert result['units'] == 'mm' and result['scene_units'] == 'm'
    assert result['coordinate_frame'] == 'physical_xyz'
    assert set(result['part_paths']) == {'x', 'y', 'z'}
    for axis, path in result['part_paths'].items():
        mesh = trimesh.load_mesh(path)
        assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0
        assert mesh.bounds[:, 2] == pytest.approx([-85, 85])
        assert len(assembly._solid(mesh, axis).decompose()) == 1
    report = json.loads(Path(result['report_path']).read_text(encoding='utf-8'))
    assert report['status'] == 'complete' and report['antenna_slot'] is False
    assert len(report['checks']) == 18
    assert all(check['intersection_mm3'] == 0 for check in report['checks'])
    assert len(result['interfaces']) == (2 if include_keys else 0)
    scene = trimesh.load(result['scene_path'], force='scene')
    assert len(scene.geometry) == 3
    assert scene.bounds[:, 2] == pytest.approx([-.085, .085])
    assert len({tuple(mesh.visual.face_colors[0]) for mesh in scene.geometry.values()}) == 3
    assert not list(Path(batch.output_dir).glob('.conjunto-*'))


def test_existing_assembly_is_never_overwritten(design):
    batch, configs, results = design
    assembly.finalize_batch(batch, configs, results)
    target = Path(batch.output_dir) / 'Conjunto' / 'encajes.json'
    before = target.read_bytes()
    with pytest.raises(FileExistsError, match='refusing to overwrite'):
        assembly.finalize_batch(batch, configs, results)
    assert target.read_bytes() == before


def test_keys_find_an_alternate_azimuth_without_rotating_coils(design):
    batch, configs, results = design
    angle = np.deg2rad(202.5)
    _conductor([.03 * np.cos(angle), .03 * np.sin(angle), -.083], radius=.0002).export(_wire(results[0]))
    before = _hashes(results)
    result = assembly.finalize_batch(batch, configs, results)
    assert result['interfaces'][0]['angle_deg'] == 210
    assert result['interfaces'][1]['angle_deg'] == 180
    assert _hashes(results) == before
    # The preview helper can reproduce the actual selected station.
    male, _ = assembly.key_pair_meshes(batch, configs[0], configs[1], 210)
    assert male.is_watertight


def test_no_safe_station_keeps_individual_designs_and_publishes_no_set(design):
    batch, configs, results = design
    wire = trimesh.creation.torus(major_radius=.03, minor_radius=.00015,
                                  major_sections=64, minor_sections=8)
    wire.apply_translation([0, 0, -.083])
    wire.export(_wire(results[0]))
    before = _hashes(results)
    with pytest.raises(RuntimeError, match='No safe key azimuth'):
        assembly.finalize_batch(batch, configs, results)
    assert _hashes(results) == before
    assert not (Path(batch.output_dir) / 'Conjunto').exists()


def test_conductor_interference_is_rejected_even_without_keys(design):
    batch, configs, results = design
    batch.include_keys = False
    _conductor([.03, 0, 0]).export(_wire(results[0]))
    _conductor([.03, 0, 0]).export(_wire(results[1]))
    with pytest.raises(RuntimeError, match='conductor / conductor'):
        assembly.finalize_batch(batch, configs, results)
    assert not (Path(batch.output_dir) / 'Conjunto').exists()


def test_round_conductors_do_not_confuse_overlapping_grooves_with_real_cable(design):
    _, configs, results = design
    # Identical groove tools intersect, while 1.5 mm round cables with 3 mm
    # center spacing do not. The actual retained paths decide this check.
    groove = _conductor([.03, 0, 0])
    groove.apply_scale(1000)
    solid = assembly._solid(groove, 'groove')
    paths = [np.array([[30., 3.*i, -1.], [30., 3.*i, 1.]]) for i in range(3)]
    roi, _ = assembly._roi_solid(configs[0])
    checks = assembly._check_conductors(configs, [solid]*3, roi, paths)
    assert len(checks) == 6
    assert all(check['intersection_mm3'] == 0 for check in checks)
    assert checks[0]['model'] == 'round_wire_segment_capsules'
    paths[1][:, 1] = .5
    with pytest.raises(RuntimeError, match='round conductor / conductor'):
        assembly._check_conductors(configs, [solid]*3, roi, paths)


def test_current_path_must_match_conductor_hash_and_coordinates(design):
    _, configs, results = design
    from halbach_coils.coilgen.leads import current_path_path
    wire = _wire(results[0])
    source = {'conductor_path': str(wire), 'conductor_sha256': 'expected'}
    filename = current_path_path(wire)
    saved = dict(path=np.array([[.03, 0, 0], [.03, 0, .01]]), units='m',
                 coordinate_frame='physical_xyz', gradient_axis='z', b0_direction='+y',
                 with_leads_sha256='expected')
    np.savez(filename, **saved)
    np.testing.assert_allclose(assembly._current_path(configs[0], source), saved['path']*1000)
    saved['with_leads_sha256'] = 'stale'
    np.savez(filename, **saved)
    with pytest.raises(RuntimeError, match='does not match'):
        assembly._current_path(configs[0], source)


def test_terminal_through_another_former_is_rejected(design):
    batch, configs, results = design
    batch.include_keys = False
    radius = (configs[1].shell_inner_radius + configs[1].shell_outer_radius) / 2
    _conductor([0, radius, -.083]).export(_wire(results[0]))
    with pytest.raises(RuntimeError, match='conductor / other former'):
        assembly.finalize_batch(batch, configs, results)


def test_actual_conductor_intruding_into_shared_roi_is_rejected(design):
    batch, configs, results = design
    batch.include_keys = False
    _conductor([.0151, 0, 0], radius=.0003).export(_wire(results[0]))
    with pytest.raises(RuntimeError, match='conductor / ROI'):
        assembly.finalize_batch(batch, configs, results)


def test_actual_former_interference_is_rejected(design):
    batch, configs, results = design
    batch.include_keys = False
    _tube(29, 33.5, 170).export(_former(results[1]))
    with pytest.raises(RuntimeError, match='former / former'):
        assembly.finalize_batch(batch, configs, results)


def test_meter_formers_are_converted_once(design):
    batch, configs, results = design
    batch.include_keys = False
    for cfg, result in zip(configs, results):
        mesh = trimesh.load_mesh(_former(result))
        mesh.vertices *= .001
        mesh.export(_former(result))
        cfg.shell.output_in_mm = False
    output = assembly.finalize_batch(batch, configs, results)
    assert trimesh.load_mesh(output['part_paths']['z']).bounds[:, 2] == pytest.approx([-85, 85])


def test_open_conductor_is_not_repaired_or_silently_accepted(design):
    batch, configs, results = design
    mesh = trimesh.load_mesh(_wire(results[0]))
    mesh.update_faces(np.arange(len(mesh.faces)) != 0)
    mesh.export(_wire(results[0]))
    with pytest.raises(RuntimeError, match='not a closed'):
        assembly.finalize_batch(batch, configs, results)
    assert not (Path(batch.output_dir) / 'Conjunto').exists()


def test_failed_serialization_cleans_only_unpublished_staging(design, monkeypatch):
    batch, configs, results = design
    before = _hashes(results)
    original = assembly.export_validated_shell_stl
    calls = []

    def fail_second(mesh, path):
        calls.append(path)
        if len(calls) == 2:
            raise RuntimeError('synthetic export failure')
        return original(mesh, path)

    monkeypatch.setattr(assembly, 'export_validated_shell_stl', fail_second)
    with pytest.raises(RuntimeError, match='synthetic export failure'):
        assembly.finalize_batch(batch, configs, results)
    assert _hashes(results) == before
    assert not (Path(batch.output_dir) / 'Conjunto').exists()
    assert not list(Path(batch.output_dir).glob('.conjunto-*'))


def test_exported_solids_are_checked_again_for_interference(design, monkeypatch):
    batch, configs, results = design
    batch.include_keys = False
    original = assembly.export_validated_shell_stl
    count = []

    def change_second(mesh, path):
        count.append(path)
        if len(count) == 2:
            mesh = _tube(29, 33.5, 170)
        return original(mesh, path)

    monkeypatch.setattr(assembly, 'export_validated_shell_stl', change_second)
    with pytest.raises(RuntimeError, match='former / former'):
        assembly.finalize_batch(batch, configs, results)
    assert not (Path(batch.output_dir) / 'Conjunto').exists()


def test_shared_physical_frame_and_roi_are_required(design):
    batch, configs, results = design
    configs = deepcopy(configs)
    configs[1].target.rx *= 1.1
    with pytest.raises(ValueError, match='must share'):
        assembly.finalize_batch(batch, configs, results)


def test_wrong_former_height_or_frame_is_rejected(design):
    batch, configs, results = design
    mesh = trimesh.load_mesh(_former(results[0]))
    mesh.apply_translation([0, 0, 1])
    mesh.export(_former(results[0]))
    with pytest.raises(RuntimeError, match='height/frame'):
        assembly.finalize_batch(batch, configs, results)


def test_roi_polyhedron_conservatively_contains_the_analytic_ellipsoid(design):
    _, configs, _ = design
    roi, inflation = assembly._roi_solid(configs[0])
    assert 1 < inflation < 1.005
    mesh = assembly.trimesh_from_manifold(roi)
    assert roi.volume() > 4 / 3 * np.pi * 15**3
    # For a sphere ROI, every face plane lies outside the analytic sphere.
    distance = np.abs(np.einsum('ij,ij->i', mesh.face_normals, mesh.triangles[:, 0]))
    assert distance.min() >= 15 - 1e-5


@pytest.mark.parametrize('b0', ['+x', '-x', '+y', '-y', '+z', '-z'])
@pytest.mark.parametrize('include_keys', [True, False])
def test_batch_marks_share_one_side_and_survive_final_export(design, b0, include_keys):
    batch, configs, results = design
    batch.include_b0_markers = True
    batch.include_keys = include_keys
    batch.base.b0_direction = b0
    for cfg in configs:
        cfg.b0_direction = b0
    before = _hashes(results)
    original = [assembly._load_layer(cfg, result)[0] for cfg, result in zip(configs, results)]
    marked, keepouts, expected_record = assembly._mark_formers(batch, configs, original)
    result = assembly.finalize_batch(batch, configs, results)
    record = result['b0_markers']
    assert record['enabled'] and record['common_side'] == 1
    assert record['radial_direction'] == expected_record['radial_direction']
    assert record['placement'] == ('outer_wall' if b0[-1] == 'z' else 'end_faces')
    assert record['layer_axes'] == ['z', 'x', 'y']
    assert _hashes(results) == before
    report = json.loads(Path(result['report_path']).read_text(encoding='utf-8'))
    assert report['b0_markers'] == record
    for cfg, stamped in zip(configs, marked):
        exported = assembly._solid(trimesh.load_mesh(result['part_paths'][cfg.gradient_axis]), 'marked')
        assert len(exported.decompose()) == 1
        # The key operations must leave all material around the marks intact.
        assert (exported ^ keepouts[0]).volume() == pytest.approx(
            (stamped ^ keepouts[0]).volume(), abs=.001)
    for interface, inner, outer in zip(result['interfaces'], configs, configs[1:]):
        male, female = assembly._key_manifolds(batch, inner, outer, interface['angle_deg'])
        assert all(assembly._intersection_volume(feature, keepouts[0]) == 0 for feature in (male, female))


def test_key_search_moves_keys_away_from_marker_azimuth(design, monkeypatch):
    batch, configs, results = design
    batch.include_b0_markers = True
    monkeypatch.setattr(assembly, 'PREFERRED_ANGLES', (90, 90))
    original = [assembly._load_layer(cfg, result)[0] for cfg, result in zip(configs, results)]
    _, keepouts, _ = assembly._mark_formers(batch, configs, original)
    output = assembly.finalize_batch(batch, configs, results)
    assert output['b0_markers']['angle_deg'] == pytest.approx(90)
    for index, interface in enumerate(output['interfaces']):
        assert interface['angle_deg'] != 90
        for feature in assembly._key_manifolds(batch, *configs[index:index + 2], interface['angle_deg']):
            assert assembly._intersection_volume(feature, keepouts[0]) == 0


def _rim_notch(cfg, side):
    radius_mm = 500 * (cfg.shell_inner_radius + cfg.shell_outer_radius)
    return m3d.Manifold.cube((3, 8, 4), center=True).translate((0, side * radius_mm, 84))


def test_one_occupied_rim_switches_all_three_marks_to_opposite_b0_side(design):
    batch, configs, results = design
    batch.include_b0_markers = True
    source = assembly._solid(trimesh.load_mesh(_former(results[1])), 'source')
    assembly.trimesh_from_manifold(source - _rim_notch(configs[1], 1)).export(_former(results[1]))
    original = [assembly._load_layer(cfg, result)[0] for cfg, result in zip(configs, results)]
    marked, _, record = assembly._mark_formers(batch, configs, original)
    assert record['common_side'] == -1
    np.testing.assert_allclose(record['radial_direction'], [0, -1, 0])
    for unmarked, stamped in zip(original, marked):
        cavities = assembly.trimesh_from_manifold(unmarked - stamped).split()
        assert len(cavities) == 2
        for cavity in cavities:
            assert abs(cavity.center_mass[0]) < 1e-5
            assert cavity.center_mass[1] < 0
    output = assembly.finalize_batch(batch, configs, results)
    assert output['b0_markers']['common_side'] == -1


def test_no_common_marker_side_keeps_sources_and_publishes_no_assembly(design):
    batch, configs, results = design
    batch.include_b0_markers = True
    for index, side in ((0, 1), (1, -1)):
        source = assembly._solid(trimesh.load_mesh(_former(results[index])), 'source')
        assembly.trimesh_from_manifold(source - _rim_notch(configs[index], side)).export(_former(results[index]))
    before = _hashes(results)
    with pytest.raises(RuntimeError, match='No common clear B0 marker position'):
        assembly.finalize_batch(batch, configs, results)
    assert _hashes(results) == before
    assert not (Path(batch.output_dir) / 'Conjunto').exists()


def test_disabled_batch_marks_preserve_original_unmarked_geometry(design):
    batch, configs, results = design
    batch.include_keys = False
    output = assembly.finalize_batch(batch, configs, results)
    assert output['b0_markers'] == {'enabled': False}
    for cfg, outcome in zip(configs, results):
        original = trimesh.load_mesh(_former(outcome))
        final = trimesh.load_mesh(output['part_paths'][cfg.gradient_axis])
        assert final.volume == pytest.approx(original.volume)
