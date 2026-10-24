"""Round-wire interference using exact distances between nonlocal 3D segments.

Adjacent samples are excluded by physical arc length, including the seam.
Manufacturing groove deformation never changes the conductor diameter.
Crossing metadata is retained only for old diagnostics without a 3D path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

from .config import Config
from pyCoilGen.helpers.wire_geometry import closed_wire_path, wire_contact_pairs


@dataclass(frozen=True)
class CollisionSite:
    """A cluster of interfering nonlocal branches (or legacy crossing metadata)."""

    part_index: int
    location_uv: Tuple[float, float]
    cable_count: int
    crossing_count: int
    segment_indices: Tuple[int, ...]
    location_xyz_m: Tuple[float, float, float] | None = None
    minimum_distance_m: float | None = None
    required_separation_m: float | None = None

    @property
    def inner_layer_count(self) -> int:
        return self.cable_count - 1


@dataclass
class OverlapReport:
    """Multi-wire congestion sites found in a completed pyCoilGen solution."""

    sites: List[CollisionSite] = field(default_factory=list)
    cluster_tolerance_m: float = 0.0

    @property
    def n_collisions(self) -> int:
        """Compatibility name: now counts congestion sites, not segment pairs."""
        return len(self.sites)

    @property
    def max_cables(self) -> int:
        return max((site.cable_count for site in self.sites), default=0)

    def physical_interference_message(self, language: str = 'es') -> str:
        """A measured physical failure cannot be overridden by confirmation."""
        measured = [site for site in self.sites
                    if site.minimum_distance_m is not None
                    and site.required_separation_m is not None]
        if not measured:
            return ''
        english = language == 'en'
        lines = [('Round-wire interference detected:' if english else
                  'Se detectó interferencia entre ramas del cable circular:')]
        for index, site in enumerate(measured, 1):
            distance = site.minimum_distance_m * 1000
            diameter = site.required_separation_m * 1000
            lines.append((f'• Location {index}: centerline distance {distance:.4g} mm; '
                          f'required {diameter:.4g} mm.') if english else
                         (f'• Lugar {index}: distancia entre ejes {distance:.4g} mm; '
                          f'se requieren {diameter:.4g} mm.'))
        lines.append(
            'The pipeline stopped before leads and shell because automatic repair could '
            'not obtain clearance within its limits. Review the available winding space '
            '(radius and height), wire diameter, number of turns or interconnection route.'
            if english else
            'El pipeline se detuvo antes de los terminales y el molde porque la reparación '
            'automática no consiguió la separación dentro de sus límites. Revise el espacio '
            'disponible para el bobinado (radio y altura), el diámetro del cable, el número '
            'de vueltas o el trazado de interconexión.')
        return '\n'.join(lines)

    def user_question(self, language: str = "es") -> str:
        """Warning shown between gradient generation and leads/shell.

        Spanish remains the default for compatibility with historical CLI
        callers; the English-default GUI passes its current language.
        """
        if not self.sites:
            return ""
        physical_failure = self.physical_interference_message(language)
        if physical_failure:
            return physical_failure
        if language == "en":
            if len(self.sites) == 1:
                site = self.sites[0]
                description = (
                    f"{site.cable_count} cables are trying to pass through the same location; "
                    f"1 will remain in the outer layer and "
                    f"{site.inner_layer_count} in the inner layer."
                )
            else:
                lines = [
                    f"{len(self.sites)} locations with three or more cables were detected:"
                ]
                for index, site in enumerate(self.sites, start=1):
                    lines.append(
                        f"• Location {index}: {site.cable_count} cables; 1 will remain "
                        f"in the outer layer and {site.inner_layer_count} in the inner layer."
                    )
                description = "\n".join(lines)
            return (
                f"{description}\n\n"
                "Do you want to continue or discard the result?\n\n"
                "Yes: continue with leads and shell.\n"
                "No: discard this result and stop the pipeline."
            )
        if len(self.sites) == 1:
            site = self.sites[0]
            description = (
                f"Hay {site.cable_count} cables intentando pasar por el mismo lugar; "
                f"entonces 1 quedará en la capa externa y "
                f"{site.inner_layer_count} quedarán en la interna."
            )
        else:
            lines = [
                f"Se detectaron {len(self.sites)} lugares con tres o más cables:"
            ]
            for index, site in enumerate(self.sites, start=1):
                lines.append(
                    f"• Lugar {index}: hay {site.cable_count} cables; 1 quedará "
                    f"en la capa externa y {site.inner_layer_count} quedarán en la interna."
                )
            description = "\n".join(lines)
        return (
            f"{description}\n\n"
            "¿Desea continuar o descartar el resultado?\n\n"
            "Sí: continuar con leads y shell.\n"
            "No: descartar este resultado y detener el pipeline."
        )


@dataclass(frozen=True)
class _CrossingRecord:
    point_uv: np.ndarray
    segment_a: int
    segment_b: int
    path_position_a: float
    path_position_b: float
    layer_factor_a: float
    layer_factor_b: float


def _metadata_for_part(part) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Read stored crossing metadata, with a fallback for older solutions."""
    points = getattr(part, 'crossing_points_uv', None)
    segments = getattr(part, 'crossing_segments', None)
    positions = getattr(part, 'crossing_path_positions', None)
    layers = getattr(part, 'crossing_layer_factors', None)
    if points is not None and segments is not None and positions is not None:
        points = np.asarray(points, dtype=float).reshape(-1, 2)
        segments = np.asarray(segments, dtype=int).reshape(-1, 2)
        positions = np.asarray(positions, dtype=float).reshape(-1, 2)
        if layers is not None:
            layers = np.asarray(layers, dtype=float).reshape(-1, 2)
        else:
            layers = _layer_factors_from_part(part, points, segments)
        return points, segments, positions, layers

    # Compatibility path for solutions produced before crossing metadata was
    # persisted. New GUI runs never need this comparatively expensive pass.
    wire_path = getattr(part, 'wire_path', None)
    if wire_path is None or wire_path.uv is None or wire_path.v is None:
        empty_f = np.empty((0, 2), dtype=float)
        return empty_f, np.empty((0, 2), dtype=int), empty_f, empty_f

    from pyCoilGen.sub_functions.shift_return_paths import (
        InterX, intersection_points_for_pairs,
    )

    _unused_points, segments = InterX(np.asarray(wire_path.uv, dtype=float))
    segments = np.asarray(segments, dtype=int)
    if segments.size == 0:
        empty_f = np.empty((0, 2), dtype=float)
        return empty_f, np.empty((0, 2), dtype=int), empty_f, empty_f
    segments = segments.reshape(-1, 2)
    points = intersection_points_for_pairs(wire_path.uv, segments)
    lengths = np.linalg.norm(np.diff(wire_path.v, axis=1), axis=0)
    point_positions = np.concatenate(([0.0], np.cumsum(lengths)))
    segment_positions = 0.5 * (point_positions[:-1] + point_positions[1:])
    layers = _layer_factors_from_part(part, points, segments)
    return points, segments, segment_positions[segments], layers


def _layer_factors_from_part(part, points: np.ndarray,
                             segments: np.ndarray) -> np.ndarray:
    """Recover layer factors for solutions saved before they were persisted."""
    shift_array = getattr(part, 'shift_array', None)
    wire_path = getattr(part, 'wire_path', None)
    if shift_array is None or wire_path is None or wire_path.uv is None:
        # Unknown is deliberately treated as separated. Guessing from crossing
        # proximity was the source of the false positives this detector replaces.
        return np.column_stack((np.zeros(len(points)), np.ones(len(points))))

    from pyCoilGen.sub_functions.shift_return_paths import layer_factors_for_crossings

    shifts = np.asarray(shift_array, dtype=float)
    uv = np.asarray(wire_path.uv, dtype=float)
    if (not len(segments)
            or np.max(segments) + 1 >= uv.shape[1]
            or np.max(segments) + 1 >= len(shifts)):
        return np.column_stack((np.zeros(len(points)), np.ones(len(points))))
    return layer_factors_for_crossings(uv, segments, points, shifts)


def _cluster_records(records: list[_CrossingRecord], tolerance: float) -> list[list[int]]:
    """Connected components of crossing points separated by at most tolerance."""
    count = len(records)
    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for left in range(count):
        for right in range(left + 1, count):
            if np.linalg.norm(records[left].point_uv - records[right].point_uv) <= tolerance:
                union(left, right)

    components: dict[int, list[int]] = {}
    for index in range(count):
        components.setdefault(find(index), []).append(index)
    return list(components.values())


def _count_path_branches(path_positions: list[float], merge_distance: float) -> int:
    """Merge repeated intersections belonging to the same nearby path branch."""
    if not path_positions:
        return 0
    ordered = sorted(float(value) for value in path_positions)
    branches = 1
    previous = ordered[0]
    for position in ordered[1:]:
        if position - previous > merge_distance:
            branches += 1
        previous = position
    return branches



def _geometric_sites(part, part_index, cfg, tolerance):
    path = np.asarray(part.wire_path.v, dtype=float).T
    diameter = float(cfg.wire.conductor_width)
    # A real pre-lead sweep closes its last ring onto its first, regardless of
    # their distance. Keep support for genuinely open diagnostic-only paths.
    closed = (getattr(part, 'layout_surface_mesh', None) is not None
              or (getattr(part, 'clearance_report', None) or {}).get('closed_loop', False)
              or np.linalg.norm(path[0] - path[-1]) <= diameter)
    if closed:
        path = closed_wire_path(path)
    i, j, distances, positions = wire_contact_pairs(path, diameter, closed=closed)
    if not len(i):
        return []
    # Clustering affects the number of displayed locations only. Every
    # nonlocal segment pair closer than the real diameter has already failed.
    centers = (path[i] + path[i+1] + path[j] + path[j+1]) / 4
    records = [_CrossingRecord(center, int(a), int(b),
                               float(positions[a]), float(positions[b]), 0., 0.)
               for center, a, b in zip(centers, i, j)]
    sites = []
    for component in _cluster_records(records, tolerance):
        component = np.asarray(component, int)
        segments = tuple(map(int, sorted(set(i[component]) | set(j[component]))))
        branch_positions = [float(positions[k]) for k in segments]
        branches = max(2, _count_path_branches(branch_positions, 1.5*tolerance))
        center = centers[component].mean(axis=0)
        uv = getattr(part.wire_path, 'uv', None)
        location = (np.asarray(uv)[:, segments].mean(axis=1) if uv is not None
                    else center[:2])
        sites.append(CollisionSite(part_index, tuple(map(float, location)), branches,
                                   len(component), segments, tuple(map(float, center)),
                                   float(distances[component].min()), diameter))
    return sites


def detect_collisions(solution, cfg: Config) -> OverlapReport:
    """Check the real round conductor, including ramps outside UV crossings."""
    # A layer transition occupies space on both sides of its exact geometric
    # crossing. Treat crossings within 2.5 cable heights/widths as the same
    # congestion zone; this catches neighbouring crossings whose smoothed
    # ramps overlap while continuing to scale with the selected conductor.
    cable_footprint = max(
        float(cfg.cable_height),
        float(2.0 * cfg.conductor_semi_b),
        float(cfg.winding.cut_width),
    )
    tolerance = 2.5 * max(float(cfg.overlap_clearance), 0.0) * cable_footprint
    merge_distance = 1.5 * tolerance
    sites: list[CollisionSite] = []
    layer_shift = abs(float(cfg.normal_shift_length))
    required_separation = float(cfg.cable_height)

    for part_index, part in enumerate(getattr(solution, 'coil_parts', [])):
        wire_path = getattr(part, 'wire_path', None)
        if wire_path is not None and getattr(wire_path, 'v', None) is not None:
            sites.extend(_geometric_sites(part, part_index, cfg, tolerance))
            continue
        # Compatibility for old metadata-only diagnostics without a 3D path.
        points, segments, positions, layers = _metadata_for_part(part)
        records = [
            _CrossingRecord(points[index], int(segments[index, 0]),
                            int(segments[index, 1]), float(positions[index, 0]),
                            float(positions[index, 1]), float(layers[index, 0]),
                            float(layers[index, 1]))
            for index in range(len(points))
            if np.all(np.isfinite(points[index]))
            and np.all(np.isfinite(layers[index]))
            # Different layer factors create radial clearance. Equal factors
            # identify the actual X left by pyCoilGen, regardless of how many
            # harmless projected crossings happen to be nearby.
            and (abs(float(layers[index, 0]) - float(layers[index, 1]))
                 * layer_shift + 1e-12 < required_separation)
        ]
        if not records:
            continue

        for component in _cluster_records(records, tolerance):
            component_records = [records[index] for index in component]
            path_positions: list[float] = []
            segment_indices: set[int] = set()
            for record in component_records:
                path_positions.extend((record.path_position_a, record.path_position_b))
                segment_indices.update((record.segment_a, record.segment_b))
            colliding_inner_branches = max(
                2, _count_path_branches(path_positions, merge_distance))
            # The same-layer X is formed by the n-1 branches that pyCoilGen
            # sent inward after leaving one competing cable on the outer layer.
            cable_count = colliding_inner_branches + 1
            location = np.mean([record.point_uv for record in component_records], axis=0)
            sites.append(CollisionSite(
                part_index=part_index,
                location_uv=(float(location[0]), float(location[1])),
                cable_count=cable_count,
                crossing_count=len(component_records),
                segment_indices=tuple(sorted(segment_indices)),
            ))

    sites.sort(key=lambda site: (-site.cable_count, site.part_index, site.location_uv))
    return OverlapReport(sites=sites, cluster_tolerance_m=tolerance)
