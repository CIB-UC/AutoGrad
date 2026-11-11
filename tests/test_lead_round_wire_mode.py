"""Manufacturing recommendations must not block physically separated leads."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from halbach_coils.coilgen.lead_surface import (
    GeometryRejected, Options, round_wire_clearance, surface_lead,
)


def terminal_ring():
    angle = np.linspace(0, 2*np.pi, 32, endpoint=False)
    return np.c_[.04+.002*np.cos(angle), np.zeros(32), .001*np.sin(angle)]


def test_bend_recommendation_does_not_block_round_wire_mode():
    ring = terminal_ring()
    options = Options(min_bend_radius=1., strict_manufacturing=False, conductor_diameter=.002)
    lead = surface_lead(ring, [0, 1, 0], np.array([0, 0, 1]), np.zeros(3), .115, .6, 1., options)
    assert 0 < lead.min_radius < options.min_bend_radius
    np.testing.assert_array_equal(lead.rings[0], ring)
    assert np.all(np.isfinite(lead.rings))


def test_explicit_strict_study_still_enforces_bend_radius():
    with pytest.raises(GeometryRejected, match='Bend radius below minimum'):
        surface_lead(terminal_ring(), [0, 1, 0], np.array([0, 0, 1]), np.zeros(3),
                     .115, .6, 1., Options(min_bend_radius=1.))


def test_real_round_wire_crossing_remains_rejected():
    path = np.array([[-.01,0,0],[.01,0,0],[.01,.02,0],[0,.02,.001],[0,-.01,.001]])
    ref = NS(path=path, rings=path[:, None, :])
    leads = [NS(path=np.array([path[-1], [0,-.03,.001]])),
             NS(path=np.array([path[0], [-.03,0,0]]))]
    with pytest.raises(GeometryRejected, match='Round-wire clearance'):
        round_wire_clearance(ref, leads, np.arange(len(path)), .002)


def test_round_wire_mode_requires_an_explicit_real_diameter():
    with pytest.raises(ValueError, match='real conductor diameter'):
        Options(strict_manufacturing=False).validate()
