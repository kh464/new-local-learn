from __future__ import annotations

from urllib.parse import urlparse

_SUPPORTED_HOSTS = {"github.com", "www.github.com"}


def normalize_github_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _SUPPORTED_HOSTS:
        raise ValueError(f"Unsupported GitHub host: {parsed.hostname or ''}")
    path = parsed.path or ""
    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"https://github.com{path}"
