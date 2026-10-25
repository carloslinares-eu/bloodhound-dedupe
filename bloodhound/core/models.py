"""Plain data types passed between the engine and the user interface."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Phase(enum.Enum):
    """The steps a job goes through, in order."""

    IDLE = "idle"
    SCANNING = "scanning"  # walking the source folders and listing files
    HASHING = "hashing"  # SHA-256 of files whose size matches another file
    COPYING = "copying"  # copying one copy of every unique file
    VERIFYING = "verifying"  # re-reading every copy and comparing hashes
    FINISHED = "finished"


@dataclass(slots=True)
class FileEntry:
    """One file found in a source folder."""

    index: int  # discovery order; when files are identical the lowest index is kept
    source: str
    size: int
    dest: str
    digest: str | None = None  # SHA-256 hex digest, filled in once the file has been read


@dataclass(frozen=True, slots=True)
class FileError:
    """A file or folder that could not be processed."""

    path: str
    message: str
    phase: Phase


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    """A consistent view of the job's progress, safe to read from the GUI thread."""

    phase: Phase
    files_done: int
    files_total: int
    bytes_done: int
    bytes_total: int
    elapsed: float  # seconds since the job started
    rate: float | None  # bytes per second over the last few seconds
    eta: float | None  # seconds left in the current phase
    current_file: str | None

    @property
    def fraction(self) -> float:
        """Completed share of the current phase, from 0.0 to 1.0."""
        if self.bytes_total > 0:
            done, total = self.bytes_done, self.bytes_total
        elif self.files_total > 0:
            done, total = self.files_done, self.files_total
        else:
            return 1.0 if self.phase is Phase.FINISHED else 0.0
        return max(0.0, min(1.0, done / total))


@dataclass
class JobResult:
    """Totals reported once a job ends, whether it finished or was stopped."""

    sources: list[str]
    destination: str
    files_found: int = 0
    bytes_found: int = 0
    unique_files: int = 0
    unique_bytes: int = 0
    duplicate_files: int = 0
    duplicate_bytes: int = 0
    files_copied: int = 0
    bytes_copied: int = 0
    files_already_present: int = 0
    files_verified: int = 0
    files_repaired: int = 0
    errors: list[FileError] = field(default_factory=list)
    cancelled: bool = False
    elapsed: float = 0.0
