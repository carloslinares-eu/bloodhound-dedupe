"""Discovering files inside the source folders."""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable, Iterable, Iterator, Sequence

from bloodhound.core.errors import OperationCancelled
from bloodhound.utils.paths import path_key

ErrorCallback = Callable[[str, OSError], None]

_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003  # NTFS junction
_INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*]+')


def assign_root_labels(sources: Sequence[str]) -> list[str]:
    """Pick the folder name each source gets inside the destination.

    Normally that is the source folder's own name. Sources that share a name
    (``D:/Photos`` and ``E:/Photos``) get ``Photos`` and ``Photos (2)`` so their
    files can never overwrite each other. Drive roots become ``Drive D``.
    """
    labels: list[str] = []
    taken: set[str] = set()
    for source in sources:
        normalized = os.path.normpath(source)
        base = os.path.basename(normalized)
        if not base:  # a drive or share root such as "D:\" or "/"
            drive = os.path.splitdrive(normalized)[0]
            base = f"Drive {drive}" if drive else "Root"
        base = _INVALID_NAME_CHARS.sub("_", base).strip(" ._") or "Folder"

        label, counter = base, 2
        while os.path.normcase(label) in taken:
            label = f"{base} ({counter})"
            counter += 1
        taken.add(os.path.normcase(label))
        labels.append(label)
    return labels


def _is_link(entry: os.DirEntry) -> bool:
    """True for symlinks and Windows junctions, which are skipped to avoid loops."""
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)  # Python 3.12+
    if is_junction is not None:
        return is_junction()
    reparse_tag = getattr(entry.stat(follow_symlinks=False), "st_reparse_tag", 0)
    return reparse_tag == _IO_REPARSE_TAG_MOUNT_POINT


def iter_files(
    root: str,
    exclude: Iterable[str] = (),
    on_error: ErrorCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> Iterator[tuple[str, int]]:
    """Yield ``(path, size)`` for every file below ``root``, in a stable sorted order.

    Each folder's files come before its subfolders, which are visited
    alphabetically. Folders in ``exclude`` (e.g. the destination) and linked
    folders are skipped. Unreadable entries are reported to ``on_error``.
    """
    excluded = {path_key(path) for path in exclude}
    pending = [root]
    while pending:
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled
        directory = pending.pop()
        try:
            with os.scandir(directory) as scan:
                entries = sorted(scan, key=lambda entry: entry.name)
        except OSError as exc:
            if on_error is not None:
                on_error(directory, exc)
            continue

        subfolders = []
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if not _is_link(entry) and path_key(entry.path) not in excluded:
                        subfolders.append(entry.path)
                elif entry.is_file():
                    yield entry.path, entry.stat().st_size
            except OSError as exc:
                if on_error is not None:
                    on_error(entry.path, exc)
        pending.extend(reversed(subfolders))
