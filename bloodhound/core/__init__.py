"""The file-processing engine. Nothing in here depends on the GUI."""

from bloodhound.core.engine import MAX_WORKERS, DedupeJob, default_workers
from bloodhound.core.errors import OperationCancelled, VerificationError
from bloodhound.core.models import FileError, JobResult, Phase, ProgressSnapshot

__all__ = [
    "MAX_WORKERS",
    "DedupeJob",
    "FileError",
    "JobResult",
    "OperationCancelled",
    "Phase",
    "ProgressSnapshot",
    "VerificationError",
    "default_workers",
]
