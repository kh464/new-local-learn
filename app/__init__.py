"""Application package."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None


if pytest is not None:

    @pytest.fixture
    def tmp_path() -> Path:
        base = Path.cwd() / "tmpbase"
        base.mkdir(parents=True, exist_ok=True)
        path = base / uuid4().hex
        path.mkdir()
        return path
