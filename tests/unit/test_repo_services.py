from pathlib import Path

import pytest

from app.services.repo.fetcher import clone_github_repo, normalize_github_url, read_repository_files
from app.services.repo.scanner import RepositoryLimitError, RepositoryScanner
from app.storage.artifacts import prune_expired_task_artifacts


def test_normalize_github_url_rejects_non_github_hosts():
    try:
        normalize_github_url("https://gitlab.com/example/project")
    except ValueError as exc:
        assert "Unsupported GitHub host" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_normalize_github_url_canonicalizes_repo_root():
    normalized = normalize_github_url("https://github.com/example/project.git/")
    assert normalized == "https://github.com/example/project"


def test_normalize_github_url_rejects_non_repo_paths():
    try:
        normalize_github_url("https://github.com/example/project/tree/main")
    except ValueError as exc:
        assert "Invalid GitHub repository path" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_normalize_github_url_uses_allowed_hosts():
    normalized = normalize_github_url(
        "https://github.internal/example/project",
        allowed_hosts=("github.internal",),
    )
    assert normalized == "https://github.internal/example/project"


def test_repository_scanner_skips_node_modules(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignore.js").write_text("console.log('x')", encoding="utf-8")
    summary = RepositoryScanner(max_file_count=10, max_file_bytes=10_000, max_total_bytes=10_000).scan(tmp_path)
    assert "src/main.py" in summary["files"]
    assert "node_modules/ignore.js" not in summary["files"]


def test_repository_scanner_enforces_max_file_count(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    with pytest.raises(RepositoryLimitError) as exc:
        RepositoryScanner(max_file_count=2, max_file_bytes=10_000, max_total_bytes=10_000).scan(tmp_path)

    assert "Repository exceeds file count limit" in str(exc.value)


def test_repository_scanner_rejects_invalid_root(tmp_path):
    missing = tmp_path / "missing"
    try:
        RepositoryScanner(max_file_count=10, max_file_bytes=10_000, max_total_bytes=10_000).scan(missing)
    except ValueError as exc:
        assert "Repository root must be an existing directory" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_repository_scanner_enforces_max_total_bytes(tmp_path):
    (tmp_path / "a.txt").write_text("abcd", encoding="utf-8")
    (tmp_path / "b.txt").write_text("efgh", encoding="utf-8")

    with pytest.raises(RepositoryLimitError) as exc:
        RepositoryScanner(max_file_count=10, max_file_bytes=10_000, max_total_bytes=7).scan(tmp_path)

    assert "Repository exceeds total scanned bytes limit" in str(exc.value)


@pytest.mark.asyncio
async def test_clone_github_repo_runs_shallow_clone(monkeypatch, tmp_path):
    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = 0

        async def communicate(self):
            destination.mkdir(parents=True, exist_ok=True)
            return b"", b""

    destination = tmp_path / "repo"
    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr("app.services.repo.fetcher.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    repo_path = await clone_github_repo(
        "https://github.com/octocat/Hello-World",
        destination,
        timeout_seconds=5,
    )

    assert repo_path == destination
    assert captured["args"] == (
        "git",
        "clone",
        "--depth",
        "1",
        "https://github.com/octocat/Hello-World",
        str(destination),
    )


def test_read_repository_files_reads_requested_text_files(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "README.md").write_text("# demo\n", encoding="utf-8")
    (repo_root / "src").mkdir()
    (repo_root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    contents = read_repository_files(repo_root, ["README.md", "src/main.py", "missing.py"])

    assert contents == {
        "README.md": "# demo\n",
        "src/main.py": "print('ok')\n",
    }


def test_prune_expired_task_artifacts_removes_only_old_directories(tmp_path):
    old_dir = tmp_path / "old-task"
    old_dir.mkdir()
    (old_dir / "result.md").write_text("# old\n", encoding="utf-8")
    recent_dir = tmp_path / "recent-task"
    recent_dir.mkdir()
    (recent_dir / "result.md").write_text("# recent\n", encoding="utf-8")

    old_timestamp = old_dir.stat().st_mtime - 7200
    recent_timestamp = recent_dir.stat().st_mtime
    import os

    os.utime(old_dir, (old_timestamp, old_timestamp))
    os.utime(old_dir / "result.md", (old_timestamp, old_timestamp))
    os.utime(recent_dir, (recent_timestamp, recent_timestamp))

    removed = prune_expired_task_artifacts(tmp_path, max_age_seconds=3600)

    assert removed == ["old-task"]
    assert not old_dir.exists()
    assert recent_dir.exists()
