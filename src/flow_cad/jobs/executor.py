"""Small priority executor: interactive work overtakes queued background work."""
from concurrent.futures import Future
from queue import PriorityQueue
import itertools
import threading


class PriorityExecutor:
    def __init__(self, max_workers):
        self._queue = PriorityQueue()
        self._sequence = itertools.count()
        self._lock = threading.Lock()
        self._closed = False
        self._threads = [threading.Thread(target=self._run, name=f'flow-cad-job-{i}', daemon=True)
                         for i in range(max_workers)]
        for thread in self._threads:
            thread.start()

    def submit(self, function, *args, priority=10):
        with self._lock:
            if self._closed:
                raise RuntimeError('executor is closed')
            future = Future()
            self._queue.put((priority, next(self._sequence), (future, function, args)))
            return future

    def _run(self):
        while True:
            _, _, task = self._queue.get()
            if task is None:
                return
            future, function, args = task
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(function(*args))
                except BaseException as exc:
                    future.set_exception(exc)

    def shutdown(self, *, wait=True, cancel_futures=False):
        with self._lock:
            if not self._closed:
                self._closed = True
                if cancel_futures:
                    while not self._queue.empty():
                        _, _, task = self._queue.get_nowait()
                        if task is not None:
                            task[0].cancel()
                for _ in self._threads:
                    self._queue.put((float('inf'), next(self._sequence), None))
        if wait:
            for thread in self._threads:
                thread.join()
