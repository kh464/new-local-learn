from app.services.repo.fetcher import normalize_github_url
from app.services.repo.scanner import RepositoryScanner


def test_normalize_github_url_rejects_non_github_hosts():
    try:
        normalize_github_url("https://gitlab.com/example/project")
    except ValueError as exc:
        assert "Unsupported GitHub host" in str(exc)
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
