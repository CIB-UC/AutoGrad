"""Localized output names and discovery of both current and historical layouts."""

from __future__ import annotations

import json
from pathlib import Path

NAMES = {
    'results': ('results', 'resultados'),
    'coil': ('Coil', 'Bobina'),
    'mold': ('Mold', 'Molde'),
    'leads': ('Leads', 'Leads'),
    'plots': ('Plots', 'Graficos'),
    'diagnostics': ('Diagnostics', 'Diagnostico'),
    'assembly': ('Assembly', 'Conjunto'),
    'summary': ('Summary.txt', 'Resumen.txt'),
    'batch_summary': ('Batch_summary.txt', 'Resumen_lote.txt'),
    'batch_manifest': ('batch.json', 'lote.json'),
    'scene': ('Gradients.glb', 'Gradientes.glb'),
    'keys': ('keys.json', 'encajes.json'),
    'axis': ('Axis', 'Eje'),
    'batch': ('Batch', 'Lote'),
    'sweep': ('tikhonov_sweep', 'barrido_tikhonov'),
}
LAYOUT_FILE = '.output_layout.json'


def name(key: str, language: str = 'en') -> str:
    if language not in ('en', 'es'):
        raise ValueError(f'Unsupported output language: {language!r}')
    return NAMES[key][language == 'es']


def variants(key: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(NAMES[key]))


def locate(root, key: str) -> Path:
    """Find an existing English/Spanish artifact, defaulting to English."""
    root = Path(root)
    return next((root / item for item in variants(key) if (root / item).exists()),
                root / name(key))


def language_for(root, default: str = 'en') -> str:
    """A saved run keeps its original layout when reopened in another language."""
    name('results', default)
    path = Path(root) / LAYOUT_FILE
    if path.is_file():
        language = json.loads(path.read_text(encoding='utf-8'))['language']
        name('results', language)
        return language
    for key in ('coil', 'mold', 'plots', 'diagnostics'):
        if (Path(root) / name(key, 'es')).is_dir():
            return 'es'
        if (Path(root) / name(key, 'en')).is_dir():
            return 'en'
    return default


def remember_language(root, language: str) -> str:
    language = language_for(root, language)
    path = Path(root) / LAYOUT_FILE
    if not path.exists():
        path.write_text(json.dumps({'version': 1, 'language': language}) + '\n',
                        encoding='utf-8')
    return language


def prepare_run_directory(cfg) -> None:
    """A new design in another language gets its own results subdirectory.

    Existing results are never renamed. Reuse-only stages keep their saved layout.
    Selection is side-effect free until the pipeline creates its output directory.
    """
    if not cfg.output_dir or not cfg.control.run_gradient:
        return
    root = Path(cfg.output_dir)
    if language_for(root, cfg.output_language) == cfg.output_language:
        return
    base = root / name('results', cfg.output_language)
    candidate = base
    number = 2
    while candidate.exists():
        candidate = base.with_name(base.name + f'({number})')
        number += 1
    cfg.output_dir = str(candidate)
