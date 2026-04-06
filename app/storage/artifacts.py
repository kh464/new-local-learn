from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactPaths:
    base_dir: Path
    task_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_dir", Path(self.base_dir))

    @property
    def task_dir(self) -> Path:
        return self.base_dir / self.task_id

    @property
    def repo_dir(self) -> Path:
        return self.task_dir / "repo"

    @property
    def markdown_path(self) -> Path:
        return self.task_dir / "result.md"
