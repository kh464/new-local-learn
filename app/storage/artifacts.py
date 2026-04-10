from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import string
import time


@dataclass(frozen=True)
class ArtifactPaths:
    base_dir: Path
    task_id: str

    @property
    def task_dir(self) -> Path:
        return self.base_dir / self.task_id

    @property
    def repo_dir(self) -> Path:
        return self.task_dir / "repo"

    @property
    def markdown_path(self) -> Path:
        return self.task_dir / "result.md"

    @property
    def html_path(self) -> Path:
        return self.task_dir / "result.html"

    @property
    def pdf_path(self) -> Path:
        return self.task_dir / "result.pdf"

    @property
    def knowledge_db_path(self) -> Path:
        return self.task_dir / "knowledge.db"

    @property
    def repo_map_path(self) -> Path:
        return self.task_dir / "repo_map.json"


def prune_expired_task_artifacts(base_dir: Path | str, max_age_seconds: int, *, now: float | None = None) -> list[str]:
    if max_age_seconds <= 0:
        return []

    root = Path(base_dir)
    if not root.exists():
        return []

    cutoff = (time.time() if now is None else now) - max_age_seconds
    removed: list[str] = []
    for task_dir in sorted(root.iterdir(), key=lambda path: path.name):
        if not _is_managed_task_dir(task_dir):
            continue
        try:
            last_modified = _latest_mtime(task_dir)
        except OSError:
            continue
        if last_modified >= cutoff:
            continue
        try:
            shutil.rmtree(task_dir, ignore_errors=False)
        except OSError:
            continue
        removed.append(task_dir.name)
    return removed


def _is_managed_task_dir(path: Path) -> bool:
    try:
        if not path.is_dir():
            return False
    except OSError:
        return False
    return len(path.name) == 32 and all(char in string.hexdigits for char in path.name)


def _latest_mtime(task_dir: Path) -> float:
    latest = task_dir.stat().st_mtime
    for path in task_dir.rglob("*"):
        latest = max(latest, path.stat().st_mtime)
    return latest
