from __future__ import annotations

import os
from pathlib import Path

_IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
_KEY_FILES = {"README.md", "package.json", "pyproject.toml", "requirements.txt"}


class RepositoryScanner:
    def __init__(self, max_file_count: int, max_file_bytes: int) -> None:
        self.max_file_count = max_file_count
        self.max_file_bytes = max_file_bytes

    def scan(self, repo_path: Path | str) -> dict[str, object]:
        root = Path(repo_path)
        if not root.is_dir():
            raise ValueError("Repository root must be an existing directory.")
        files: list[str] = []
        key_files: list[str] = []

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in sorted(dirnames) if name not in _IGNORED_DIRS]
            for filename in sorted(filenames):
                if len(files) >= self.max_file_count:
                    return {"files": files, "key_files": key_files, "file_count": len(files)}
                file_path = Path(dirpath) / filename
                try:
                    if file_path.stat().st_size > self.max_file_bytes:
                        continue
                except OSError:
                    continue
                relative_path = file_path.relative_to(root).as_posix()
                files.append(relative_path)
                if filename in _KEY_FILES:
                    key_files.append(relative_path)

        return {"files": files, "key_files": key_files, "file_count": len(files)}
