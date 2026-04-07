from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
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


def prune_expired_task_artifacts(base_dir: Path | str, max_age_seconds: int, *, now: float | None = None) -> list[str]:
    if max_age_seconds <= 0:
        return []

    root = Path(base_dir)
    if not root.exists():
        return []

    cutoff = (time.time() if now is None else now) - max_age_seconds
    removed: list[str] = []
    for task_dir in sorted(root.iterdir(), key=lambda path: path.name):
        if not task_dir.is_dir():
            continue
        try:
            last_modified = _latest_mtime(task_dir)
        except OSError:
            continue
        if last_modified >= cutoff:
            continue
        shutil.rmtree(task_dir, ignore_errors=False)
        removed.append(task_dir.name)
    return removed


def _latest_mtime(task_dir: Path) -> float:
    latest = task_dir.stat().st_mtime
    for path in task_dir.rglob("*"):
        latest = max(latest, path.stat().st_mtime)
    return latest
