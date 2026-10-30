"""Importable GUI job entry point. No Tk objects cross the process boundary."""

from __future__ import annotations

import io
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


JOB_STATUS_FILENAME = '.job_status.json'
JOB_KINDS = ('pipeline', 'batch', 'standalone', 'sweep')


def result_job_status(kind, result):
    partial = ((kind == 'batch' and not getattr(result, 'completed', True))
               or getattr(result, 'needs_revision', False)
               or getattr(result, 'discarded', False)
               or (kind == 'sweep' and getattr(result, 'best_error', None) is None))
    return 'partial' if partial else 'completed'


def job_output_dir(kind, cfg, extra=None):
    extra = extra or {}
    if kind == 'sweep':
        base = extra.get('output_base_dir') or getattr(cfg, 'output_dir', '')
        from halbach_coils.coilgen.output_layout import name
        return os.path.abspath(os.path.join(base, f"{name('axis', getattr(cfg, 'output_language', 'en'))}_{cfg.axis_label}")) if base else ''
    output_dir = getattr(cfg, 'output_dir', '')
    return os.path.abspath(output_dir) if output_dir else ''


def write_job_status(output_dir, status, *, kind, pid=None, error=None):
    """Persist a tiny atomic marker; cancelled output remains explicitly partial."""
    if not output_dir:
        return
    os.makedirs(output_dir, exist_ok=True)
    record = {
        'status': status, 'job_kind': kind, 'pid': pid,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'partial': status != 'completed',
    }
    if error:
        record['error'] = str(error)
    path = os.path.join(output_dir, JOB_STATUS_FILENAME)
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    os.replace(temporary, path)
    if kind == 'batch' and status in ('cancelled', 'error'):
        _update_interrupted_batch(output_dir, status, error)


def _update_interrupted_batch(output_dir, status, error):
    """The parent reports cancellation after the worker can no longer do so."""
    root = Path(output_dir)
    from halbach_coils.coilgen.output_layout import locate
    manifest = locate(root, 'batch_manifest')
    try:
        document = json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return
    if document.get('status') not in ('running', 'assembly'):
        return
    final_status = 'cancelled' if status == 'cancelled' else 'failed'
    document['status'] = final_status
    if error:
        document['error'] = str(error)
    for layer in document.get('layers', ()):
        if layer.get('status') == 'running':
            layer['status'] = final_status
    from halbach_coils.coilgen.batch import _write_report
    _write_report(root, document)


class _ProcessLog(io.TextIOBase):
    def __init__(self, events):
        self.events = events
        self.pending = ''

    def write(self, text):
        if not text:
            return 0
        self.pending += text
        while '\n' in self.pending or len(self.pending) >= 2048:
            newline = self.pending.find('\n')
            size = min(newline + 1 if newline >= 0 else 2048, 2048)
            line, self.pending = self.pending[:size], self.pending[size:]
            self.events.put(('log', line))
        return len(text)

    def flush(self):
        if self.pending:
            self.events.put(('log', self.pending))
            self.pending = ''


def dispatch_job(kind, cfg, extra, *, ask_user, on_progress):
    """Return small results only: paths/reports/rows, never a solved field mesh."""
    if kind == 'pipeline':
        from halbach_coils.run_pipeline import run_pipeline
        return run_pipeline(cfg, ask_user=ask_user,
                            question_language=extra.get('question_language', 'en'))
    if kind == 'batch':
        from halbach_coils.coilgen.batch import run_batch
        from halbach_coils.coilgen.assembly import finalize_batch
        return run_batch(cfg, ask_user=ask_user, on_progress=on_progress,
                         question_language=extra.get('question_language', 'en'),
                         finalize=finalize_batch)
    if kind == 'standalone':
        from halbach_coils.coilgen.outputs import organize_outputs, relocate_paths, write_result_summary
        action = extra.get('action', 'wire')
        if action == 'wire':
            from halbach_coils.coilgen.gradient import run_gradient
            _solution, metrics, overlap = run_gradient(cfg, output_dir=cfg.output_dir)
            moves = organize_outputs(cfg.output_dir, language=cfg.output_language)
            write_result_summary(cfg.output_dir, language=cfg.output_language)
            return relocate_paths(metrics.get('field_plots'), moves), overlap
        input_stl = extra.get('input_stl', '')
        if not input_stl or not os.path.isfile(input_stl):
            raise FileNotFoundError(f'Input STL does not exist: {input_stl}')
        if action == 'leads':
            from halbach_coils.coilgen.leads import run_leads
            from halbach_coils.coilgen.design_state import validate_design_state
            from halbach_coils.coilgen.final_field import evaluate_final_conductor
            validate_design_state(input_stl, cfg)
            paths = run_leads(cfg, input_stl=input_stl)
            final = evaluate_final_conductor(cfg, input_stl, paths[0], cfg.output_dir)
            moves = organize_outputs(cfg.output_dir, language=cfg.output_language)
            stem = os.path.basename(input_stl).rsplit('_wire_0', 1)[0]
            write_result_summary(cfg.output_dir, stem=stem, language=cfg.output_language)
            return relocate_paths({'paths': paths, 'field_plots': final['field_plots'],
                                   'metrics_path': final['metrics_path']}, moves), None
        if action == 'shell':
            from halbach_coils.coilgen.shell import run_shell
            _output, paths = run_shell(cfg, wire_with_leads_stl=input_stl,
                                       output_dir=cfg.output_dir)
            moves = organize_outputs(cfg.output_dir, language=cfg.output_language)
            write_result_summary(cfg.output_dir, language=cfg.output_language)
            return relocate_paths(paths, moves), None
        raise ValueError(f'Unknown standalone action: {action}')
    if kind == 'sweep':
        from halbach_coils.coilgen.sweep import run_tikhonov_sweep
        sweep_options = {key: value for key, value in extra.items()
                         if key != 'question_language'}
        return run_tikhonov_sweep(cfg, on_progress=on_progress, **sweep_options)
    if kind == '_callable':
        kwargs = dict(extra.get('kwargs') or {})
        if extra.get('ask_user_enabled'):
            kwargs.setdefault('ask_user', ask_user)
        return extra['target'](*extra.get('args', ()), **kwargs)
    raise ValueError(f'Unknown GUI job: {kind}')


def execute_job(kind, cfg, extra, events, answers, start_gate, output_dir):
    """Spawn target: process-local cwd/stdout and queued user decisions."""
    if os.name != 'nt':
        os.setsid()
    start_gate.wait()
    redirect = _ProcessLog(events)
    sys.stdout = sys.stderr = redirect

    def ask_user(question):
        redirect.flush()
        events.put(('question', question))
        return bool(answers.get())

    def on_progress(phase, tikhonov, event, row=None):
        events.put(('progress', phase, tikhonov, event, row))

    try:
        write_job_status(output_dir, 'running', kind=kind, pid=os.getpid())
        result = dispatch_job(kind, cfg, extra, ask_user=ask_user,
                              on_progress=on_progress)
        write_job_status(output_dir, result_job_status(kind, result), kind=kind, pid=os.getpid())
        redirect.flush()
        events.put(('done', result))
    except BaseException as exc:
        detail = f'{type(exc).__name__}: {exc}'
        try:
            write_job_status(output_dir, 'error', kind=kind, pid=os.getpid(), error=detail)
        except OSError:
            pass
        redirect.flush()
        events.put(('error', detail, traceback.format_exc()))
