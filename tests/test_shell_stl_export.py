import numpy as np
import pytest
import trimesh
from io import BytesIO

from halbach_coils.coilgen.shell import export_validated_shell_stl, load_shell_stl


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
