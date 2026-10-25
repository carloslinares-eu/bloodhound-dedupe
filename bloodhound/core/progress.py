"""Thread-safe progress counters with a smoothed transfer rate and time-remaining estimate."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from bloodhound.core.models import Phase, ProgressSnapshot

_TIMED_PHASES = (Phase.HASHING, Phase.COPYING, Phase.VERIFYING)


class ProgressTracker:
    """Collects progress from worker threads and hands out snapshots to the GUI.

    Workers call :meth:`advance` (or :meth:`add_bytes`) as data is processed;
    the GUI calls :meth:`snapshot` on a timer. The rate is averaged over the
    last ``window`` seconds so the speed and time remaining don't jitter.
    """

    SAMPLE_INTERVAL = 0.25  # seconds between rate samples
    MIN_RATE_SPAN = 0.5  # don't guess a speed from less data than this

    def __init__(self, window: float = 5.0, clock: Callable[[], float] = time.monotonic):
        self._lock = threading.Lock()
        self._clock = clock
        self._window = window
        self._job_start: float | None = None
        self._job_end: float | None = None
        self._reset_phase(Phase.IDLE, 0, 0)

    # -- updates -----------------------------------------------------------

    def start_job(self) -> None:
        with self._lock:
            self._job_start = self._clock()
            self._job_end = None
            self._reset_phase(Phase.SCANNING, 0, 0)

    def begin_phase(self, phase: Phase, files_total: int = 0, bytes_total: int = 0) -> None:
        with self._lock:
            self._reset_phase(phase, files_total, bytes_total)

    def advance(self, files: int = 0, nbytes: int = 0) -> None:
        with self._lock:
            self._files_done += files
            self._bytes_done += nbytes
            now = self._clock()
            if now - self._samples[-1][0] >= self.SAMPLE_INTERVAL:
                self._samples.append((now, self._bytes_done, self._files_done))
                while len(self._samples) > 1 and self._samples[1][0] <= now - self._window:
                    self._samples.popleft()

    def add_bytes(self, nbytes: int) -> None:
        """Progress callback for :mod:`bloodhound.core.hashing`."""
        self.advance(nbytes=nbytes)

    def add_totals(self, files: int = 0, nbytes: int = 0) -> None:
        """Grow the current phase's totals, e.g. when a file has to be copied again."""
        with self._lock:
            self._files_total += files
            self._bytes_total += nbytes

    def set_current(self, path: str | None) -> None:
        with self._lock:
            self._current = path

    def finish(self) -> None:
        with self._lock:
            self._phase = Phase.FINISHED
            self._current = None
            self._job_end = self._clock()

    # -- reading -----------------------------------------------------------

    def snapshot(self) -> ProgressSnapshot:
        with self._lock:
            now = self._clock()
            elapsed = 0.0
            if self._job_start is not None:
                elapsed = (self._job_end if self._job_end is not None else now) - self._job_start

            rate = files_rate = None
            start_time, start_bytes, start_files = self._samples[0]
            span = now - start_time
            if self._phase in _TIMED_PHASES and span >= self.MIN_RATE_SPAN:
                rate = (self._bytes_done - start_bytes) / span
                files_rate = (self._files_done - start_files) / span

            return ProgressSnapshot(
                phase=self._phase,
                files_done=self._files_done,
                files_total=self._files_total,
                bytes_done=self._bytes_done,
                bytes_total=self._bytes_total,
                elapsed=elapsed,
                rate=rate,
                eta=self._eta(rate, files_rate),
                current_file=self._current,
            )

    # -- internals (call with the lock held) -------------------------------

    def _reset_phase(self, phase: Phase, files_total: int, bytes_total: int) -> None:
        self._phase = phase
        self._files_total = files_total
        self._bytes_total = bytes_total
        self._files_done = 0
        self._bytes_done = 0
        self._current = None
        self._samples: deque[tuple[float, int, int]] = deque([(self._clock(), 0, 0)])

    def _eta(self, rate: float | None, files_rate: float | None) -> float | None:
        if self._phase not in _TIMED_PHASES:
            return None
        bytes_left = max(0, self._bytes_total - self._bytes_done)
        files_left = max(0, self._files_total - self._files_done)
        if bytes_left == 0 and files_left == 0:
            return 0.0
        if bytes_left and rate:
            return bytes_left / rate
        if not bytes_left and files_rate:  # only empty files left
            return files_left / files_rate
        return None
