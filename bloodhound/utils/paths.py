"""Path comparisons that respect the platform's case rules."""

from __future__ import annotations

import os
from collections.abc import Iterable


def path_key(path: str) -> str:
    """Return a key that is equal for two spellings of the same path (case-insensitive on Windows)."""
    return os.path.normcase(os.path.abspath(path))


def is_within(path: str, parent: str) -> bool:
    """True if ``path`` is ``parent`` itself or lies somewhere inside it."""
    path, parent = path_key(path), path_key(parent)
    try:
        return os.path.commonpath([path, parent]) == parent
    except ValueError:  # different drives on Windows
        return False


def unique_paths(paths: Iterable[str]) -> list[str]:
    """Absolute versions of ``paths`` with repeats removed, keeping the first spelling of each."""
    seen: set[str] = set()
    result = []
    for path in paths:
        key = path_key(path)
        if key not in seen:
            seen.add(key)
            result.append(os.path.abspath(path))
    return result
