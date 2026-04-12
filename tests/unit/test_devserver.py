from pathlib import Path

from app.core.config import Settings
from app.devserver import build_reload_watch_config


def test_build_reload_watch_config_limits_reload_scope_and_excludes_runtime_artifacts(
    tmp_path: Path,
    monkeypatch,
):
    for relative in ("app", "tests", "config", "artifacts", "artifacts/workspace"):
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "artifacts" / "workspace"))

    reload_dirs, reload_excludes = build_reload_watch_config(Settings(), cwd=tmp_path)

    assert reload_dirs == [
        str((tmp_path / "app").resolve()),
        str((tmp_path / "tests").resolve()),
        str((tmp_path / "config").resolve()),
    ]
    assert reload_excludes == [
        str((tmp_path / "artifacts").resolve()),
        str((tmp_path / "artifacts" / "workspace").resolve()),
    ]
