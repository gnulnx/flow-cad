"""Persistent, cancellable CAD processes with a shared per-project resource budget.

Only paths, build plans and plain results cross the pipe. Native shapes stay in
one process. A cancelled or crashed process is discarded, never returned warm.
"""
from __future__ import annotations

import fcntl
import hashlib
import importlib.abc
import importlib.machinery
import sys
import multiprocessing
import os
import threading
import time
from pathlib import Path

from flow_cad.config import FlowCadConfig


class CadWorkerError(RuntimeError):
    pass


def source_revision(root: Path, package: str) -> str:
    digest = hashlib.sha256()
    source = root.joinpath(*package.split('.'))
    paths = sorted(p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    manifest = root / 'flowcad.project.yaml'
    for path in [manifest, *paths]:
        if not path.exists():
            continue
        stat = path.stat()
        digest.update(str(path.relative_to(root)).encode())
        if path.suffix in {'.py', '.json', '.yaml', '.toml'}:
            digest.update(path.read_bytes())
        else:
            digest.update(f'{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}'.encode())
    return digest.hexdigest()


class _Worker:
    def __init__(self):
        self.process = None
        self.pipe = None
        self.revision = None
        self.tasks = 0
        self.busy = False
        self.lock_file = None

    def stop(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.kill(); self.process.join(timeout=1)
            self.process.close()
        if self.pipe is not None:
            self.pipe.close()
        self.process = self.pipe = None
        self.revision = None
        self.tasks = 0


class CadWorkerPool:
    def __init__(self, root: Path, config: FlowCadConfig):
        self.root = root.resolve()
        self.config = config
        self._workers = [_Worker() for _ in range(config.cad.workers)]
        self._condition = threading.Condition()
        self._waiting = []
        self._sequence = 0
        self._closed = False
        self._lock_dir = self.root / '.flow/worker-slots'
        self._lock_dir.mkdir(parents=True, exist_ok=True)

    def run(self, operation, arguments, context, *, revision=None, priority=10):
        with self._condition:
            ticket = (priority, self._sequence)
            self._sequence += 1
            self._waiting.append(ticket)
        worker = None
        try:
            while worker is None:
                context.checkpoint()
                with self._condition:
                    if self._closed:
                        raise CadWorkerError('CAD worker pool is closed')
                    if ticket == min(self._waiting):
                        for index, candidate in enumerate(self._workers):
                            if candidate.busy:
                                continue
                            lock_file = (self._lock_dir / str(index)).open('a+b')
                            try:
                                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            except BlockingIOError:
                                lock_file.close(); continue
                            candidate.busy = True
                            candidate.lock_file = lock_file
                            worker = candidate
                            self._waiting.remove(ticket)
                            break
                    if worker is None:
                        self._condition.wait(.05)
            settings = self.config.cad
            if (worker.process is not None and (not worker.process.is_alive()
                    or worker.tasks >= settings.recycle_after_tasks
                    or (revision is not None and worker.revision not in (None, revision)))):
                worker.stop()
            if worker.process is None:
                parent, child = multiprocessing.get_context('spawn').Pipe()
                index = self._workers.index(worker)
                process = multiprocessing.get_context('spawn').Process(
                    target=_serve, args=(child, self.root, settings, index), daemon=True,
                    name=f'flow-cad-worker-{index}')
                process.start()
                child.close()
                worker.pipe, worker.process = parent, process
            if revision is not None:
                worker.revision = revision
            worker.pipe.send((operation, arguments))
            started = time.monotonic()
            while True:
                context.checkpoint()
                if time.monotonic() - started > settings.timeout_seconds:
                    raise CadWorkerError(f'CAD worker exceeded {settings.timeout_seconds}s time budget')
                rss = _rss_mb(worker.process.pid)
                if rss > settings.memory_mb:
                    raise CadWorkerError(f'CAD worker exceeded {settings.memory_mb} MiB memory budget ({rss:.0f} MiB)')
                if worker.pipe.poll(.05):
                    try:
                        kind, payload = worker.pipe.recv()
                    except EOFError as exc:
                        raise CadWorkerError('CAD worker exited without a result') from exc
                    if kind == 'report':
                        context.report(*payload)
                    elif kind == 'result':
                        worker.tasks += 1
                        return payload
                    else:
                        raise CadWorkerError(payload)
                elif not worker.process.is_alive():
                    raise CadWorkerError(f'CAD worker exited with status {worker.process.exitcode}')
        except BaseException:
            if worker is not None:
                worker.stop()
            raise
        finally:
            with self._condition:
                if ticket in self._waiting:
                    self._waiting.remove(ticket)
                if worker is not None:
                    fcntl.flock(worker.lock_file.fileno(), fcntl.LOCK_UN)
                    worker.lock_file.close()
                    worker.lock_file = None
                    worker.busy = False
                    if self._closed:
                        worker.stop()
                self._condition.notify_all()

    def close(self):
        with self._condition:
            self._closed = True
            for worker in self._workers:
                if not worker.busy:
                    worker.stop()
            self._condition.notify_all()


def _rss_mb(pid):
    try:
        fields = Path(f'/proc/{pid}/statm').read_text().split()
        return int(fields[1]) * os.sysconf('SC_PAGE_SIZE') / 1024**2
    except (OSError, IndexError):
        return 0


class _PipeContext:
    def __init__(self, pipe):
        self.pipe = pipe

    def checkpoint(self):
        # Parent checkpoints can terminate native calls, not just Python loops.
        pass

    def report(self, phase, progress, message=None):
        self.pipe.send(('report', (phase, progress, message)))


class _FreshSourceLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        # Timestamp-based pyc files can otherwise survive a same-second edit.
        return self.source_to_code(self.get_data(self.path), self.path)


class _ProjectSourceFinder(importlib.abc.MetaPathFinder):
    def __init__(self, root):
        self.root = root

    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec and spec.origin and spec.origin.endswith('.py'):
            origin = Path(spec.origin).resolve()
            if origin.is_relative_to(self.root):
                spec.loader = _FreshSourceLoader(fullname, spec.origin)
                return spec
        return None


def _serve(pipe, root, settings, index):
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[name] = str(settings.native_threads)
    if hasattr(os, 'sched_getaffinity'):
        cores = sorted(os.sched_getaffinity(0))
        width = min(settings.native_threads, len(cores))
        chosen = [cores[-1 - ((index * width + offset) % len(cores))] for offset in range(width)]
        os.sched_setaffinity(0, chosen)
    os.chdir(root)
    sys.meta_path.insert(0, _ProjectSourceFinder(root))
    # Bound address space too, allowing virtual reservations above the RSS limit.
    import resource
    ceiling = max(8 * 1024**3, settings.memory_mb * 4 * 1024**2)
    resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
    context = _PipeContext(pipe)
    while True:
        try:
            operation, arguments = pipe.recv()
        except EOFError:
            return
        try:
            if operation == 'scene':
                from flow_cad.viewer.scene_export import export_scene
                result = export_scene(*arguments)
            elif operation == 'features':
                from flow_cad.measurement.extractor import extract_step_features
                path, part_uuid, revision = arguments
                result = extract_step_features(path, part_uuid=part_uuid, artifact_revision=revision)
            elif operation == 'prepare_part':
                from flow_cad.build.worker import prepare_scoped_part_build
                result = prepare_scoped_part_build(*arguments, context=context)
            else:
                raise ValueError(f'Unknown CAD operation: {operation}')
            pipe.send(('result', result))
        except BaseException as exc:
            pipe.send(('error', f'{type(exc).__name__}: {exc}'))
            return
