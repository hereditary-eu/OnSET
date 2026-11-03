"""Bounded concurrent execution of the endpoint queries of a request: the job pool,
cancellation, and the metering and budget of the queries."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


class SamplingCancelled(Exception):
    """The sampling was cancelled (CancelToken), its partial result is discarded."""


class CancelToken:
    """Cancellation of a running sampling: cancel() drops the pending jobs of its pool and
    stops the events (thread-safe, idempotent)."""

    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[], None]] = []

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self):
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            callback()

    def on_cancel(self, callback: Callable[[], None]):
        """Run ``callback`` on cancel (at once if it is cancelled already)."""
        with self._lock:
            if not self._event.is_set():
                self._callbacks.append(callback)
                return
        callback()

    def check(self):
        if self.cancelled:
            raise SamplingCancelled()


@dataclass(eq=False)
class _Job:
    run: Callable[[], object]
    timeout: float
    callback: Callable[[object], None] | None
    started: float | None = None
    # the callback was called (result, failure or timeout) or is being called
    settled: bool = False


class JobPool:
    """Bounded pool of the endpoint queries of one request, streaming each result.

    Every submitted job's callback is called exactly once, from a worker thread, with the
    job's result, or with None if it raised or ran longer than its timeout (counted from
    its start). Timed-out jobs cannot be interrupted: their thread finishes in the
    background (the endpoint runners have their own HTTP timeout) and its worker is
    replaced, so at most ``parallelism`` jobs that have not timed out run at once and
    waiting jobs never starve behind stuck ones. ``urgent`` jobs (value distributions,
    which further counts wait for) are queued before the others.

    cancel() drops the waiting jobs and suppresses the callbacks of the running ones;
    join()/run_all() return at once then.
    """

    def __init__(self, parallelism: int, name: str = "progressive"):
        self.parallelism = max(1, parallelism)
        self.name = name
        self.cancelled = False
        self._cond = threading.Condition(threading.Lock())
        self._queue: deque[_Job] = deque()
        self._running: set[_Job] = set()
        # workers that are not stuck in a timed-out job
        self._workers = 0
        # submitted jobs whose callback has not returned yet
        self._outstanding = 0
        self._closed = False
        self._watchdog: threading.Thread | None = None

    def submit(self, run: Callable[[], T], timeout: float, callback: Callable[[T | None], None] | None = None, urgent: bool = False):
        self.submit_all([run], timeout, [callback], urgent)

    def submit_all(self, runs: list[Callable[[], T]], timeout: float, callbacks: list, urgent: bool = False):
        jobs = [_Job(run, timeout, callback) for run, callback in zip(runs, callbacks)]
        with self._cond:
            if self.cancelled or self._closed or not jobs:
                return
            if urgent:
                self._queue.extendleft(reversed(jobs))
            else:
                self._queue.extend(jobs)
            self._outstanding += len(jobs)
            self._spawn()
            if self._watchdog is None:
                self._watchdog = threading.Thread(target=self._watch, name=f"{self.name}-watchdog", daemon=True)
                self._watchdog.start()

    def run_all(self, runs: list[Callable[[], T]], timeout: float, urgent: bool = False) -> list[T | None]:
        """Results of ``runs`` (None where one raised or timed out), once all are done;
        the pool's other jobs keep running meanwhile."""
        results: list = [None] * len(runs)
        remaining = [len(runs)]

        def callback(i: int):
            def store(value):
                results[i] = value
                with self._cond:
                    remaining[0] -= 1
                    self._cond.notify_all()

            return store

        self.submit_all(runs, timeout, [callback(i) for i in range(len(runs))], urgent)
        with self._cond:
            while remaining[0] > 0 and not self.cancelled:
                self._cond.wait()
        return results

    def join(self):
        """Wait until every submitted job's callback returned (or the pool is cancelled)."""
        with self._cond:
            while self._outstanding > 0 and not self.cancelled:
                self._cond.wait()

    def cancel(self):
        with self._cond:
            self.cancelled = True
            self._outstanding -= len(self._queue)
            self._queue.clear()
            self._cond.notify_all()

    def close(self):
        """Stop the watchdog (after the request); running jobs finish in the background."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def _spawn(self):
        # under the lock
        missing = min(self.parallelism - self._workers, len(self._queue))
        for _ in range(max(0, missing)):
            self._workers += 1
            threading.Thread(target=self._work, name=self.name, daemon=True).start()

    def _work(self):
        while True:
            with self._cond:
                if not self._queue:
                    self._workers -= 1
                    return
                job = self._queue.popleft()
                job.started = time.monotonic()
                self._running.add(job)
                # the watchdog's next expiry changed
                self._cond.notify_all()
            try:
                value = job.run()
            except Exception as e:
                print(f"Progressive job failed: {e!r}")
                value = None
            with self._cond:
                self._running.discard(job)
                abandoned, job.settled = job.settled, True
            if abandoned:
                # timed out: the watchdog replaced this worker
                return
            self._finish(job, value)

    def _finish(self, job: _Job, value):
        try:
            if job.callback is not None and not self.cancelled:
                job.callback(value)
        except Exception as e:
            print(f"Progressive job callback failed: {e!r}")
        finally:
            with self._cond:
                self._outstanding -= 1
                self._cond.notify_all()

    def _watch(self):
        with self._cond:
            while not self._closed:
                now = time.monotonic()
                expired = [job for job in self._running if now - job.started > job.timeout]
                if expired:
                    for job in expired:
                        self._running.discard(job)
                        job.settled = True
                        self._workers -= 1
                    self._spawn()
                    self._cond.release()
                    try:
                        for job in expired:
                            print(f"Progressive job timed out after {job.timeout:g}s")
                            self._finish(job, None)
                    finally:
                        self._cond.acquire()
                    continue
                expiry = min((job.started + job.timeout for job in self._running), default=None)
                self._cond.wait(None if expiry is None else max(0.01, expiry - now))


def run_bounded(
    jobs: list[Callable[[], T]], parallelism: int, timeout: float
) -> list[T | None]:
    """Results of ``jobs`` run on ``parallelism`` threads; None where a job raised
    or ran longer than ``timeout`` seconds (see JobPool)."""
    if not jobs:
        return []
    pool = JobPool(parallelism)
    try:
        return pool.run_all(jobs, timeout)
    finally:
        pool.close()


class QueryMeter:
    """Counts the calls of the wrapped query runners (thread-safe), in total and, within
    measured(), of the current thread."""

    def __init__(self):
        self.count = 0
        self._lock = threading.Lock()
        self._local = threading.local()

    def wrap(self, run: Callable[[str, float], T]) -> Callable[[str, float], T]:
        def metered(query: str, timeout: float) -> T:
            with self._lock:
                self.count += 1
            if getattr(self._local, "count", None) is not None:
                self._local.count += 1
            return run(query, timeout)

        return metered

    def measured(self, run: Callable[[], T], costs: dict, key) -> Callable[[], T]:
        """``run`` storing the queries it ran (in its thread) as ``costs[key]``."""

        def job() -> T:
            self._local.count = 0
            try:
                return run()
            finally:
                costs[key] = self._local.count
                self._local.count = None

        return job


@dataclass
class QueryBudget:
    """Endpoint queries left of a request: the cap minus the queries spent (run, or
    committed: counts submitted to the pool) and those reserved for modifications that
    are not submitted yet. Spending at submission keeps the budget's decisions
    independent of the order in which the concurrent queries run."""

    limit: int
    spent: int = 0
    reserved: int = 0

    def remaining(self) -> int:
        return self.limit - self.spent - self.reserved
