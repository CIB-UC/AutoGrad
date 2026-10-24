"""Arrange generated files by stage, preserving names and reusable sidecars."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from .output_layout import name, locate, variants, remember_language, language_for


def result_subfolder(filename: str, language: str = 'en') -> str | None:
    """Only recognize application outputs; leave unrelated user files alone."""
    if filename.endswith('_geometry.json'):
        return name('diagnostics', language)
    if '_field_' in filename and filename.endswith('.png'):
        return name('plots', language) + ('' if '_with_leads' in filename else '/CoilGen')
    if '_shell_' in filename and filename.endswith('.stl'):
        return name('mold', language)
    if any(tag in filename for tag in ('_with_leads', '_coil_open', '_leads_only')):
        if filename.endswith(('.stl', '.npz', '.json')):
            return name('leads', language)
    if (('_wire_' in filename and filename.endswith(('.stl', '_design.json', '_lead_reference.npz')))
            or filename.endswith(('_field_data.npz', '_metrics.txt'))):
        return name('coil', language)
    return None


def relocate_paths(value, moves: dict[str, str]):
    """Update returned artifacts and stored JSON references after moving files."""
    if isinstance(value, dict):
        return {key: relocate_paths(item, moves) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [relocate_paths(item, moves) for item in value]
    if isinstance(value, str):
        normalized = os.path.normcase(value)
        for old, new in moves.items():
            if normalized == os.path.normcase(old):
                return new
            if normalized.startswith(os.path.normcase(old + os.sep)):
                return new + value[len(old):]
    return value


def organize_outputs(output_dir, *, replace=False, language='en') -> dict[str, str]:
    """Move only known outputs, checking all destinations before any mutation.

    STL sidecars stay beside their STL. No numerical arrays are rewritten, so
    provenance hashes remain valid. Existing flat directories are supported.
    """
    root = Path(output_dir).resolve()
    if not root.is_dir():
        return {}
    language = remember_language(root, language)
    planned = []
    for source in root.iterdir():
        if source.is_symlink():
            continue
        if source.is_file():
            group = result_subfolder(source.name, language)
            if group is None:
                continue
            destination = root / group / source.name
        elif source.is_dir() and (source.name.startswith('final_fasthenry_')
                                  or source.name in ('target_fields', 'debug')):
            if not any(source.iterdir()):
                source.rmdir()
                continue
            destination = root / name('diagnostics', language) / source.name
            number = 2
            while destination.exists():
                destination = root / name('diagnostics', language) / f'{source.name}({number})'
                number += 1
        else:
            continue
        assert source.resolve().is_relative_to(root)
        assert destination.resolve().is_relative_to(root)
        if destination.exists() and not replace:
            raise FileExistsError(f'Result already exists; refusing to overwrite: {destination}')
        planned.append((source, destination))
    moves = {str(source): str(destination) for source, destination in planned}
    for source, destination in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_file():
            source.replace(destination)
        else:
            shutil.move(str(source), str(destination))
    # JSON files contain filenames/parameters plus a few absolute artifact paths.
    for group in dict.fromkeys(item for key in ('coil', 'leads', 'diagnostics') for item in variants(key)):
        for filename in (root / group).rglob('*.json'):
            try:
                previous = json.loads(filename.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            updated = relocate_paths(previous, moves)
            if updated != previous:
                filename.write_text(json.dumps(updated, indent=2, ensure_ascii=False,
                                                allow_nan=False) + '\n', encoding='utf-8')
    return moves


def write_result_summary(output_dir, *, stem='', error=None, language='en') -> str:
    """Write the final summary in the run's saved output language."""
    root = Path(output_dir).resolve()
    language = language_for(root, language)
    def text(english, spanish):
        return spanish if language == 'es' else english
    if not stem:
        marker = root / '.active_project_stem'
        stem = marker.read_text(encoding='utf-8').strip() if marker.is_file() else ''
    leads = locate(root, 'leads')
    matches = list(leads.glob(f'{stem}_wire_0_with_leads*_final_metrics.json')) if stem else []
    metrics_path = max(matches, key=lambda p: p.stat().st_mtime) if matches else None
    lines = [text('DESIGN RESULT', 'RESULTADO DEL DISEÑO'),
             text('Design: ', 'Diseño: ') + (stem or root.name), '']
    if error:
        lines.extend([text('Incomplete run: ', 'Ejecución incompleta: ') + str(error), ''])
    geometry_path = locate(root, 'diagnostics') / (stem + '_geometry.json')
    if geometry_path.is_file():
        geometry = json.loads(geometry_path.read_text(encoding='utf-8'))
        adjustments = [part.get('max_displacement_mm', 0.) for part in geometry.get('parts', [])]
        lines.extend([
            text('Winding geometry: ', 'Geometría del bobinado: ') + geometry['status'],
            text('Maximum automatic adjustment: ', 'Ajuste automático máximo: ') + f"{max(adjustments, default=0.):.6g} mm",
            text('Winding check: ', 'Comprobación del bobinado: ') + str(geometry_path.relative_to(root)), '',
        ])
    if metrics_path:
        result = json.loads(metrics_path.read_text(encoding='utf-8'))
        fh = result['fasthenry']
        lines.extend([
            text('Final conductor: retained winding and both terminal leads.', 'Conductor final: bobinado retenido y ambos terminales.'),
            text('Gradient: ', 'Gradiente: ') + f"G{result['gradient_axis'].upper()} | B0: {result['b0_direction'].upper()}",
            text('Slope: ', 'Pendiente: ') + f"{result['slope_mT_per_m_per_A']:.7g} mT/(m·A)",
            text('Length: ', 'Longitud: ') + f"{result['wire_length_m']:.7g} m",
            text('Analytical resistance: ', 'Resistencia analítica: ') + f"{result['resistance_ohm_analytic']:.7g} Ω",
            f"FastHenry: {fh['status']}",
        ])
        if fh['status'] == 'success':
            lines.extend([text('FastHenry resistance: ', 'Resistencia FastHenry: ') + f"{fh['resistance_ohm']:.7g} Ω",
                          text('FastHenry inductance: ', 'Inductancia FastHenry: ') + f"{fh['inductance_H'] * 1e6:.7g} µH"])
        elif fh.get('reason'):
            lines.append(text('Reason: ', 'Motivo: ') + fh['reason'])
        lines.extend([text('External supply and return wiring are not included.', 'Los cables externos de alimentación y retorno no están incluidos.'),
                      text('Full metrics: ', 'Métricas completas: ') + str(metrics_path.relative_to(root)), ''])
    elif list(locate(root, 'coil').glob('*_wire_*.stl')):
        lines.extend([text('Only preliminary CoilGen winding results are available.', 'Solo hay resultados del bobinado de CoilGen.'),
                      text('Final-conductor FastHenry is evaluated after lead creation.', 'FastHenry del conductor final se calcula después de generar los leads.'), ''])
    elif list(locate(root, 'mold').glob('*.stl')):
        lines.extend([text('Mold stage complete. This stage does not evaluate FastHenry.', 'Etapa de molde completada. Esta etapa no calcula FastHenry.'), ''])
    else:
        lines.extend([text('No final metrics available.', 'No hay métricas finales disponibles.'), ''])
    lines.extend([text('FILES', 'ARCHIVOS')])
    descriptions = {
        'mold': ('Manufacturing mold STL(s).', 'STL del molde para fabricación.'),
        'leads': ('Final conductor, terminal parts, field and final metrics.', 'Conductor final, terminales, campo y métricas finales.'),
        'plots': ('Final plots; CoilGen/ keeps pre-lead plots.', 'Gráficos finales; CoilGen/ conserva los anteriores a los leads.'),
        'coil': ('Original wire, configuration and reuse references.', 'Bobinado original, parámetros y referencias para reutilización.'),
        'diagnostics': ('Solver inputs and diagnostic evidence.', 'Entradas de cálculo y evidencia del solver.'),
    }
    for key, description in descriptions.items():
        lines.append(name(key, language) + '/: ' + text(*description))
    lines.extend(['', text('Coil metrics are preliminary. Use this summary and the final Leads JSON for final R/L.',
                          'Las métricas de bobina son preliminares. Use este resumen y el JSON final de Leads para R/L finales.')])
    (root / name('summary', language)).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return str(metrics_path) if metrics_path else ''
