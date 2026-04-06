from app.services.repo.fetcher import normalize_github_url
from app.services.repo.scanner import RepositoryScanner


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


def test_repository_scanner_skips_node_modules(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignore.js").write_text("console.log('x')", encoding="utf-8")
    summary = RepositoryScanner(max_file_count=10, max_file_bytes=10_000).scan(tmp_path)
    assert "src/main.py" in summary["files"]
    assert "node_modules/ignore.js" not in summary["files"]


def test_repository_scanner_enforces_max_file_count(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    summary = RepositoryScanner(max_file_count=2, max_file_bytes=10_000).scan(tmp_path)
    assert summary["file_count"] == 2
    assert "c.txt" not in summary["files"]


def test_repository_scanner_rejects_invalid_root(tmp_path):
    missing = tmp_path / "missing"
    try:
        RepositoryScanner(max_file_count=10, max_file_bytes=10_000).scan(missing)
    except ValueError as exc:
        assert "Repository root must be an existing directory" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
