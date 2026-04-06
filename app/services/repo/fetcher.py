from __future__ import annotations

from urllib.parse import urlparse

_SUPPORTED_HOSTS = {"github.com", "www.github.com"}


def normalize_github_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _SUPPORTED_HOSTS:
        raise ValueError(f"Unsupported GitHub host: {parsed.hostname or ''}")
    path = (parsed.path or "").strip("/")
    if not path:
        raise ValueError("Invalid GitHub repository path: empty path")
    parts = [segment for segment in path.split("/") if segment]
    if len(parts) != 2:
        raise ValueError("Invalid GitHub repository path: expected /owner/repo")
    owner, repo = parts
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        raise ValueError("Invalid GitHub repository path: expected /owner/repo")
    return f"https://github.com/{owner}/{repo}"
