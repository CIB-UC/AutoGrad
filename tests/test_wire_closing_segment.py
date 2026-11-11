"""The actual GY failure: a sweep closure omitted before adding terminals."""

from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from halbach_coils.coilgen.config import Config
from halbach_coils.coilgen.leads import final_current_path
from halbach_coils.coilgen.overlap import detect_collisions
from pyCoilGen.helpers.wire_geometry import closed_wire_path, wire_contact_pairs
from pyCoilGen.sub_functions import wire_clearance as recovery
from pyCoilGen.sub_functions.data_structures import Mesh, Shape3D
from pyCoilGen.sub_functions.routing_recovery import _physical_status


def failed_gy():
    filename = Path(__file__).parent/'test_data'/'gy_closing_segment.npz'
    with np.load(filename, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def with_saved_leads(path, data):
    # Only the ordered section centres are needed to reconstruct the current.
    # The saved engine sweep traverses the optimized path in reverse order.
    reference = NS(path=path, rings=path[::-1, None, :], semi_b=.00075)
    leads = [NS(path=data['lead0']), NS(path=data['lead1'])]
    return final_current_path(reference, leads, dict(cut_indices=data['cut_indices']))


def test_closure_is_explicit_idempotent_and_preserves_the_station_indices():
    path = failed_gy()['path']
    closed = closed_wire_path(path)
    np.testing.assert_array_equal(closed[:-1], path)
    np.testing.assert_array_equal(closed[-1], path[0])
    np.testing.assert_array_equal(closed_wire_path(closed), closed)
    assert not len(wire_contact_pairs(path, .0015, closed=False)[0])
    i, j, distances, _ = wire_contact_pairs(closed, .0015, closed=True)
    assert len(i) == 4 and np.all(j == len(path)-1)
    assert distances.min()*1000 == pytest.approx(.11934761606632285)


def test_independent_pre_lead_checks_include_the_swept_closing_edge():
    path = failed_gy()['path']
    part = NS(wire_path=NS(v=path.T, uv=path[:, :2].T), layout_surface_mesh=object())
    cfg = Config()
    cfg.wire.conductor_width = .0015
    report = detect_collisions(NS(coil_parts=[part]), cfg)
    assert report.n_collisions > 0
    assert min(site.minimum_distance_m for site in report.sites)*1000 == pytest.approx(.11934761606632285)
    contacts, minimum_mm = _physical_status([part], .0015)
    assert contacts == 4
    assert minimum_mm == pytest.approx(.11934761606632285)


def test_application_repairs_the_closure_and_the_actual_retained_coil_and_terminals():
    data = failed_gy()
    path = data['path']
    before = with_saved_leads(path, data)
    _, _, distances, _ = wire_contact_pairs(before, .0015, closed=False)
    assert distances.min()*1000 == pytest.approx(.11934761606632285)
    with np.load(Path(__file__).parent/'test_data'/'gx_crossing_ramps.npz') as geometry:
        vertices = geometry['vertices'].copy()
        vertices[:, :2] *= .0658/.0673
        mesh = Mesh(vertices=vertices, faces=geometry['faces'])
        mesh.uv = geometry['mesh_uv']
    part = NS(coil_mesh=mesh, wire_path=Shape3D(v=path.T.copy(), uv=np.zeros((2, len(path)))))
    args = NS(auto_wire_clearance=True, surface_is_cylinder_flag=True,
              cylinder_mesh_parameter_list=[.1615,.0658,200,10,0,1,0,0],
              conductor_thickness=.0015)
    recovery.ensure_wire_clearance(part, args)
    report = part.clearance_report
    assert report['status'] == 'repaired' and report['closed_loop']
    fixed = part.wire_path.v.T
    assert fixed.shape == path.shape
    assert np.isfinite(part.wire_path.uv).all()
    assert not len(wire_contact_pairs(closed_wire_path(fixed), .001515, closed=True,
                                      local_diameter=.0015)[0])
    final = with_saved_leads(fixed, data)
    assert not len(wire_contact_pairs(final, .0015, closed=False)[0])
    # Reusing the original terminal curves exercises exactly the failed stage.
    # Only the coil region around the omitted closure needed to change.
    np.testing.assert_array_equal(final[:len(data['lead0'])], before[:len(data['lead0'])])
    np.testing.assert_array_equal(final[-len(data['lead1']):], before[-len(data['lead1']):])
