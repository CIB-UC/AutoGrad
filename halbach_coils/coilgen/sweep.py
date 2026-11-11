"""
Tikhonov regularization sweep.

Runs pyCoilGen headless across a coarse (log-spaced) Tikhonov grid, then an
optional fine pass around the best coarse point. Reports both the realized
slope [mT/(m.A)] and the mean relative layout-vs-target error -- the latter is
the figure of merit the Gz design was failing on, so the sweep surfaces it
explicitly instead of ranking by slope alone.

Refactored from the former ``obsolete/barrido_tikhonov_v2.py`` and
``obsolete/gradiente_belen_santi_func.py`` into a function that reuses
:func:`coilgen.gradient.run_gradient` (including physical winding checks) and
:func:`coilgen.metrics.compute_metrics`.

Outputs: per-axis ``Resumen_Completo_Eje_<AXIS>.csv`` and ``.txt`` with the
best-by-slope and best-by-error (lowest mean rel err) points highlighted.
"""

from __future__ import annotations

import copy
import csv
import io
import logging
import multiprocessing
import os
import queue
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

from .config import Config
from .output_layout import name
from .paths import output_base
from .gradient import run_gradient
from .presets import save_config_preset


SWEEP_CONFIG_FILENAME = 'Sweep_Config.json'
# ProcessPoolExecutor supports at most 61 workers on Windows.
MAX_SWEEP_PROCESSES = os.cpu_count() or 1
if os.name == 'nt':
    MAX_SWEEP_PROCESSES = min(MAX_SWEEP_PROCESSES, 61)


@dataclass
class SweepResult:
    axis: str
    rows: List[dict] = field(default_factory=list)
    csv_path: str = ''
    txt_path: str = ''
    config_preset_path: str = ''
    best_slope: Optional[dict] = None
    best_error: Optional[dict] = None


# Per-axis default sweep ranges. Gz needs a much wider high-Tikhonov regime
# (its best point currently has a large target-field error), so the default
# upper bound is extended to 1e6 for Z. The GUI exposes these as editable
# starting points.
DEFAULT_RANGES = {
    'x': (1.0, 100_000.0, 10),
    'y': (1.0, 100_000.0, 10),
    'z': (1.0, 1_000_000.0, 12),
}


def validate_sweep_parameters(tk_min: float, tk_max: float,
                              n_coarse: int, n_fine: int = 7) -> None:
    """Reject sweep ranges that cannot produce a meaningful finite grid."""
    if not np.isfinite(tk_min) or tk_min <= 0:
        raise ValueError('Tikhonov min must be a positive finite number.')
    if not np.isfinite(tk_max) or tk_max < tk_min:
        raise ValueError('Tikhonov max must be finite and >= Tikhonov min.')
    if n_coarse < 2:
        raise ValueError('Coarse points must be at least 2.')
    if n_fine < 1:
        raise ValueError('Fine points must be at least 1.')


def _row_from_metrics(tk: float, phase: str, metrics: dict) -> dict:
    return {
        'Fase': phase,
        'Tikhonov': tk,
        'Pendiente_mT_per_m_per_A': float(metrics.get('slope_mTmA', float('nan'))),
        'Error_Medio_pct': (
            float(metrics['mean_rel_err_layout_pct'])
            if metrics.get('mean_rel_err_layout_pct') is not None
            else float('nan')
        ),
        'RMSE_per_range_mT_per_m_per_A': float(
            metrics.get('rmse_gradient_mTmA', float('nan'))
        ),
        'Wire_length_m': float(
            metrics.get('total_wire_length_computed', float('nan'))
        ),
    }


def row_is_feasible(row: dict) -> bool:
    """Unknown/legacy geometry is never a validated recommendation."""
    return (row.get('Geometry_status') == 'valid'
            and np.isfinite(row.get('Pendiente_mT_per_m_per_A', float('nan')))
            and np.isfinite(row.get('Error_Medio_pct', float('nan'))))


def _fmt_val(v, fmt='.6g'):
    if v is None:
        return 'n/a'
    try:
        if isinstance(v, float) and not np.isfinite(v):
            return 'n/a'
        return format(v, fmt)
    except (TypeError, ValueError):
        return str(v)


CSV_ENGLISH_NAMES = {'Fase': 'Phase', 'Pendiente_mT_per_m_per_A': 'Slope_mT_per_m_per_A',
                     'Error_Medio_pct': 'Mean_error_pct'}


def normalize_csv_row(row: dict) -> dict:
    """Read English headers and historical identifiers without changing saved data."""
    aliases = {english: legacy for legacy, english in CSV_ENGLISH_NAMES.items()}
    return {aliases.get(key, key): value for key, value in row.items()}


def _write_csv(path: str, rows: List[dict], language='en') -> None:
    if not rows:
        return
    if language == 'en':
        rows = [{CSV_ENGLISH_NAMES.get(key, key): value for key, value in row.items()}
                for row in rows]
    fields = list(rows[0].keys())
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def _write_txt(path: str, cfg: Config, rows: List[dict],
               best_slope: dict | None, best_error: dict | None) -> None:
    if cfg.output_language == 'en':
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(f"Tikhonov sweep summary — {cfg.axis_label}\n")
            fh.write(f"B0={cfg.b0_direction}; component={cfg.field_component_label}; frame=physical_XYZ\n")
            fh.write(f"Outer radius={cfg.cylinder.radius} m; height={cfg.cylinder.height} m; levels={cfg.num_levels}\n")
            fh.write('Winding clearance is checked here; leads and assembly require the full pipeline.\n')
            fh.write('Phase\tTikhonov\tSlope[mT/(m.A)]\tMean error[%]\tRMSE/range\tGeometry\n')
            for row in rows:
                phase = {'Grueso': 'Coarse', 'Fino': 'Fine'}.get(row['Fase'], row['Fase'])
                fh.write(f"{phase}\t{row['Tikhonov']}\t{_fmt_val(row['Pendiente_mT_per_m_per_A'])}\t{_fmt_val(row['Error_Medio_pct'])}\t{_fmt_val(row['RMSE_per_range_mT_per_m_per_A'])}\t{row.get('Geometry_status', 'unchecked')}\n")
            if best_slope is None or best_error is None:
                fh.write('No interference-free winding was found. No design is recommended; all attempts were kept.\n')
            else:
                fh.write(f"Best absolute slope: Tikhonov={best_slope['Tikhonov']}\n")
                fh.write(f"Lowest mean target-field error: Tikhonov={best_error['Tikhonov']}\n")
        return
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(f"Resumen Barrido Tikhonov - EJE {cfg.axis_label}\n")
        fh.write(f"B0={cfg.b0_direction}; componente={cfg.field_component_label}; "
                 "coordenadas=fisicas_XYZ\n")
        fh.write(f"Construccion: radio_externo={cfg.cylinder.radius}m, "
                 f"largo={cfg.cylinder.height}m, niveles={cfg.num_levels}\n")
        fh.write("-" * 70 + "\n")
        fh.write('Validación geométrica del bobinado; terminales y ensamble se comprueban en el pipeline.\n')
        fh.write("Fase\tTikhonov\tPendiente[mT/(m.A)]\tErrorMedio[%]\tRMSE/range\tGeometria\n")
        for r in rows:
            fh.write(f"{r['Fase']}\t{r['Tikhonov']}\t"
                     f"{_fmt_val(r['Pendiente_mT_per_m_per_A'])}\t"
                     f"{_fmt_val(r['Error_Medio_pct'])}\t"
                     f"{_fmt_val(r['RMSE_per_range_mT_per_m_per_A'])}\t"
                     f"{r.get('Geometry_status', 'unchecked')}\n")
        fh.write("-" * 70 + "\n")
        if best_slope is None or best_error is None:
            fh.write('No se encontró un bobinado sin interferencias en este barrido.\n'
                     'No hay un diseño recomendado. Se conservaron todos los intentos.\n')
            return
        fh.write(f"[*] MEJOR PENDIENTE ABSOLUTA:\n"
                 f"    Tikhonov = {best_slope['Tikhonov']} "
                 f"(Fase: {best_slope['Fase']})\n"
                 f"    Pendiente = {_fmt_val(best_slope['Pendiente_mT_per_m_per_A'])} "
                 f"mT/(m.A)\n\n")
        fh.write(f"[*] MENOR ERROR MEDIO vs CAMPO OBJETIVO:\n"
                 f"    Tikhonov = {best_error['Tikhonov']} "
                 f"(Fase: {best_error['Fase']})\n"
                 f"    Error = {_fmt_val(best_error['Error_Medio_pct'])} %\n")


def _run_one(cfg: Config, tk: float, base_dir: str, phase: str,
             on_progress: Optional[Callable] = None) -> dict:
    """Run pyCoilGen for one Tikhonov value; return a sweep row dict."""
    run_cfg = copy.deepcopy(cfg)
    run_cfg.tikhonov_factor = float(tk)
    run_cfg.show_plots = False
    run_cfg.overlap_warn = True
    run_cfg.control.run_gradient = True

    tk_dir = os.path.join(base_dir, f"Tk_{phase}_{tk}")
    os.makedirs(tk_dir, exist_ok=True)
    run_cfg.output_dir = tk_dir

    if on_progress:
        on_progress(phase, tk, 'start')
    try:
        _, metrics, report = run_gradient(run_cfg, output_dir=tk_dir, check_overlap=True)
        row = _row_from_metrics(tk, phase, metrics)
        row.update(Geometry_status=('unchecked' if report is None else
                                    'valid' if report.n_collisions == 0 else 'interference'),
                   Collision_sites=report.n_collisions if report is not None else '',
                   Minimum_separation_mm=(metrics.get('geometry_report') or {}).get('minimum_found_mm'),
                   Geometry_report=metrics.get('geometry_report_path', ''), Error='')
    except Exception as exc:  # keep sweeping on a single failure
        print(f"  [sweep] FAILED tk={tk}: {exc}")
        row = {
            'Fase': phase, 'Tikhonov': tk,
            'Pendiente_mT_per_m_per_A': float('nan'),
            'Error_Medio_pct': float('nan'),
            'RMSE_per_range_mT_per_m_per_A': float('nan'),
            'Wire_length_m': float('nan'),
            'Geometry_status': 'failed', 'Collision_sites': '',
            'Minimum_separation_mm': None, 'Geometry_report': '', 'Error': str(exc),
        }
    if on_progress:
        on_progress(phase, tk, 'done', row)
    return row


class _SweepLog(io.TextIOBase):
    """Forward spawned workers' output to the coordinating sweep process."""

    def __init__(self, messages):
        self.messages = messages

    def write(self, text):
        if text:
            self.messages.put(text)
        return len(text)

    def flush(self):
        pass


def _init_sweep_worker(messages):
    # Spawned processes do not inherit the GUI job's stdout redirection.
    # The coordinator prints these messages into the existing GUI log pipe.
    sys.stdout = sys.stderr = _SweepLog(messages)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, force=True)


def _drain_worker_logs(messages):
    while True:
        try:
            text = messages.get_nowait()
        except queue.Empty:
            return
        print(text, end='', flush=True)


def _run_phase(cfg: Config, tks: list[float], base_dir: str, phase: str,
               processes: int, on_progress: Optional[Callable]) -> List[dict]:
    # Rounding or a constant range can produce duplicate values. Each value
    # must run only once so simultaneous workers never share an output folder.
    tks = list(dict.fromkeys(tks))
    if not tks:
        return []
    if processes == 1:
        rows = []
        for tk in tks:
            print(f"\n  -> [{phase}] Tikhonov = {tk}")
            rows.append(_run_one(cfg, tk, base_dir, phase, on_progress))
        return rows

    context = multiprocessing.get_context('spawn')
    # A manager queue needs no worker-side feeder-thread flush at shutdown.
    # This keeps pool shutdown from waiting on an undrained pipe of log text.
    manager = context.Manager()
    messages = manager.Queue()
    rows = []
    values = iter(tks)
    workers = min(processes, len(tks))
    try:
        with ProcessPoolExecutor(
            max_workers=workers, mp_context=context,
            initializer=_init_sweep_worker, initargs=(messages,),
        ) as executor:
            pending = {}

            def submit_next():
                tk = next(values, None)
                if tk is None:
                    return
                print(f"\n  -> [{phase}] Tikhonov = {tk}")
                pending[executor.submit(_run_one, cfg, tk, base_dir, phase)] = tk
                if on_progress:
                    on_progress(phase, tk, 'start')

            for _ in range(workers):
                submit_next()
            while pending:
                completed, _ = wait(
                    pending, timeout=0.1, return_when=FIRST_COMPLETED)
                _drain_worker_logs(messages)
                for future in completed:
                    tk = pending.pop(future)
                    row = future.result()
                    rows.append(row)
                    if on_progress:
                        on_progress(phase, tk, 'done', row)
                    submit_next()
        _drain_worker_logs(messages)
    finally:
        manager.shutdown()
    # Match sequential ordering so ties select the same coarse/fine optimum.
    rows.sort(key=lambda row: row['Tikhonov'])
    return rows


def run_tikhonov_sweep(
    cfg: Config,
    tk_min: Optional[float] = None,
    tk_max: Optional[float] = None,
    n_coarse: Optional[int] = None,
    fine: Optional[bool] = None,
    n_fine: int = 7,
    output_base_dir: Optional[str] = None,
    on_progress: Optional[Callable] = None,
    processes: Optional[int] = None,
) -> SweepResult:
    """
    Sweep Tikhonov regularization for ``cfg.gradient_axis``.

    Coarse grid is log-spaced from ``tk_min`` to ``tk_max`` (``n_coarse``
    points). If ``fine`` is True, a second linear pass of ``n_fine`` points
    runs between the neighbours of the best coarse point (by max |slope|).
    Defaults come from :data:`DEFAULT_RANGES` (Gz widened to 1e6).

    ``on_progress(phase, tk, event, row=None)`` is called for GUI updates.
    ``processes`` defaults to ``cfg.sweep.processes``; 1 runs sequentially.
    Each phase runs up to that many independent spawned processes. The fine
    pass starts only after every coarse result is available. Progress and log
    messages are forwarded by the coordinator, keeping Tk in its own process.
    """
    axis = cfg.gradient_axis.lower()
    d_min, d_max, d_n = DEFAULT_RANGES.get(axis, (1.0, 100_000.0, 10))
    tk_min = d_min if tk_min is None else tk_min
    tk_max = d_max if tk_max is None else tk_max
    n_coarse = d_n if n_coarse is None else n_coarse
    fine = cfg.sweep.fine if fine is None else fine
    processes = cfg.sweep.processes if processes is None else processes
    validate_sweep_parameters(tk_min, tk_max, n_coarse, n_fine)
    if (isinstance(processes, bool) or not isinstance(processes, int)
            or not 1 <= processes <= MAX_SWEEP_PROCESSES):
        raise ValueError(
            f'Processes must be an integer between 1 and {MAX_SWEEP_PROCESSES}.')
    cfg = copy.deepcopy(cfg)
    cfg.sweep.tk_min, cfg.sweep.tk_max = tk_min, tk_max
    cfg.sweep.n_coarse, cfg.sweep.n_fine = n_coarse, n_fine
    cfg.sweep.fine, cfg.sweep.processes = fine, processes

    if output_base_dir is None:
        output_base_dir = output_base(cfg.output_language, name('sweep', cfg.output_language))
    axis_dir = os.path.abspath(os.path.join(output_base_dir, f"{name('axis', cfg.output_language)}_{cfg.axis_label}"))
    os.makedirs(axis_dir, exist_ok=True)
    config_preset_path = save_config_preset(
        cfg, os.path.join(axis_dir, SWEEP_CONFIG_FILENAME),
        name=f'Sweep {cfg.axis_label}', source='tikhonov_sweep',
    )

    print("\n" + "=" * 60)
    label = 'BARRIDO TIKHONOV' if cfg.output_language == 'es' else 'TIKHONOV SWEEP'
    print(f"  {label} - {cfg.axis_label} (R={cfg.cylinder.radius} m)")
    print("=" * 60)
    label = 'Procesos simultáneos' if cfg.output_language == 'es' else 'Simultaneous processes'
    print(f"  {label}: {processes}")

    # ----- Phase 1: coarse (log-spaced) -----------------------------------
    coarse_tks = np.logspace(np.log10(tk_min), np.log10(tk_max), n_coarse)
    coarse_tks = [round(float(tk), 4) for tk in coarse_tks]
    rows = _run_phase(cfg, coarse_tks, axis_dir,
                      'Grueso' if cfg.output_language == 'es' else 'Coarse', processes, on_progress)

    # ----- Phase 2: fine (linear around best coarse) ----------------------
    finite = [r for r in rows if np.isfinite(r['Pendiente_mT_per_m_per_A'])]
    feasible = [r for r in finite if row_is_feasible(r)]
    if not finite:
        print("  [sweep] no successful coarse runs; skipping fine pass.")
        best_slope = None
    else:
        # Still explore a bounded fine grid when no coarse point fits. Failed
        # geometry can seed exploration, but can never become a recommendation.
        best_slope = max(feasible or finite, key=lambda r: abs(r['Pendiente_mT_per_m_per_A']))
        if fine:
            best_tk = best_slope['Tikhonov']
            # neighbours in the coarse grid
            sorted_coarse = sorted(coarse_tks)
            idx = sorted_coarse.index(best_tk) if best_tk in sorted_coarse else min(
                range(len(sorted_coarse)),
                key=lambda i: abs(sorted_coarse[i] - best_tk),
            )
            tk_prev = sorted_coarse[idx - 1] if idx > 0 else max(tk_min, best_tk / 2)
            tk_next = sorted_coarse[idx + 1] if idx < len(sorted_coarse) - 1 else best_tk * 2
            tk_prev, tk_next = max(tk_min, tk_prev), min(tk_max, tk_next)

            label = 'Mejor grueso / rango fino' if cfg.output_language == 'es' else 'Best coarse / fine range'
            print(f"\n  [*] {label}: {best_tk}; [{tk_prev}, {tk_next}]")
            fine_tks = [round(float(v), 4) for v in
                        np.linspace(tk_prev, tk_next, n_fine)]
            fine_tks = [tk for tk in fine_tks if tk not in coarse_tks]
            rows.extend(_run_phase(
                cfg, fine_tks, axis_dir, 'Fino' if cfg.output_language == 'es' else 'Fine', processes, on_progress))

    # ----- Consolidate ----------------------------------------------------
    rows.sort(key=lambda r: r['Tikhonov'])
    finite_rows = [r for r in rows if row_is_feasible(r)]
    best_error = (
        min(finite_rows, key=lambda r: r['Error_Medio_pct'])
        if finite_rows else None
    )
    best_slope = (max(finite_rows, key=lambda r: abs(r['Pendiente_mT_per_m_per_A']))
                  if finite_rows else None)

    csv_path = os.path.join(axis_dir, f"{'Resumen_Completo_Eje' if cfg.output_language == 'es' else 'Sweep_summary_Axis'}_{cfg.axis_label}.csv")
    txt_path = os.path.join(axis_dir, f"{'Resumen_Completo_Eje' if cfg.output_language == 'es' else 'Sweep_summary_Axis'}_{cfg.axis_label}.txt")
    _write_csv(csv_path, rows, cfg.output_language)
    _write_txt(txt_path, cfg, rows, best_slope, best_error)

    if cfg.output_language == 'es':
        print(f"\n  Resumen guardado en: {axis_dir}")
        if best_slope is not None and best_error is not None:
            print(f"  Mejor pendiente sin interferencias: tk={best_slope['Tikhonov']} "
                  f"({_fmt_val(best_slope['Pendiente_mT_per_m_per_A'])} mT/(m.A))")
            print(f"  Menor error sin interferencias: tk={best_error['Tikhonov']} "
                  f"({_fmt_val(best_error['Error_Medio_pct'])} %)")
        else:
            print('  No se encontró un bobinado sin interferencias; no hay un diseño recomendado.')
    else:
        print(f"\n  Summary saved to: {axis_dir}")
        if best_slope is not None and best_error is not None:
            print(f"  Best feasible slope: tk={best_slope['Tikhonov']}")
            print(f"  Lowest feasible error: tk={best_error['Tikhonov']}")
        else:
            print('  No interference-free winding found; no design is recommended.')

    return SweepResult(
        axis=axis, rows=rows, csv_path=csv_path, txt_path=txt_path,
        config_preset_path=config_preset_path,
        best_slope=best_slope, best_error=best_error,
    )


def main():
    """CLI entry: run a Tikhonov sweep for one axis."""
    import argparse
    parser = argparse.ArgumentParser(description="AutoGrad: Tikhonov regularization sweep.")
    parser.add_argument('--axis', default='z', choices=('x', 'y', 'z'))
    parser.add_argument('--b0', default='+y', choices=('+x', '-x', '+y', '-y', '+z', '-z'),
                        help='Physical B0 direction; use --b0=-y for a negative direction')
    parser.add_argument('--tikhonov-min', type=float, default=None)
    parser.add_argument('--tikhonov-max', type=float, default=None)
    parser.add_argument('--n-coarse', type=int, default=None)
    parser.add_argument('--processes', type=int, default=1,
                        help=f'Simultaneous sweep processes (1-{MAX_SWEEP_PROCESSES})')
    parser.add_argument('--no-fine', action='store_true')
    parser.add_argument('--levels', type=int, default=26)
    parser.add_argument('--radius', type=float, default=None)
    parser.add_argument('--height', type=float, default=0.430)
    args = parser.parse_args()

    cfg = Config(gradient_axis=args.axis, b0_direction=args.b0, num_levels=args.levels,
                 show_plots=False, overlap_warn=False)
    cfg.cylinder.height = args.height
    if args.radius is not None:
        cfg.cylinder.radius = args.radius
    cfg.sweep.fine = not args.no_fine
    run_tikhonov_sweep(
        cfg, tk_min=args.tikhonov_min, tk_max=args.tikhonov_max,
        n_coarse=args.n_coarse, processes=args.processes,
    )


if __name__ == '__main__':
    main()
