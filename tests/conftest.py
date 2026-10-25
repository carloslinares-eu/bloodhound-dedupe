from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def make_tree(tmp_path: Path):
    """Create files from a ``{relative_path: bytes_or_text}`` mapping under ``tmp_path / name``."""

    def make(name: str, files: dict[str, bytes | str]) -> Path:
        root = tmp_path / name
        root.mkdir(parents=True, exist_ok=True)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            data = content.encode() if isinstance(content, str) else content
            path.write_bytes(data)
        return root

    return make
