from __future__ import annotations

import pytest

from bloodhound.utils.formatting import format_bytes, format_duration, format_rate, shorten_path


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, "0 B"),
        (999, "999 B"),
        (1000, "0.98 KB"),
        (1536, "1.50 KB"),
        (50 * 1024, "50.0 KB"),
        (512 * 1024, "512 KB"),
        (1024**2, "1.00 MB"),
        (int(1.25 * 1024**3), "1.25 GB"),
        (3 * 1024**4, "3.00 TB"),
    ],
)
def test_format_bytes(size, expected):
    assert format_bytes(size) == expected


def test_format_rate():
    assert format_rate(85.3 * 1024**2) == "85.3 MB/s"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00"),
        (59.4, "00:00:59"),
        (61, "00:01:01"),
        (3 * 3600 + 25 * 60 + 9, "03:25:09"),
        (90000, "1d 01:00:00"),
        (None, "--:--:--"),
        (-1, "--:--:--"),
        (float("inf"), "--:--:--"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


def test_shorten_path_keeps_both_ends():
    path = "C:/Users/someone/Pictures/2024/Holidays/Beach/IMG_0001.jpg"
    short = shorten_path(path, 30)
    assert len(short) == 30
    assert short.startswith("C:/Users")
    assert short.endswith("IMG_0001.jpg")
    assert "…" in short
    assert shorten_path("short", 30) == "short"
