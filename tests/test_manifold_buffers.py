"""Native CAD accepts only writable, correctly typed mesh buffers."""
import manifold3d as m3d
import numpy as np
import pytest
import trimesh

from halbach_coils.coilgen import assembly, lead_surface, shell


@pytest.mark.parametrize('convert,scale', [
    (shell.manifold_from_trimesh, 1),
    (lambda mesh: assembly._solid(mesh, 'test', one_part=True), 1),
    (lead_surface.manifold, 1000),
])
def test_read_only_manifold_vertices_round_trip_without_changing_input(convert, scale):
    original = m3d.Manifold.cube([1, 2, 3])
    # This is the actual assembly export path: trimesh retains the native
    # manifold's read-only vertex buffer. Contiguity alone cannot repair it.
    mesh = assembly.trimesh_from_manifold(original)
    assert mesh.vertices.flags.c_contiguous
    assert not mesh.vertices.flags.writeable
    before = mesh.vertices.copy()
    converted = convert(mesh)
    assert converted.status() == m3d.Error.NoError
    assert converted.volume() == pytest.approx(original.volume() * scale ** 3)
    np.testing.assert_array_equal(mesh.vertices, before)
    assert not mesh.vertices.flags.writeable


def test_stl_repair_accepts_read_only_vertices(tmp_path):
    base = trimesh.creation.box(extents=[100, 100, 100])
    a, b, c = base.faces[0]
    extra = len(base.vertices)
    point = base.vertices[a] + (base.vertices[b] - base.vertices[a]) * .3
    mesh = trimesh.Trimesh(
        np.vstack([base.vertices, point]),
        np.vstack([base.faces[1:], [a, b, extra], [b, c, extra], [c, a, extra]]),
        process=False)
    mesh.vertices.setflags(write=False)
    assert mesh.is_watertight
    assert np.count_nonzero(~mesh.nondegenerate_faces()) == 1
    result = shell.export_validated_shell_stl(mesh, tmp_path / 'repaired.stl')
    assert result.is_watertight and result.is_winding_consistent
    assert np.all(result.nondegenerate_faces())
    assert result.volume == pytest.approx(base.volume)
    np.testing.assert_allclose(result.bounds, base.bounds)
