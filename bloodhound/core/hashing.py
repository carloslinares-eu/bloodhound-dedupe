"""Chunked, cancellable hashing and copying of single files."""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import threading
from collections.abc import Callable

from bloodhound.core.errors import OperationCancelled

CHUNK_SIZE = 1024 * 1024  # 1 MiB: large enough for fast disk I/O, small enough to stop quickly
PARTIAL_SUFFIX = ".bloodhound-partial"

ProgressCallback = Callable[[int], None]


def _check_cancel(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelled


def hash_file(
    path: str,
    cancel_event: threading.Event | None = None,
    on_progress: ProgressCallback | None = None,
    chunk_size: int = CHUNK_SIZE,
) -> str:
    """Return the SHA-256 hex digest of ``path``.

    ``on_progress`` is called with the number of bytes read after every chunk.
    Raises :class:`OperationCancelled` as soon as ``cancel_event`` is set.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            _check_cancel(cancel_event)
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            if on_progress is not None:
                on_progress(len(chunk))
    return digest.hexdigest()


def copy_file(
    source: str,
    dest: str,
    cancel_event: threading.Event | None = None,
    on_progress: ProgressCallback | None = None,
    chunk_size: int = CHUNK_SIZE,
) -> str:
    """Copy ``source`` to ``dest`` and return the SHA-256 of the data copied.

    The data is written to a temporary file next to ``dest`` that only replaces
    ``dest`` once it is complete, so a stopped or failed copy never leaves a
    half-written file behind. Timestamps and permission bits are preserved like
    :func:`shutil.copy2`.
    """
    partial = dest + PARTIAL_SUFFIX
    digest = hashlib.sha256()
    try:
        with open(source, "rb") as src, open(partial, "wb") as dst:
            while True:
                _check_cancel(cancel_event)
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
                dst.write(chunk)
                if on_progress is not None:
                    on_progress(len(chunk))
        shutil.copystat(source, partial)
        os.replace(partial, dest)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(partial)
        raise
    return digest.hexdigest()
