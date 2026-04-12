from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from app.core.config import Settings

_RELOAD_SOURCE_DIRS = ("app", "tests", "config")


def _resolve_path(path: Path, *, cwd: Path) -> Path:
    return path if path.is_absolute() else (cwd / path)


def build_reload_watch_config(settings: Settings, *, cwd: Path | None = None) -> tuple[list[str], list[str]]:
    project_root = (cwd or Path.cwd()).resolve()

    reload_dirs: list[str] = []
    for relative in _RELOAD_SOURCE_DIRS:
        candidate = (project_root / relative).resolve()
        if candidate.is_dir():
            reload_dirs.append(str(candidate))
    if not reload_dirs:
        reload_dirs.append(str(project_root))

    reload_excludes: list[str] = []
    for candidate in (settings.artifacts_dir, settings.workspace_dir):
        resolved = _resolve_path(Path(candidate), cwd=project_root).resolve()
        rendered = str(resolved)
        if rendered not in reload_excludes:
            reload_excludes.append(rendered)

    return reload_dirs, reload_excludes


def main() -> None:
    settings = Settings()
    reload_dirs, reload_excludes = build_reload_watch_config(settings)
    host = os.getenv("UVICORN_HOST", "127.0.0.1")
    port = int(os.getenv("UVICORN_PORT", "8000"))

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True,
        reload_dirs=reload_dirs,
        reload_excludes=reload_excludes,
        log_level=str(settings.log_level).lower(),
    )


if __name__ == "__main__":
    main()
