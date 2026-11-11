"""Real zero-gap Gx cuts must continue their tangent without changing profile."""

from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from halbach_coils.coilgen.lead_surface import (
    GeometryRejected, Options, surface_lead, tube_mesh, validate_mesh, vector_areas,
)
from pyCoilGen.helpers.wire_geometry import closed_wire_path, wire_contact_pairs
from pyCoilGen.mesh_factory.build_cylinder_mesh import create_cylinder_mesh
from pyCoilGen.sub_functions.data_structures import Shape3D
from pyCoilGen.sub_functions.parameterize_mesh import parameterize_mesh
from pyCoilGen.sub_functions import wire_clearance as repair

DATA = Path(__file__).parent/'test_data'


def actual_cut():
    with np.load(DATA/'gx_terminal_radial_cut.npz', allow_pickle=False) as saved:
        return {key: saved[key].copy() for key in saved.files}


@pytest.mark.parametrize('transform', [False, True])
def test_actual_inclined_cut_preserves_profile_tangent_radius_and_curvature(transform):
    values = actual_cut()
    options = Options(max_step=.00003)
    base = surface_lead(**values, options=options)
    if transform:
        rotation = Rotation.from_rotvec([.43, -1.1, .71]).as_matrix()
        offset = np.array([.25, -.13, .08])
        values['ring'] = values['ring']@rotation.T+offset
        values['outward'] = values['outward']@rotation.T
        values['axis'] = values['axis']@rotation.T
        values['origin'] = values['origin']@rotation.T+offset
    lead = surface_lead(**values, options=options)
    assert lead.metrics['radial_continuation']
    assert lead.metrics['junction_tangent_error_deg'] < 1e-5
    assert np.array_equal(lead.rings[0], values['ring'])
    np.testing.assert_allclose(lead.tangent[0], values['outward'], atol=1e-12)
    np.testing.assert_allclose(np.abs(lead.tangent[-1]@values['axis']), 1., atol=1e-12)
    np.testing.assert_allclose(vector_areas(lead.rings), vector_areas(values['ring'][None])[0], rtol=1e-10)
    # Full pairwise corner distances establish preservation of the polygon,
    # rather than only an equal area after deformation.
    expected = np.linalg.norm(values['ring'][:, None]-values['ring'][None, :], axis=2)
    actual = np.linalg.norm(lead.rings[:, :, None]-lead.rings[:, None, :], axis=3)
    np.testing.assert_allclose(actual, np.broadcast_to(expected, actual.shape), atol=1e-12)
    relative = lead.path-values['origin']
    radial = relative-(relative@values['axis'])[:, None]*values['axis']
    radii = np.linalg.norm(radial, axis=1)
    assert radii.min() >= values['radial_bounds'][0]-1e-12
    assert radii.max() <= values['radial_bounds'][1]+1e-12
    edges = np.diff(lead.path, axis=0)
    assert np.linalg.norm(edges, axis=1).max() <= options.max_step*1.001
    # Independently recover circumcircle curvature from consecutive centers.
    a, b, c = edges[:-1], edges[1:], lead.path[2:]-lead.path[:-2]
    curvature = 2*np.linalg.norm(np.cross(a, b), axis=1)/(
        np.linalg.norm(a, axis=1)*np.linalg.norm(b, axis=1)*np.linalg.norm(c, axis=1))
    assert 1/curvature.max() >= options.min_bend_radius
    assert lead.min_radius >= options.min_bend_radius
    validate_mesh(tube_mesh(lead.rings))
    if transform:
        np.testing.assert_allclose(lead.path, base.path@rotation.T+offset, atol=1e-11)


def test_radial_continuation_rejects_an_insufficient_envelope_or_impossible_bend():
    values = actual_cut()
    with pytest.raises(GeometryRejected, match='Junction tangent'):
        surface_lead(**{k: v for k, v in values.items() if k != 'radial_bounds'}, options=Options())
    center = values['ring'].mean(0)-values['origin']
    radius = np.linalg.norm(center-np.dot(center, values['axis'])*values['axis'])
    with pytest.raises(GeometryRejected, match='winding envelope'):
        surface_lead(**dict(values, radial_bounds=(radius-1e-10, radius+1e-10)), options=Options())
    with pytest.raises(GeometryRejected):
        surface_lead(**values, options=Options(min_bend_radius=1.))


def test_noncoincident_ramp_contacts_reach_the_spatial_repair_before_routing_retries():
    with np.load(DATA/'gx_20_no_gap_ramps.npz', allow_pickle=False) as saved:
        original = saved['path']
    args = NS(cylinder_mesh_parameter_list=[.114, .05, 40, 40, 0, 1, 0, 0],
              surface_is_cylinder_flag=True, circular_diameter_factor=1., debug=0,
              auto_wire_clearance=True, conductor_thickness=.002)
    part = NS(coil_mesh=create_cylinder_mesh(args))
    parameterize_mesh([part], args)
    part.wire_path = Shape3D(v=original.T.copy(), uv=np.zeros((2, len(original))))
    repair.ensure_wire_clearance(part, args)
    report = part.clearance_report
    assert report['initial_contact_pairs'] == 1018
    assert .2 < report['initial_minimum_mm'] < 1.
    assert report['status'] == 'repaired'
    assert report['method'] == 'spatial_crossing_separation'
    assert report['cylindrical_recovery']['reason'] == 'clearance_not_reached_within_limits'
    assert report['remaining_contact_pairs'] == 0
    assert not len(wire_contact_pairs(closed_wire_path(part.wire_path.v.T), .002, closed=True)[0])
