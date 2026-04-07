from __future__ import annotations

import asyncio
import shutil
from urllib.parse import urlparse
from pathlib import Path

_SUPPORTED_HOSTS = ("github.com", "www.github.com")


def normalize_github_url(url: str, *, allowed_hosts: tuple[str, ...] | None = None) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    supported_hosts = tuple(value.lower() for value in (allowed_hosts or _SUPPORTED_HOSTS))
    if host not in supported_hosts:
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
    return f"https://{host}/{owner}/{repo}"


async def clone_github_repo(
    github_url: str,
    destination: Path | str,
    *,
    timeout_seconds: int = 60,
) -> Path:
    normalized_url = normalize_github_url(github_url)
    target = Path(destination)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)

    process = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        "--depth",
        "1",
        normalized_url,
        str(target),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        shutil.rmtree(target, ignore_errors=True)
        raise TimeoutError(f"Timed out cloning repository after {timeout_seconds} seconds.") from exc

    if process.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        error_message = stderr.decode("utf-8", errors="ignore").strip() or "git clone failed"
        raise RuntimeError(error_message)

    return target


def read_repository_files(repo_path: Path | str, file_list: list[str]) -> dict[str, str]:
    root = Path(repo_path).resolve()
    contents: dict[str, str] = {}

    for relative_path in file_list:
        candidate = (root / relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            continue
        if not candidate.is_file():
            continue
        try:
            contents[Path(relative_path).as_posix()] = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            contents[Path(relative_path).as_posix()] = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

    return contents
