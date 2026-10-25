"""Human-friendly formatting of sizes, speeds, durations and paths."""

from __future__ import annotations

import math

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_bytes(num_bytes: float) -> str:
    """Format a size using binary multiples (1 KB = 1024 bytes), as Windows Explorer does.

    >>> format_bytes(512), format_bytes(1536), format_bytes(1.25 * 1024 ** 3)
    ('512 B', '1.50 KB', '1.25 GB')
    """
    value = float(num_bytes)
    if abs(value) < 1000:
        return f"{value:.0f} B"
    for unit in _UNITS[1:]:
        value /= 1024
        decimals = 2 if abs(value) < 10 else 1 if abs(value) < 100 else 0
        if abs(round(value, decimals)) < 1000 or unit == _UNITS[-1]:
            return f"{value:.{decimals}f} {unit}"
    raise AssertionError("unreachable")


def format_rate(bytes_per_second: float) -> str:
    """Format a transfer speed, e.g. ``'85.3 MB/s'``."""
    return f"{format_bytes(bytes_per_second)}/s"


def format_duration(seconds: float | None) -> str:
    """Format seconds as ``HH:MM:SS`` (with a day prefix when needed); unknown values give ``'--:--:--'``."""
    if seconds is None or math.isnan(seconds) or math.isinf(seconds) or seconds < 0:
        return "--:--:--"
    total = int(round(seconds))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    clock = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{days}d {clock}" if days else clock


def shorten_path(path: str, max_chars: int) -> str:
    """Shorten ``path`` to ``max_chars`` by replacing its middle with an ellipsis."""
    if len(path) <= max_chars:
        return path
    if max_chars < 5:
        return path[-max_chars:]
    keep = max_chars - 1
    head = keep // 3
    return f"{path[:head]}…{path[-(keep - head):]}"
