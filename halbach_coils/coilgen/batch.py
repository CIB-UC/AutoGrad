"""Selected concentric gradient designs using sequential or parallel pipelines.

Lengths use metres. One anchor radius and the gap between complete gradient
envelopes define the selected concentric layers. Each envelope contains both the
former and the cable/groove, including crossings. Former wall thicknesses use
the existing pipeline formula. Per-axis tuples always use X, Y, Z order.
``axis_order`` selects the axes and their inside-to-outside order. Complete wire envelopes are
reported separately and the actual assembly must pass its final 3D check.
"""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import time
from typing import Callable

import numpy as np

from .config import Config, preset_for
from .output_layout import name, locate, variants
from .paths import output_base
from .paths import PIPELINE_OUTPUT_BASE, unique_run_dir


@dataclass
class BatchConfig:
    base: Config = field(default_factory=Config)
    anchor_radius: float = 0.0265
    radius_mode: str = 'inner'
    radial_gap: float = 0.0003
    axis_order: tuple[str, ...] = ('z', 'x', 'y')
    tikhonov_factors: tuple[float, float, float] | None = None
    num_levels: tuple[int, int, int] | None = None
    conductor_widths: tuple[float, float, float] | None = None
    layer_gaps: tuple[float, float, float] | None = None
    output_dir: str = ''
    include_keys: bool = True
    key_length: float = 0.004
    key_width: float = 0.004
    fit_clearance: float = 0.0003
    include_b0_markers: bool = False
    cut_widths: tuple[float, float, float] | None = None
    shift_smooth_factors: tuple[tuple[int, int, int], ...] | None = None
    parallel_gradients: bool = False


@dataclass(frozen=True)
class BatchResult:
    output_dir: str
    completed: bool
    layers: tuple
    summary_path: str
    manifest_path: str
    assembly: dict | None = None
    message: str = ''
    layer_axes: tuple[str, ...] = ()


def _positive(value, name, *, allow_zero=False) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f'{name} must be finite and {"non-negative" if allow_zero else "positive"}.')
    return number


def gradient_radial_bounds(cfg: Config) -> tuple[float, float]:
    """Complete radial extent, including the parts outside the plastic former."""
    centers = (cfg.cylinder_design_radius,
               cfg.cylinder_design_radius + cfg.normal_shift_length)
    wire_radius = cfg.wire.conductor_width / 2
    return (min(cfg.shell_inner_radius, cfg.estimated_wire_inner_radius, min(centers)-wire_radius),
            max(cfg.shell_outer_radius, cfg.estimated_wire_outer_radius, max(centers)+wire_radius))


def build_layer_configs(batch: BatchConfig) -> tuple[Config, ...]:
    """Validate and derive each layer without changing the shared input Config.

    ``radius_mode='inner'`` fixes the innermost complete gradient's inner
    radius; ``outer`` fixes the outermost complete gradient's outer radius.
    ``radial_gap = Rinner(next gradient) - Router(previous gradient)``.
    The plastic faces are derived separately; exposed cable must not consume
    the gap requested by the user. Final CAD still checks actual leads/keys.
    """
    base = batch.base
    anchor_radius = _positive(batch.anchor_radius, 'Anchor radius')
    gap = _positive(batch.radial_gap, 'Inter-gradient gap', allow_zero=True)
    if batch.radius_mode not in ('inner', 'outer'):
        raise ValueError('Radius mode must be inner or outer.')
    key_length = _positive(batch.key_length, 'Key axial length')
    key_width = _positive(batch.key_width, 'Key tangential width')
    fit_clearance = _positive(batch.fit_clearance, 'Key fit clearance')
    if fit_clearance >= min(key_length, key_width):
        raise ValueError('Key fit clearance must be smaller than key width and length.')
    order = tuple(str(axis).lower() for axis in batch.axis_order)
    if not order or len(set(order)) != len(order) or not set(order) <= {'x', 'y', 'z'}:
        raise ValueError('Select at least one gradient (X, Y or Z), without duplicates.')
    if base.shell.use_custom_stl:
        raise ValueError('Batch design requires generated cylindrical shells, not custom STL shells.')
    if not np.allclose(base.rotated_cylinder_axis, (0, 0, 1), atol=1e-10):
        raise ValueError('Batch design requires a longitudinal +Z cylinder.')
    if not all((base.control.run_gradient, base.control.run_leads, base.control.run_shell)):
        raise ValueError('Batch design must run gradient, leads and shell for all selected axes.')
    _positive(base.wire.conductor_width, 'Wire diameter')
    _positive(base.conductor_semi_a, 'Groove radial semi-axis')
    _positive(base.conductor_semi_b, 'Groove tangential semi-axis')
    _positive(base.cylinder.height, 'Cylinder height')
    if not 0 < float(base.cylinder.mesh_length_factor) <= 1:
        raise ValueError('The winding length factor must lie between zero and one.')
    roi = tuple(_positive(value, 'ROI semi-axis')
                for value in (base.target.rx, base.target.ry, base.target.rz))
    if roi[2] >= base.cylinder.height / 2:
        raise ValueError('The ROI must fit inside the cylinder height.')

    factors = batch.tikhonov_factors
    if factors is None:
        factors = (base.tikhonov_factor,) * 3
    levels = batch.num_levels
    if levels is None:
        levels = (base.num_levels,) * 3
    if len(factors) != 3 or len(levels) != 3:
        raise ValueError('Supply exactly three Tikhonov factors and level counts in X, Y, Z order.')
    factors = tuple(_positive(value, 'Tikhonov factor') if axis in order else value
                    for axis, value in zip('xyz', factors))
    if any(isinstance(value, bool) or int(value) != value or value < 2
           for axis, value in zip('xyz', levels) if axis in order):
        raise ValueError('Each contour level count must be an integer of at least two.')

    widths = (batch.conductor_widths if batch.conductor_widths is not None
              else (base.wire.conductor_width,) * 3)
    layer_gaps = (batch.layer_gaps if batch.layer_gaps is not None
                  else (base.winding.layer_gap_mm,) * 3)
    if len(widths) != 3 or len(layer_gaps) != 3:
        raise ValueError('Supply three wire diameters and layer gaps in X, Y, Z order.')
    widths = tuple(_positive(value, 'Wire diameter') if axis in order else value
                   for axis, value in zip('xyz', widths))
    layer_gaps = tuple(_positive(value, 'Layer crossing gap', allow_zero=True) if axis in order else value
                       for axis, value in zip('xyz', layer_gaps))
    cut_widths = batch.cut_widths if batch.cut_widths is not None else (base.winding.cut_width,) * 3
    smooth_factors = (batch.shift_smooth_factors if batch.shift_smooth_factors is not None
                      else (base.winding.normal_shift_smooth,) * 3)
    if len(cut_widths) != 3 or len(smooth_factors) != 3:
        raise ValueError('Supply three connection widths and smoothing triples in X, Y, Z order.')
    cut_widths = tuple(_positive(value, 'Connection cut width') if axis in order else value
                       for axis, value in zip('xyz', cut_widths))
    if any(len(factors) != 3 or any(isinstance(v, bool) or int(v) != v or not 1 <= v <= 101
                                  for v in factors)
           for axis, factors in zip('xyz', smooth_factors) if axis in order):
        raise ValueError('Each shift smoothing triple must contain three integers from 1 to 101.')
    configs = []
    for index, axis in enumerate(order):
        cfg = deepcopy(base)
        # Choose one clear B0 side jointly after all selected shells are available.
        cfg.shell.b0_marker = False
        cfg.gradient_axis = axis
        cfg.leads.preset = deepcopy(preset_for(axis))
        axis_index = 'xyz'.index(axis)
        cfg.tikhonov_factor = factors[axis_index]
        cfg.num_levels = int(levels[axis_index])
        cfg.wire.conductor_width = widths[axis_index]
        cfg.winding.layer_gap_mm = layer_gaps[axis_index]
        cfg.winding.cut_width = cut_widths[axis_index]
        cfg.winding.normal_shift_smooth = list(smooth_factors[axis_index])
        _positive(cfg.shell_wall_thickness, f'{cfg.axis_label} derived shell wall thickness')
        cfg.output_dir = (str(Path(batch.output_dir).resolve() / f'{index + 1:02d}_G{axis}')
                          if batch.output_dir else '')
        cfg.show_plots = False
        configs.append(cfg)
    # All radius-derived geometry translates linearly with cylinder.radius.
    # Work out each layer's full width before placing any layer, so both
    # anchor modes and different cable sizes use exactly the same gap.
    extents = []
    for cfg in configs:
        low, high = gradient_radial_bounds(cfg)
        extents.append((cfg.shell_inner_radius - low, high - cfg.shell_outer_radius))
    widths = [cfg.shell_wall_thickness + low + high
              for cfg, (low, high) in zip(configs, extents)]
    inner_radius = (anchor_radius if batch.radius_mode == 'inner' else
                    anchor_radius - sum(widths) - (len(configs) - 1) * gap)
    if inner_radius <= max(roi[:2]):
        raise ValueError('The ROI must fit inside the innermost gradient; increase the anchor radius or reduce thickness/gap.')
    next_inner = inner_radius
    for cfg, (protrudes_in, protrudes_out) in zip(configs, extents):
        cfg.cylinder.radius = next_inner + protrudes_in + cfg.shell_wall_thickness
        next_inner = cfg.shell_outer_radius + protrudes_out + gap
    return tuple(configs)


def _layer_record(cfg: Config, index: int) -> dict:
    return {
        'layer': index + 1,
        'axis': cfg.gradient_axis,
        'status': 'pending',
        'directory': f'{index + 1:02d}_G{cfg.gradient_axis}',
        'tikhonov_factor': cfg.tikhonov_factor,
        'num_levels': cfg.num_levels,
        'conductor_width_m': cfg.wire.conductor_width,
        'layer_crossing_gap_m': cfg.winding.layer_gap_mm,
        'interconnection_cut_width_m': cfg.winding.cut_width,
        'normal_shift_smooth_factors': list(cfg.winding.normal_shift_smooth),
        'shell_wall_thickness_m': cfg.shell_wall_thickness,
        'gradient_inner_radius_m': gradient_radial_bounds(cfg)[0],
        'gradient_outer_radius_m': gradient_radial_bounds(cfg)[1],
        'shell_inner_radius_m': cfg.shell_inner_radius,
        'shell_outer_radius_m': cfg.shell_outer_radius,
        'wire_inner_radius_m': cfg.estimated_wire_inner_radius,
        'wire_outer_radius_m': cfg.estimated_wire_outer_radius,
    }


def _write_report(root: Path, document: dict) -> tuple[str, str]:
    complete_gap = document.get('format_version', 1) >= 2
    language = document.get('output_language', 'es')
    manifest = root / name('batch_manifest', language)
    temporary = manifest.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(document, indent=2, ensure_ascii=False,
                                    allow_nan=False) + '\n', encoding='utf-8')
    for attempt in range(6):
        try:
            os.replace(temporary, manifest)
            break
        except PermissionError as exc:
            # Windows scanners/readers can briefly deny atomic replacement.
            # Keep the old manifest intact and retry only sharing/access locks.
            if os.name != 'nt' or getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == 5:
                raise
            time.sleep(.02 * (attempt + 1))
    lines = _spanish_report_lines(document) if language == 'es' else _english_report_lines(document)
    summary = root / name('batch_summary', language)
    summary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return str(summary), str(manifest)


def _spanish_report_lines(document):
    complete_gap = document.get('format_version', 1) >= 2
    lines = [
        'CONJUNTO DE GRADIENTES ' + ' / '.join('G' + layer['axis'].upper()
                                              for layer in document['layers']),
        'Estado: ' + document['status'],
        'Generación de gradientes: ' + ('simultánea, un proceso por gradiente'
                                      if document.get('parallel_gradients') else 'secuencial'),
        'Orden interior → exterior: ' + ' → '.join('G' + item['axis'].upper()
                                                    for item in document['layers']),
        f"B0 compartido: {document['b0_direction'].upper()}",
        'Marcas B0 en los moldes seleccionados: ' +
        ('activadas' if document.get('include_b0_markers') else 'desactivadas'),
        f"Radio ancla {'del gradiente completo' if complete_gap else 'del molde'} ({document['radius_mode']}): {document['anchor_radius_m'] * 1000:.6g} mm",
        f"Radio interior del molde: {document['shell_inner_radius_m'] * 1000:.6g} mm",
        f"Radio exterior del molde: {document['shell_outer_radius_m'] * 1000:.6g} mm",
        f"Radio interior del cable estimado: {document['wire_inner_radius_m'] * 1000:.6g} mm",
        f"Gap radial {'entre gradientes completos' if complete_gap else 'entre cuerpos de moldes'}: {document['radial_gap_m'] * 1000:.6g} mm",
        ('Gap = Rint del gradiente exterior - Rext del gradiente interior, incluyendo cable y ranuras.'
         if complete_gap else 'Formato anterior: el gap no incluía las partes de cable fuera del molde.'),
        'Las caras de plástico del molde se indican por separado.',
        '',
    ]
    if document.get('requires_interference_check'):
        lines.extend(['Las envolventes radiales de cable coinciden o se acercan a la ROI.',
                      'Se debe comprobar la separación 3D real antes de completar el ensamble.', ''])
    for layer in document['layers']:
        gradient_inner = layer.get('gradient_inner_radius_m', min(layer['shell_inner_radius_m'], layer['wire_inner_radius_m']))
        gradient_outer = layer.get('gradient_outer_radius_m', max(layer['shell_outer_radius_m'], layer['wire_outer_radius_m']))
        lines.extend([
            f"{layer['directory']}/: {layer['status']}",
            f"  Rint / Rext del gradiente completo: {gradient_inner * 1000:.6g} / "
            f"{gradient_outer * 1000:.6g} mm",
            f"  Rint / Rext del molde: {layer['shell_inner_radius_m'] * 1000:.6g} / "
            f"{layer['shell_outer_radius_m'] * 1000:.6g} mm",
            f"  Envolvente del cable: {layer['wire_inner_radius_m'] * 1000:.6g} / "
            f"{layer['wire_outer_radius_m'] * 1000:.6g} mm",
            f"  Tikhonov: {layer['tikhonov_factor']:.8g}; niveles: {layer['num_levels']}",
            f"  Cable: {layer['conductor_width_m'] * 1000:.6g} mm; "
            f"gap de cruce: {layer['layer_crossing_gap_m'] * 1000:.6g} mm; "
            f"pared: {layer['shell_wall_thickness_m'] * 1000:.6g} mm",
            '  Consultar Resumen.txt de esa capa para campo, resistencia e inductancia.',
        ])
        if layer.get('error'):
            lines.append('  Motivo: ' + layer['error'])
    if document.get('assembly'):
        lines.extend([
            '',
            'CONJUNTO VALIDADO',
            f"Conjunto/: {len(document['layers'])} STL finales de montaje en mm, escena GLB y encajes.json.",
            'Usar los STL de Conjunto/ para el montaje.',
        ])
        markers = document['assembly'].get('b0_markers', {})
        if markers.get('enabled'):
            lines.append(f"Marcas B0 alineadas en los moldes seleccionados a {markers['angle_deg']:.6g}°.")
        for interface in document['assembly'].get('interfaces', ()):
            lines.append(
                f"  G{interface['inner_axis'].upper()} → G{interface['outer_axis'].upper()}: "
                f"{interface['angle_deg']:.6g}°; holgura por lado "
                f"{interface['side_clearance_mm']:.6g} mm; "
                f"holgura axial {interface['axial_clearance_mm']:.6g} mm.")
    if document.get('error'):
        lines.extend(['', 'Motivo: ' + document['error']])
    if document['status'] != 'complete':
        lines.extend(['', 'El conjunto está incompleto. No se debe tratar como un ensamble terminado.'])
    return lines


def _english_report_lines(document):
    lines = [
        'GRADIENT ASSEMBLY ' + ' / '.join('G' + layer['axis'].upper() for layer in document['layers']),
        'Status: ' + document['status'],
        'Gradient generation: ' + ('parallel, one process per gradient' if document.get('parallel_gradients') else 'sequential'),
        'Inside-to-outside order: ' + ' → '.join('G' + item['axis'].upper() for item in document['layers']),
        'Shared B0: ' + document['b0_direction'].upper(),
        'B0 marks: ' + ('enabled' if document.get('include_b0_markers') else 'disabled'),
        f"Anchor radius ({document['radius_mode']}): {document['anchor_radius_m'] * 1000:.6g} mm",
        f"Mold inner / outer radius: {document['shell_inner_radius_m'] * 1000:.6g} / {document['shell_outer_radius_m'] * 1000:.6g} mm",
        f"Estimated wire inner radius: {document['wire_inner_radius_m'] * 1000:.6g} mm",
        f"Radial gap: {document['radial_gap_m'] * 1000:.6g} mm",
        'The gap separates complete gradient envelopes, including cable and grooves.',
        'Plastic mold radii are reported separately.', '',
    ]
    if document.get('requires_interference_check'):
        lines.extend(['Real 3D clearance must be checked before completing the assembly.', ''])
    for layer in document['layers']:
        inner = layer.get('gradient_inner_radius_m', min(layer['shell_inner_radius_m'], layer['wire_inner_radius_m']))
        outer = layer.get('gradient_outer_radius_m', max(layer['shell_outer_radius_m'], layer['wire_outer_radius_m']))
        lines.extend([
            f"{layer['directory']}/: {layer['status']}",
            f"  Complete gradient inner / outer radius: {inner * 1000:.6g} / {outer * 1000:.6g} mm",
            f"  Mold inner / outer radius: {layer['shell_inner_radius_m'] * 1000:.6g} / {layer['shell_outer_radius_m'] * 1000:.6g} mm",
            f"  Wire envelope: {layer['wire_inner_radius_m'] * 1000:.6g} / {layer['wire_outer_radius_m'] * 1000:.6g} mm",
            f"  Tikhonov: {layer['tikhonov_factor']:.8g}; levels: {layer['num_levels']}",
            f"  Cable: {layer['conductor_width_m'] * 1000:.6g} mm; crossing gap: {layer['layer_crossing_gap_m'] * 1000:.6g} mm; wall: {layer['shell_wall_thickness_m'] * 1000:.6g} mm",
            '  See the layer Summary.txt for final field, resistance and inductance.',
        ])
        if layer.get('error'): lines.append('  Reason: ' + layer['error'])
    if document.get('assembly'):
        lines.extend(['', 'VALIDATED ASSEMBLY',
                      f"Assembly/: {len(document['layers'])} final mold STLs in mm, Gradients.glb and keys.json.",
                      'Use the STLs in Assembly/ for manufacture.'])
        markers = document['assembly'].get('b0_markers', {})
        if markers.get('enabled'): lines.append(f"Aligned B0 marks: {markers['angle_deg']:.6g}°.")
        for interface in document['assembly'].get('interfaces', ()):
            lines.append(f"  G{interface['inner_axis'].upper()} → G{interface['outer_axis'].upper()}: {interface['angle_deg']:.6g}°; side clearance {interface['side_clearance_mm']:.6g} mm; axial clearance {interface['axial_clearance_mm']:.6g} mm.")
    if document.get('error'): lines.extend(['', 'Reason: ' + document['error']])
    if document['status'] != 'complete': lines.extend(['', 'The assembly is incomplete. Do not treat it as a finished assembly.'])
    return lines


def run_batch(batch: BatchConfig, should_stop=None, ask_user=None,
              question_language='en', on_progress=None,
              finalize: Callable | None = None) -> BatchResult:
    """Run selected axes, retaining expected geometry failures for revision.

    A geometric infeasibility keeps the other axes running and prevents final
    assembly. Cancellation/discard and unexpected program errors still stop.

    ``finalize(batch, layer_configs, layer_results)`` may add assembly geometry
    and returns a small artifact dictionary. It runs only after all pipelines
    finish. GUI cancellation terminates this worker process; ``lote.json`` and
    its per-layer reports preserve the last known stage for partial outputs.
    ``batch.parallel_gradients`` spawns one independent process per gradient;
    only the coordinator writes the batch report and performs final assembly.
    """
    configs = build_layer_configs(batch)
    if finalize is None:
        from .assembly import finalize_batch
        finalize = finalize_batch
    root = Path(batch.output_dir).resolve() if batch.output_dir else Path(
        unique_run_dir(output_base(batch.base.output_language), name('batch', batch.base.output_language) + '_' + '_'.join(
            'G' + axis for axis in 'xyz' if axis in {cfg.gradient_axis for cfg in configs})))
    # A new batch never reuses/overwrites results from an earlier batch.
    if any((root / item).exists() for item in variants('batch_manifest')) or any((root / f'{i + 1:02d}_G{cfg.gradient_axis}').exists()
                                          for i, cfg in enumerate(configs)):
        raise FileExistsError('The batch output folder already contains a batch; choose a new folder.')
    root.mkdir(parents=True, exist_ok=True)
    working_batch = deepcopy(batch)
    working_batch.output_dir = str(root)
    configs = build_layer_configs(working_batch)
    document = {
        'format_version': 2,
        'output_language': batch.base.output_language,
        'coordinate_frame': 'physical_xyz',
        'status': 'running',
        'b0_direction': configs[0].b0_direction,
        'anchor_radius_m': float(batch.anchor_radius),
        'radius_mode': batch.radius_mode,
        'shell_inner_radius_m': configs[0].shell_inner_radius,
        'shell_outer_radius_m': configs[-1].shell_outer_radius,
        'gradient_inner_radius_m': gradient_radial_bounds(configs[0])[0],
        'gradient_outer_radius_m': gradient_radial_bounds(configs[-1])[1],
        'wire_inner_radius_m': configs[0].estimated_wire_inner_radius,
        'radial_gap_m': float(batch.radial_gap),
        'radial_gap_definition': 'complete_gradient_envelopes_including_cable_and_groove',
        'requires_interference_check': (
            configs[0].estimated_wire_inner_radius <= max(configs[0].target.rx, configs[0].target.ry)
            or any(right.estimated_wire_inner_radius < left.estimated_wire_outer_radius
                   for left, right in zip(configs, configs[1:]))),
        'roi_m': [configs[0].target.rx, configs[0].target.ry, configs[0].target.rz],
        'height_m': configs[0].cylinder.height,
        'include_keys': batch.include_keys,
        'include_b0_markers': batch.include_b0_markers,
        'parallel_gradients': batch.parallel_gradients,
        'selected_axes': [cfg.gradient_axis for cfg in configs],
        'key_length_m': float(batch.key_length),
        'key_width_m': float(batch.key_width),
        'fit_clearance_m': float(batch.fit_clearance),
        'layers': [_layer_record(cfg, index) for index, cfg in enumerate(configs)],
    }
    summary, manifest = _write_report(root, document)
    results = {}
    assembly = None

    def stop_requested():
        return bool(should_stop and should_stop())

    def partial(status):
        document['status'] = status
        for layer in document['layers']:
            if layer['status'] == 'running':
                layer['status'] = 'cancelled'
        _write_report(root, document)
        return BatchResult(str(root), False, ordered_results(), summary, manifest,
                           layer_axes=tuple(configs[i].gradient_axis for i in sorted(results)))

    def ordered_results():
        return tuple(results[i] for i in sorted(results))

    def on_start(index, cfg):
        layer = document['layers'][index]
        layer['status'] = 'running'
        _write_report(root, document)
        print(f"\n[{index + 1}/{len(configs)}] Designing {cfg.axis_label}, "
              f"shell R={cfg.shell_inner_radius * 1000:.3f}–{cfg.shell_outer_radius * 1000:.3f} mm")
        if on_progress:
            on_progress('batch', index + 1, 'start', layer)

    from .batch_parallel import iter_layer_runs
    with closing(iter_layer_runs(
        configs, parallel=batch.parallel_gradients, should_stop=should_stop,
        ask_user=ask_user, question_language=question_language, on_start=on_start,
    )) as runs:
        for index, result, error in runs:
            cfg = configs[index]
            layer = document['layers'][index]
            try:
                if error is not None:
                    raise error
                results[index] = result
                if stop_requested():
                    layer['status'] = 'cancelled'
                    return partial('cancelled')
                if result.discarded:
                    layer['status'] = 'discarded'
                    return partial('discarded')
                if result.needs_revision:
                    layer['status'] = 'needs_revision'
                    layer['error'] = result.message
                    if result.geometry_report_path:
                        layer['geometry_report_path'] = str(Path(result.geometry_report_path).relative_to(root))
                    _write_report(root, document)
                    if on_progress:
                        on_progress('batch', len(results), 'needs_revision', layer)
                    continue
                if not any(locate(result.output_dir, 'mold').glob('*.stl')):
                    raise RuntimeError(f'{cfg.axis_label} did not produce a completed shell.')
                if not result.metrics_path or not Path(result.metrics_path).is_file():
                    raise RuntimeError(f'{cfg.axis_label} did not produce final-conductor metrics.')
            except Exception as exc:
                layer['status'] = 'failed'
                layer['error'] = str(exc)
                document['error'] = f'{cfg.axis_label}: {exc}'
                document['status'] = 'failed'
                for other in document['layers']:
                    if other['status'] == 'running':
                        other['status'] = 'cancelled'
                _write_report(root, document)
                raise
            layer['status'] = 'complete'
            layer['metrics_path'] = str(Path(result.metrics_path).relative_to(root))
            _write_report(root, document)
            if on_progress:
                on_progress('batch', len(results), 'complete', layer)
    if stop_requested():
        return partial('cancelled')
    if any(layer['status'] == 'needs_revision' for layer in document['layers']):
        return partial('needs_revision')
    if finalize is not None:
        from .assembly import AssemblyFeasibilityError
        document['status'] = 'assembly'
        _write_report(root, document)
        try:
            assembly = finalize(working_batch, configs, ordered_results())
        except AssemblyFeasibilityError as exc:
            document['status'] = 'needs_revision'
            document['error'] = 'Assembly: ' + str(exc)
            _write_report(root, document)
            return BatchResult(str(root), False, ordered_results(), summary, manifest,
                               message=document['error'],
                               layer_axes=tuple(cfg.gradient_axis for cfg in configs))
        except Exception as exc:
            document['status'] = 'failed'
            document['error'] = 'Assembly: ' + str(exc)
            _write_report(root, document)
            raise
        document['assembly'] = assembly
    if stop_requested():
        return partial('cancelled')
    document['status'] = 'complete'
    _write_report(root, document)
    return BatchResult(str(root), True, ordered_results(), summary, manifest, assembly,
                       layer_axes=tuple(cfg.gradient_axis for cfg in configs))
