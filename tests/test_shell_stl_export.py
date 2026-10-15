import numpy as np
import pytest
import trimesh
from io import BytesIO

from halbach_coils.coilgen.shell import export_validated_shell_stl


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
