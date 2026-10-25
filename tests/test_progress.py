from __future__ import annotations

import pytest

from bloodhound.core.models import Phase
from bloodhound.core.progress import ProgressTracker


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_rate_and_time_remaining():
    clock = FakeClock()
    tracker = ProgressTracker(window=5.0, clock=clock)
    tracker.start_job()
    clock.now += 2
    tracker.begin_phase(Phase.COPYING, files_total=10, bytes_total=1000)
    for _ in range(4):
        clock.now += 1
        tracker.add_bytes(100)  # 100 bytes per second

    snap = tracker.snapshot()
    assert snap.rate == pytest.approx(100)
    assert snap.eta == pytest.approx(6)  # 600 bytes left
    assert snap.elapsed == pytest.approx(6)
    assert snap.fraction == pytest.approx(0.4)


def test_rate_follows_recent_speed_only():
    clock = FakeClock()
    tracker = ProgressTracker(window=5.0, clock=clock)
    tracker.start_job()
    tracker.begin_phase(Phase.HASHING, files_total=1, bytes_total=100_000)
    for _ in range(10):  # slow start: 10 B/s
        clock.now += 1
        tracker.add_bytes(10)
    for _ in range(10):  # then 1000 B/s
        clock.now += 1
        tracker.add_bytes(1000)

    assert tracker.snapshot().rate == pytest.approx(1000)


def test_no_estimate_until_there_is_enough_data():
    clock = FakeClock()
    tracker = ProgressTracker(clock=clock)
    tracker.start_job()
    tracker.begin_phase(Phase.COPYING, files_total=1, bytes_total=100)
    clock.now += 0.1
    tracker.add_bytes(1)

    snap = tracker.snapshot()
    assert snap.rate is None
    assert snap.eta is None


def test_elapsed_stops_when_finished():
    clock = FakeClock()
    tracker = ProgressTracker(clock=clock)
    tracker.start_job()
    clock.now += 42
    tracker.finish()
    clock.now += 100

    snap = tracker.snapshot()
    assert snap.phase is Phase.FINISHED
    assert snap.elapsed == pytest.approx(42)
    assert snap.eta is None
