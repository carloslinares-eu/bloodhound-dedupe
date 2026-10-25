"""The job that finds unique files and copies them, using a pool of worker threads.

A job runs in four phases:

1. **Scanning** - walk every source folder and list each file with its size.
2. **Hashing** - files whose size is unique cannot have a duplicate, so only
   files that share a size with another file are hashed (SHA-256), in parallel.
   Among identical files the first one found is kept.
3. **Copying** - copy each unique file into ``<destination>/<source name>/...``,
   hashing the data while it is copied. Copies already present from an earlier
   (possibly stopped) run are kept, so a job can be resumed.
4. **Verifying** - re-read every copy and compare its hash with the source; any
   mismatch is copied again.
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from operator import attrgetter
from typing import TypeVar

from bloodhound.core.errors import OperationCancelled, VerificationError
from bloodhound.core.hashing import copy_file, hash_file
from bloodhound.core.models import FileEntry, FileError, JobResult, Phase, ProgressSnapshot
from bloodhound.core.progress import ProgressTracker
from bloodhound.core.scanner import assign_root_labels, iter_files
from bloodhound.utils.paths import StrPath, is_within, path_key, unique_paths

log = logging.getLogger(__name__)

T = TypeVar("T")

MAX_WORKERS = 64


def default_workers() -> int:
    """A sensible number of worker threads for SSDs and network shares."""
    return max(1, min(8, os.cpu_count() or 4))


class DedupeJob:
    """Copies one instance of every unique file from ``sources`` into ``destination``.

    Call :meth:`run` from a background thread; it blocks until the job ends and
    returns a :class:`JobResult`. From any other thread, :meth:`snapshot` reports
    progress and :meth:`cancel` asks the job to stop as soon as possible.
    """

    def __init__(self, sources: Iterable[StrPath], destination: StrPath, workers: int | None = None):
        self.sources = unique_paths(source for source in sources if source)
        if not self.sources:
            raise ValueError("Please add at least one source folder.")
        if not destination:
            raise ValueError("Please choose a destination folder.")
        self.destination = os.path.abspath(destination)
        for source in self.sources:
            if not os.path.isdir(source):
                raise ValueError(f"This source folder doesn't exist or isn't a folder:\n{source}")
            if is_within(source, self.destination):
                raise ValueError(
                    "The destination folder can't be one of the source folders or contain one of them:\n"
                    f"{source}"
                )
        self.workers = max(1, min(MAX_WORKERS, workers or default_workers()))

        self.result: JobResult | None = None
        self._cancel = threading.Event()
        self._tracker = ProgressTracker()
        self._errors: list[FileError] = []

    # -- control -------------------------------------------------------------

    def cancel(self) -> None:
        """Ask the job to stop. Files being copied are discarded; finished copies are kept."""
        self._cancel.set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def snapshot(self) -> ProgressSnapshot:
        return self._tracker.snapshot()

    def run(self) -> JobResult:
        """Run every phase and return the totals. Must only be called once."""
        result = JobResult(sources=list(self.sources), destination=self.destination, errors=self._errors)
        started = time.monotonic()
        self._tracker.start_job()
        try:
            entries = self._scan(result)
            unique = self._find_unique(entries, result)
            copied = self._copy(unique, result)
            self._verify(copied, result)
        except OperationCancelled:
            result.cancelled = True
        finally:
            self._tracker.finish()
            result.elapsed = time.monotonic() - started
            self.result = result
        return result

    # -- phases ----------------------------------------------------------------

    def _scan(self, result: JobResult) -> list[FileEntry]:
        entries: list[FileEntry] = []
        labels = assign_root_labels(self.sources)
        for source, label in zip(self.sources, labels):
            dest_root = os.path.join(self.destination, label)
            for path, size in iter_files(
                source,
                exclude=[self.destination],
                on_error=lambda p, exc: self._record(p, exc, Phase.SCANNING),
                cancel_event=self._cancel,
            ):
                dest = os.path.join(dest_root, os.path.relpath(path, source))
                entries.append(FileEntry(index=len(entries), source=path, size=size, dest=dest))
                self._tracker.advance(files=1, nbytes=size)
        result.files_found = len(entries)
        result.bytes_found = sum(entry.size for entry in entries)
        return entries

    def _find_unique(self, entries: list[FileEntry], result: JobResult) -> list[FileEntry]:
        by_size: dict[int, list[FileEntry]] = defaultdict(list)
        for entry in entries:
            by_size[entry.size].append(entry)
        to_hash = [entry for group in by_size.values() if len(group) > 1 for entry in group]

        self._tracker.begin_phase(Phase.HASHING, len(to_hash), sum(entry.size for entry in to_hash))
        for entry, digest, error in self._parallel(self._hash_task, to_hash):
            self._tracker.advance(files=1)
            if error is not None:
                self._record(entry.source, error, Phase.HASHING)
            else:
                entry.digest = digest

        unique: list[FileEntry] = []
        for group in by_size.values():
            if len(group) == 1:
                unique.extend(group)
                continue
            kept: set[str] = set()
            for entry in group:  # groups are in discovery order, so the first copy wins
                if entry.digest is None:
                    continue  # unreadable; already reported
                if entry.digest in kept:
                    result.duplicate_files += 1
                    result.duplicate_bytes += entry.size
                else:
                    kept.add(entry.digest)
                    unique.append(entry)
        unique.sort(key=attrgetter("index"))
        _make_destinations_unique(unique)

        result.unique_files = len(unique)
        result.unique_bytes = sum(entry.size for entry in unique)
        return unique

    def _copy(self, unique: list[FileEntry], result: JobResult) -> list[FileEntry]:
        self._tracker.begin_phase(Phase.COPYING, len(unique), sum(entry.size for entry in unique))
        copied: list[FileEntry] = []
        for entry, was_copied, error in self._parallel(self._copy_task, unique):
            self._tracker.advance(files=1)
            if error is not None:
                self._record(entry.source, error, Phase.COPYING)
                continue
            copied.append(entry)
            if was_copied:
                result.files_copied += 1
                result.bytes_copied += entry.size
            else:
                result.files_already_present += 1
        copied.sort(key=attrgetter("index"))
        return copied

    def _verify(self, copied: list[FileEntry], result: JobResult) -> None:
        self._tracker.begin_phase(Phase.VERIFYING, len(copied), sum(entry.size for entry in copied))
        for entry, repaired, error in self._parallel(self._verify_task, copied):
            self._tracker.advance(files=1)
            if error is not None:
                self._record(entry.dest, error, Phase.VERIFYING)
                continue
            result.files_verified += 1
            if repaired:
                result.files_repaired += 1

    # -- per-file work (runs on the worker threads) -------------------------

    def _hash_task(self, entry: FileEntry) -> str:
        self._check_cancel()
        self._tracker.set_current(entry.source)
        with self._progress_for(entry.size) as report:
            return hash_file(entry.source, self._cancel, report)

    def _copy_task(self, entry: FileEntry) -> bool:
        """Copy one file; returns False if an identical-size copy was already there."""
        self._check_cancel()
        self._tracker.set_current(entry.source)
        with self._progress_for(entry.size) as report:
            if _is_file_of_size(entry.dest, entry.size):
                # Left by an earlier run. Make sure we know the source hash so the
                # verify phase can prove the existing copy is identical.
                if entry.digest is None:
                    entry.digest = hash_file(entry.source, self._cancel, report)
                return False
            os.makedirs(os.path.dirname(entry.dest), exist_ok=True)
            digest = copy_file(entry.source, entry.dest, self._cancel, report)
        if entry.digest is not None and entry.digest != digest:
            log.warning("%s changed while Bloodhound was running", entry.source)
        entry.digest = digest
        return True

    def _verify_task(self, entry: FileEntry) -> bool:
        """Check one copy; returns True if it was wrong and has been copied again."""
        self._check_cancel()
        self._tracker.set_current(entry.dest)
        with self._progress_for(entry.size) as report:
            try:
                digest = hash_file(entry.dest, self._cancel, report)
            except FileNotFoundError:
                digest = None
        if digest == entry.digest:
            return False

        log.warning("Copy of %s did not match its source; copying it again", entry.source)
        self._tracker.add_totals(nbytes=2 * entry.size)  # one more copy and one more check
        with self._progress_for(2 * entry.size) as report:
            source_digest = copy_file(entry.source, entry.dest, self._cancel, report)
            copy_digest = hash_file(entry.dest, self._cancel, report)
        if copy_digest != source_digest:
            raise VerificationError(f"The copy still differs from the source after copying it again: {entry.dest}")
        entry.digest = source_digest
        return True

    # -- helpers -----------------------------------------------------------------

    def _parallel(
        self, task: Callable[[FileEntry], T], entries: Sequence[FileEntry]
    ) -> Iterator[tuple[FileEntry, T | None, OSError | None]]:
        """Run ``task`` for every entry on the thread pool and yield ``(entry, result, error)`` per finished task.

        Only a few tasks per worker are queued at a time, which keeps memory flat
        for millions of files and lets Stop take effect quickly.
        """
        pending_limit = self.workers * 4
        remaining = iter(entries)
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="bloodhound") as pool:
            pending: dict[Future[T], FileEntry] = {}

            def refill() -> None:
                while len(pending) < pending_limit and not self._cancel.is_set():
                    next_entry = next(remaining, None)
                    if next_entry is None:
                        return
                    pending[pool.submit(task, next_entry)] = next_entry

            refill()
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    entry = pending.pop(future)
                    error = future.exception()
                    if isinstance(error, OperationCancelled):
                        continue
                    if error is None:
                        yield entry, future.result(), None
                    elif isinstance(error, OSError):
                        yield entry, None, error
                    else:  # a bug, not a bad file: stop the other workers and fail the job
                        self._cancel.set()
                        raise error
                refill()
        self._check_cancel()

    @contextlib.contextmanager
    def _progress_for(self, size: int) -> Iterator[Callable[[int], None]]:
        """Report bytes as they are processed, topping up to ``size`` if a file ends early or fails."""
        reported = 0

        def report(nbytes: int) -> None:
            nonlocal reported
            reported += nbytes
            self._tracker.add_bytes(nbytes)

        try:
            yield report
        finally:
            if reported < size and not self._cancel.is_set():
                self._tracker.add_bytes(size - reported)

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise OperationCancelled

    def _record(self, path: str, error: OSError, phase: Phase) -> None:
        message = error.strerror or str(error)
        log.warning("%s: %s", path, message)
        self._errors.append(FileError(path=path, message=message, phase=phase))


def _is_file_of_size(path: str, size: int) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) == size
    except OSError:
        return False


def _make_destinations_unique(entries: list[FileEntry]) -> None:
    """Rename destinations that would clash, e.g. ``a.txt`` and ``A.txt`` from a case-sensitive drive."""
    claimed: set[str] = set()
    for entry in entries:
        key = path_key(entry.dest)
        if key in claimed:
            stem, ext = os.path.splitext(entry.dest)
            counter = 2
            while path_key(f"{stem} ({counter}){ext}") in claimed:
                counter += 1
            entry.dest = f"{stem} ({counter}){ext}"
            key = path_key(entry.dest)
        claimed.add(key)
