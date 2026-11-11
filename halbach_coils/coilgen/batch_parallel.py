"""Isolated per-gradient processes and coordinator-owned user interaction."""

from __future__ import annotations

import io
import logging
import multiprocessing
import os
import queue
import subprocess
import sys
import traceback

from .process_control import WindowsJob


class _LayerLog(io.TextIOBase):
    def __init__(self, events, index):
        self.events, self.index = events, index
        self.pending = ''

    def write(self, text):
        self.pending += text
        while '\n' in self.pending or len(self.pending) >= 2048:
            newline = self.pending.find('\n')
            size = min(newline + 1 if newline >= 0 else 2048, 2048)
            line, self.pending = self.pending[:size], self.pending[size:]
            self.events.put(('log', self.index, line))
        return len(text)

    def flush(self):
        if self.pending:
            self.events.put(('log', self.index, self.pending))
            self.pending = ''


def _run_layer(index, cfg, events, answers, stop, gate, language, interactive,
               electrical_lock):
    # Wait until the coordinator has contained this process and descendants.
    gate.wait()
    redirect = _LayerLog(events, index)
    sys.stdout = sys.stderr = redirect
    logging.basicConfig(level=logging.INFO, stream=redirect, force=True)

    def ask_user(question):
        redirect.flush()
        events.put(('question', index, question))
        while not stop.is_set():
            try:
                return bool(answers.get(timeout=.1))
            except queue.Empty:
                pass
        return False

    try:
        from halbach_coils.run_pipeline import run_pipeline
        result = run_pipeline(cfg, should_stop=stop.is_set,
                              ask_user=ask_user if interactive else None,
                              question_language=language,
                              electrical_lock=electrical_lock)
        redirect.flush()
        events.put(('result', index, result))
    except BaseException as exc:
        redirect.flush()
        events.put(('log', index, traceback.format_exc()))
        events.put(('error', index, f'{type(exc).__name__}: {exc}'))


def _stop_worker(process, job):
    if job is not None:
        job.close()
    elif process.is_alive():
        if os.name == 'nt':
            try:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               capture_output=True, timeout=4,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            # Workers share the GUI job's process group, so its Stop action
            # also terminates descendants on POSIX.
            process.terminate()
    if process.is_alive():
        process.kill()
    process.join(timeout=1)


def iter_layer_runs(configs, *, parallel, should_stop, ask_user,
                    question_language, on_start):
    """Yield (layer index, result, error), forwarding logs/questions centrally.

    The caller must close this iterator on early return. No Tk objects or
    parent callbacks are passed to spawned processes.
    """
    if not parallel:
        from halbach_coils.run_pipeline import run_pipeline
        for index, cfg in enumerate(configs):
            if should_stop and should_stop():
                return
            on_start(index, cfg)
            try:
                result = run_pipeline(cfg, should_stop=should_stop, ask_user=ask_user,
                                      question_language=question_language)
            except Exception as exc:
                yield index, None, exc
                return
            yield index, result, None
        return

    context = multiprocessing.get_context('spawn')
    # Synchronous manager queues avoid feeder-thread deadlocks during shutdown.
    manager = context.Manager()
    workers, jobs, answers, gates = {}, {}, {}, {}
    stop = context.Event()
    try:
        events = manager.Queue()
        # FastHenry's Windows COM server is shared system-wide. Only that
        # solver stage needs serialization; the gradient pipelines overlap.
        electrical_lock = context.Lock() if os.name == 'nt' else None
        for index, cfg in enumerate(configs):
            if should_stop and should_stop():
                return
            try:
                answers[index] = manager.Queue()
                gate = context.Event()
                gates[index] = gate  # retain spawn handles until the child exits
                process = context.Process(
                    target=_run_layer,
                    args=(index, cfg, events, answers[index], stop, gate,
                          question_language, ask_user is not None, electrical_lock),
                    name=f'AutoGrad-batch-G{cfg.gradient_axis}',
                )
                process.start()
                workers[index] = process
                jobs[index] = None
                if os.name == 'nt':
                    try:
                        jobs[index] = WindowsJob(process.pid)
                    except OSError:
                        pass  # taskkill /T fallback; GUI containment also applies
                on_start(index, cfg)
                gate.set()
            except Exception as exc:
                yield index, None, exc
                return

        pending = set(workers)
        while pending:
            if should_stop and should_stop():
                return
            try:
                kind, index, payload = events.get(timeout=.1)
            except queue.Empty:
                # A worker's terminal event is queued synchronously before it
                # exits. An empty queue plus an exited worker means a crash.
                exited = [i for i in pending if workers[i].exitcode is not None]
                if not exited:
                    continue
                # A result may have arrived between the timeout and checking
                # exit codes. Drain that event before declaring any crash.
                try:
                    kind, index, payload = events.get_nowait()
                except queue.Empty:
                    for index in exited:
                        pending.remove(index)
                        yield index, None, RuntimeError(
                            f'{configs[index].axis_label} process exited without a result '
                            f'(code {workers[index].exitcode}).')
                    continue
            if kind == 'log':
                print(f'[{configs[index].axis_label}] {payload}', end='', flush=True)
            elif kind == 'question':
                # Only this coordinator calls the GUI's existing question pipe.
                answer = bool(ask_user(payload)) if ask_user is not None else True
                answers[index].put(answer)
            elif kind in ('result', 'error'):
                pending.remove(index)
                if kind == 'error':
                    yield index, None, RuntimeError(payload)
                else:
                    yield index, payload, None
    finally:
        stop.set()
        for index, process in workers.items():
            _stop_worker(process, jobs.get(index))
        manager.shutdown()
