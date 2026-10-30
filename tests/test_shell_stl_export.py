import numpy as np
import pytest
import trimesh
from io import BytesIO

from halbach_coils.coilgen.shell import export_validated_shell_stl, load_shell_stl


def test_ordered_overlapping_sweep_segments_are_a_solid_union_without_expansion():
    from halbach_coils.coilgen.shell import ordered_groove_manifold, trimesh_from_manifold
    count = 12
    theta = np.arange(count)*2*np.pi/count
    section = np.column_stack((.002*np.cos(theta), .001*np.sin(theta), np.zeros(count)))
    rings = np.stack([section+[0, 0, z] for z in (0., .010, .005, .015)])
    j, k = np.arange(count), (np.arange(count)+1) % count
    faces = np.vstack((np.column_stack((j, k, k+count)), np.column_stack((j, k+count, j+count))))
    sides = np.broadcast_to(faces, (len(rings)-1, *faces.shape))
    result = ordered_groove_manifold(rings, sides)
    mesh = trimesh_from_manifold(result)
    area = np.linalg.norm(np.cross(section, np.roll(section, -1, axis=0)).sum(axis=0))/2
    assert result.volume() == pytest.approx(area*.015, rel=1e-10)
    assert mesh.is_volume and len(mesh.split()) == 1
    np.testing.assert_allclose(mesh.bounds, [[-.002, -.001, 0.], [.002, .001, .015]], atol=1e-12)


def test_ordered_groove_preserves_the_original_nonplanar_side_diagonals():
    from halbach_coils.coilgen.lead_surface import tube_mesh
    from halbach_coils.coilgen.shell import ordered_groove_manifold
    count = 12
    theta = np.arange(count)*2*np.pi/count
    first = np.column_stack((.002*np.cos(theta), .001*np.sin(theta), np.zeros(count)))
    angle = .2
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0.],
                         [np.sin(angle), np.cos(angle), 0.], [0., 0., 1.]])
    rings = np.stack((first, first@rotation.T+[0., 0., .01]))
    mesh = tube_mesh(rings)
    # Use the opposite diagonal from tube_mesh on every nonplanar side.
    j, k = np.arange(count), (np.arange(count)+1) % count
    sides = np.vstack((np.column_stack((j, k, j+count)),
                       np.column_stack((k, k+count, j+count))))
    caps = mesh.faces[(mesh.faces >= 2*count).any(axis=1)]
    original = trimesh.Trimesh(mesh.vertices, np.vstack((sides, caps)), process=False)
    original.fix_normals()
    result = ordered_groove_manifold(rings, sides[None])
    assert result.volume() == pytest.approx(original.volume, rel=1e-10)
    assert abs(original.volume-mesh.volume) > 1e-12


def test_generated_carrier_removes_only_disconnected_positive_offcuts():
    import manifold3d as m3d
    from halbach_coils.coilgen.config import Config
    from halbach_coils.coilgen.shell import retain_connected_former
    cfg = Config()
    cfg.cylinder.height = .170
    tube = (m3d.Manifold.cylinder(.170,.035,center=True)
            - m3d.Manifold.cylinder(.172,.029,center=True))
    carrier = tube.trim_by_plane((1,0,0),0)
    # This deliberately large offcut rules out a tiny-volume discard policy.
    offcut = m3d.Manifold.cube((.005,.005,.005),center=True).translate((-.032,0,0))
    result, removed = retain_connected_former(carrier+offcut,cfg)
    assert len(result.decompose()) == 1
    assert result.volume() == pytest.approx(carrier.volume())
    assert removed[0]['volume_mm3'] == pytest.approx(125)


def test_generated_carrier_never_fills_enclosed_negative_cavities():
    import manifold3d as m3d
    from halbach_coils.coilgen.config import Config
    from halbach_coils.coilgen.shell import retain_connected_former
    cfg = Config()
    cfg.cylinder.height = .170
    tube = (m3d.Manifold.cylinder(.170,.035,center=True)
            - m3d.Manifold.cylinder(.172,.029,center=True))
    cavity = m3d.Manifold.cube((.001,.001,.001),center=True).translate((.032,0,0))
    original = tube-cavity
    assert any(part.volume()<0 for part in original.decompose())
    result, removed = retain_connected_former(original,cfg)
    assert result is original and removed == []


def test_generated_carrier_rejects_two_bodies_joining_the_rims():
    import manifold3d as m3d
    from halbach_coils.coilgen.config import Config
    from halbach_coils.coilgen.shell import retain_connected_former
    cfg = Config()
    cfg.cylinder.height = .170
    tube = (m3d.Manifold.cylinder(.170,.035,center=True)
            - m3d.Manifold.cylinder(.172,.029,center=True))
    split = tube.trim_by_plane((1,0,0),.001)+tube.trim_by_plane((-1,0,0),.001)
    with pytest.raises(RuntimeError,match='exactly one connected body'):
        retain_connected_former(split,cfg)


@pytest.mark.parametrize('units', ['mm', 'm'])
def test_exported_generated_carrier_discards_only_disconnected_offcuts(tmp_path, units):
    import manifold3d as m3d
    from halbach_coils.coilgen.config import Config
    from halbach_coils.coilgen.shell import trimesh_from_manifold
    cfg = Config()
    cfg.cylinder.height = .170
    tube = (m3d.Manifold.cylinder(.170, .035, center=True)
            - m3d.Manifold.cylinder(.172, .029, center=True))
    carrier = tube.trim_by_plane((1, 0, 0), 0)
    offcut = m3d.Manifold.cube((.005, .005, .005), center=True).translate((-.032, 0, 0))
    mesh = trimesh_from_manifold(carrier+offcut)
    if units == 'mm':
        mesh.apply_scale(1000)
    target = tmp_path/'carrier.stl'
    result = export_validated_shell_stl(mesh, target, units, generated_config=cfg)
    assert len(result.split()) == 1 and result.is_volume
    scale = 1000 if units == 'mm' else 1
    assert result.volume == pytest.approx(carrier.volume()*scale**3, rel=1e-6)
    assert len(load_shell_stl(target, units).split()) == 1


def test_serialized_carrier_never_fills_a_negative_enclosed_cavity(tmp_path):
    import manifold3d as m3d
    from halbach_coils.coilgen.config import Config
    from halbach_coils.coilgen.shell import trimesh_from_manifold
    cfg = Config()
    cfg.cylinder.height = .170
    tube = (m3d.Manifold.cylinder(.170, .035, center=True)
            - m3d.Manifold.cylinder(.172, .029, center=True))
    cavity = m3d.Manifold.cube((.001, .001, .001), center=True).translate((.032, 0, 0))
    offcut = m3d.Manifold.cube((.005, .005, .005), center=True).translate((.05, 0, 0))
    mesh = trimesh_from_manifold(tube-cavity+offcut)
    mesh.apply_scale(1000)
    result = export_validated_shell_stl(mesh, tmp_path/'cavity.stl', generated_config=cfg)
    assert any(part.volume < 0 for part in result.split())
    assert sum(part.volume > 0 for part in result.split()) == 1
    assert result.volume == pytest.approx((tube.volume()-cavity.volume())*1e9, rel=1e-6)


def test_float32_opposite_faces_cancel_instead_of_leaving_an_open_sheet(tmp_path):
    base = trimesh.creation.box(extents=[100., 100., 100.])
    triangle = np.array([[50., 0., 0.], [50., 1., 0.], [50., 0., 1.]])
    vertices = np.vstack((triangle, triangle+[1e-9, 0., 0.]))
    j, k = np.arange(3), (np.arange(3)+1) % 3
    faces = np.vstack(([[0, 2, 1], [3, 4, 5]], np.column_stack((j, k, k+3)),
                       np.column_stack((j, k+3, j+3))))
    sheet = trimesh.Trimesh(vertices, faces, process=False)
    sheet.fix_normals()
    mesh = trimesh.util.concatenate((base, sheet))
    assert mesh.is_watertight
    result = export_validated_shell_stl(mesh, tmp_path/'cancelled_sheet.stl')
    assert result.is_volume and len(result.faces) == len(base.faces)
    assert result.volume == pytest.approx(base.volume, rel=1e-12)


@pytest.mark.parametrize('output_in_mm', [True, False])
def test_two_cylindrical_halves_run_carve_export_and_reload(tmp_path, capsys, output_in_mm):
    import manifold3d as m3d
    from halbach_coils.coilgen.config import Config, apply_custom_shell_dims
    from halbach_coils.coilgen.shell import run_shell, trimesh_from_manifold
    cfg = Config(show_plots=False)
    cfg.cylinder.height = .170
    blank = (m3d.Manifold.cylinder(.170, .035, circular_segments=64, center=True)
             - m3d.Manifold.cylinder(.172, .029, circular_segments=64, center=True))
    halves = []
    for label, normal in (('a',(1,0,0)), ('b',(-1,0,0))):
        mesh = trimesh_from_manifold(blank.trim_by_plane(normal, 0))
        mesh.apply_scale(1000)
        target = tmp_path / f'blank_{label}.stl'
        mesh.export(target)
        halves.append(str(target))
    apply_custom_shell_dims(cfg, *halves)
    cfg.shell.layer = 2  # The integer layer used to raise after exporting A.
    cfg.shell.output_in_mm = output_in_mm
    cfg.shell.shell_outer_pad = 0
    wire = trimesh.creation.torus(major_radius=cfg.cylinder_design_radius,
                                  minor_radius=.001, major_sections=64, minor_sections=12)
    wire_path = tmp_path/'wire.stl'
    final_path = tmp_path/'wire_with_leads.stl'
    wire.export(wire_path)
    wire.export(final_path)
    _, paths = run_shell(cfg, str(final_path), align_wire_stl=str(wire_path),
                         output_dir=str(tmp_path/'carved'))
    assert len(paths) == 2
    log = capsys.readouterr().out
    scale = 1000 if output_in_mm else 1
    for label, target in zip(('a','b'), paths):
        assert f'Half {label.upper()} (g_2{label})' in log
        mesh = load_shell_stl(target, units='mm' if output_in_mm else 'm')
        validation = mesh.copy()
        validation.apply_scale(1000 / scale)
        assert mesh.is_volume and np.all(validation.nondegenerate_faces())
        assert np.ptp(mesh.vertices[:,2]) == pytest.approx(.170*scale, abs=1e-7*scale)
        assert np.max(np.linalg.norm(mesh.vertices[:,:2],axis=1)) == pytest.approx(.035*scale, abs=1e-7*scale)
        assert 0 < mesh.volume < blank.volume()*scale**3/2


def test_float32_collapsed_edge_exports_as_a_closed_shell(tmp_path):
    base = trimesh.creation.box(extents=[100, 100, 100])
    a, b = base.faces[0][:2]
    extra = len(base.vertices)
    vertices = np.vstack([base.vertices, base.vertices[a] +
                          (base.vertices[b] - base.vertices[a]) * 1e-10])
    faces = []
    for face in base.faces:
        if a in face and b in face:
            for index in range(3):
                rotated = np.roll(face, -index)
                if set(rotated[:2]) == {a, b}:
                    x, y, z = rotated
                    faces.extend([[x, extra, z], [extra, y, z]])
                    break
        else:
            faces.append(face)
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    assert mesh.is_watertight
    target = tmp_path / 'shell.stl'
    exported = export_validated_shell_stl(mesh, target)
    reloaded = trimesh.load_mesh(target)
    assert reloaded.is_watertight and reloaded.is_winding_consistent
    assert len(reloaded.faces) == len(base.faces) < len(mesh.faces)
    assert np.all(reloaded.nondegenerate_faces())
    assert reloaded.volume == pytest.approx(base.volume)
    assert exported.is_watertight


def test_an_open_shell_is_not_published(tmp_path):
    mesh = trimesh.creation.box()
    mesh.update_faces(np.arange(len(mesh.faces)) != 0)
    target = tmp_path / 'invalid.stl'
    with pytest.raises(RuntimeError, match='failed validation'):
        export_validated_shell_stl(mesh, target)
    assert not target.exists()


def test_float32_collinear_sliver_collapses_only_its_sub_precision_edge(tmp_path):
    base = trimesh.creation.box(extents=[100, 100, 100])
    a, b, c = base.faces[0]
    extra = len(base.vertices)
    # The point lies inside this face, close to the a-b edge and vertex a.
    # Float32 erases its perpendicular component but retains the tiny a-p
    # edge. Deleting the now-collinear a-b-p triangle alone opens the solid.
    point = (base.vertices[a] + (base.vertices[b] - base.vertices[a]) * 7e-8
             + (base.vertices[c] - base.vertices[a]) * 1e-10)
    vertices = np.vstack([base.vertices, point])
    faces = np.vstack([base.faces[1:], [a, b, extra], [b, c, extra], [c, a, extra]])
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    assert mesh.is_watertight
    rounded = trimesh.load_mesh(BytesIO(mesh.export(file_type='stl')), file_type='stl')
    assert np.count_nonzero(~rounded.nondegenerate_faces()) == 1
    rounded.update_faces(rounded.nondegenerate_faces())
    assert not rounded.is_watertight
    target = tmp_path / 'precision_sliver.stl'
    result = export_validated_shell_stl(mesh, target)
    assert result.is_watertight and result.is_winding_consistent
    assert np.all(result.nondegenerate_faces())
    assert result.volume == pytest.approx(base.volume)
    assert len(result.faces) == len(base.faces)


def test_collinear_t_junction_retessellates_neighbor_without_filling_a_hole(tmp_path):
    base = trimesh.creation.box(extents=[100, 100, 100])
    a, b, c = base.faces[0]
    extra = len(base.vertices)
    point = base.vertices[a] + (base.vertices[b] - base.vertices[a]) * .3
    vertices = np.vstack([base.vertices, point])
    faces = np.vstack([base.faces[1:], [a, b, extra], [b, c, extra], [c, a, extra]])
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    assert mesh.is_watertight
    assert np.count_nonzero(~mesh.nondegenerate_faces()) == 1
    target = tmp_path / 'collinear_junction.stl'
    result = export_validated_shell_stl(mesh, target)
    assert result.is_watertight and result.is_winding_consistent
    assert np.all(result.nondegenerate_faces())
    assert result.volume == pytest.approx(base.volume)
    np.testing.assert_allclose(result.bounds, base.bounds)


def test_stl_rounding_collinearizes_a_face_with_long_edges(tmp_path):
    base = trimesh.creation.box(extents=[100, 100, 100])
    a, b, c = base.faces[0]
    extra = len(base.vertices)
    # Every input face is valid. Float32 erases the perpendicular offset,
    # making this face collinear without collapsing any of its long edges.
    point = (base.vertices[a] + (base.vertices[b] - base.vertices[a]) * .3
             + (base.vertices[c] - base.vertices[a]) * 1e-9)
    mesh = trimesh.Trimesh(
        np.vstack([base.vertices, point]),
        np.vstack([base.faces[1:], [a, b, extra], [b, c, extra], [c, a, extra]]),
        process=False)
    assert mesh.is_watertight and np.all(mesh.nondegenerate_faces())
    rounded = trimesh.load_mesh(BytesIO(mesh.export(file_type='stl')), file_type='stl')
    assert np.count_nonzero(~rounded.nondegenerate_faces()) == 1
    result = export_validated_shell_stl(mesh, tmp_path / 'rounding_sliver.stl')
    assert result.is_watertight and result.is_winding_consistent
    assert np.all(result.nondegenerate_faces())
    assert result.volume == pytest.approx(base.volume)
    np.testing.assert_allclose(result.bounds, base.bounds)
