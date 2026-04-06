"""Application package marker."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

__version__ = "0.1.0"

try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None


if pytest is not None:

    @pytest.fixture
    def tmp_path() -> Path:
        # Temporary Task 1 sandbox workaround; move this fixture to tests/conftest.py in Task 2.
        base = Path.cwd() / "tmpbase"
        base.mkdir(parents=True, exist_ok=True)
        path = base / uuid4().hex
        path.mkdir()
        return path
