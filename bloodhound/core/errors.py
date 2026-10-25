"""Exceptions shared by the core modules."""


class OperationCancelled(Exception):
    """Raised inside worker code once the user has pressed Stop."""


class VerificationError(OSError):
    """A copied file still differs from its source after being copied a second time."""
