from __future__ import annotations

import os
from pathlib import Path

_IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
_KEY_FILES = {"README.md", "package.json", "pyproject.toml", "requirements.txt"}


class RepositoryLimitError(ValueError):
    pass


class RepositoryScanner:
    def __init__(self, max_file_count: int, max_file_bytes: int, max_total_bytes: int) -> None:
        self.max_file_count = max_file_count
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes

    def scan(self, repo_path: Path | str) -> dict[str, object]:
        root = Path(repo_path)
        if not root.is_dir():
            raise ValueError("Repository root must be an existing directory.")
        files: list[str] = []
        key_files: list[str] = []
        total_bytes = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in sorted(dirnames) if name not in _IGNORED_DIRS]
            for filename in sorted(filenames):
                if len(files) >= self.max_file_count:
                    raise RepositoryLimitError(
                        f"Repository exceeds file count limit of {self.max_file_count} files."
                    )
                file_path = Path(dirpath) / filename
                try:
                    file_size = file_path.stat().st_size
                    if file_size > self.max_file_bytes:
                        continue
                except OSError:
                    continue
                if total_bytes + file_size > self.max_total_bytes:
                    raise RepositoryLimitError(
                        f"Repository exceeds total scanned bytes limit of {self.max_total_bytes} bytes."
                    )
                relative_path = file_path.relative_to(root).as_posix()
                files.append(relative_path)
                total_bytes += file_size
                if filename in _KEY_FILES:
                    key_files.append(relative_path)

        return {"files": files, "key_files": key_files, "file_count": len(files)}
