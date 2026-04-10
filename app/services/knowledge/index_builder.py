from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.storage.knowledge_store import KnowledgeChunkRecord, KnowledgeDocumentRecord, SQLiteKnowledgeStore

_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".next",
    ".nuxt",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "tests",
    "tmp",
    "tmpbase",
}
_IGNORED_FILE_SUFFIXES = (".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx", ".test.py")
_SOURCE_EXTENSIONS = {
    ".py": ("source", "python"),
    ".js": ("source", "javascript"),
    ".jsx": ("source", "javascript"),
    ".ts": ("source", "typescript"),
    ".tsx": ("source", "typescript"),
    ".vue": ("source", "vue"),
}
_CONFIG_EXTENSIONS = {
    ".conf": ("config", None),
    ".cfg": ("config", None),
    ".env": ("config", "dotenv"),
    ".ini": ("config", "ini"),
    ".json": ("config", "json"),
    ".toml": ("config", "toml"),
    ".yaml": ("config", "yaml"),
    ".yml": ("config", "yaml"),
}
_CONFIG_FILENAMES = {
    "docker-compose.yaml": ("config", "yaml"),
    "docker-compose.yml": ("config", "yaml"),
    "dockerfile": ("config", "dockerfile"),
}
_SYMBOL_PATTERNS = [
    re.compile(r"^\s*async\s+def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"^\s*def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"^\s*class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"^\s*export\s+function\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"^\s*function\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"^\s*const\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*="),
]


@dataclass(frozen=True)
class KnowledgeBuildResult:
    indexed_documents: int
    indexed_chunks: int
    skipped_paths: list[str]


class KnowledgeIndexBuilder:
    def __init__(
        self,
        *,
        max_file_bytes: int = 50_000,
        chunk_size_lines: int = 60,
        chunk_overlap_lines: int = 8,
    ) -> None:
        self._max_file_bytes = max_file_bytes
        self._chunk_size_lines = max(1, chunk_size_lines)
        self._chunk_overlap_lines = max(0, min(chunk_overlap_lines, self._chunk_size_lines - 1))

    def build(self, *, task_id: str, repo_path: Path | str, db_path: Path | str) -> KnowledgeBuildResult:
        repo_root = Path(repo_path)
        store = SQLiteKnowledgeStore(db_path)
        store.initialize()

        indexed_documents = 0
        indexed_chunks = 0
        skipped_paths: list[str] = []

        file_paths, ignored_paths = self._iter_files(repo_root)
        skipped_paths.extend(ignored_paths)

        for file_path in file_paths:
            relative_path = file_path.relative_to(repo_root).as_posix()
            file_size = self._safe_file_size(file_path)
            if file_size is None or file_size > self._max_file_bytes:
                skipped_paths.append(relative_path)
                continue

            file_type, language = self._classify_file(file_path)
            if file_type is None:
                skipped_paths.append(relative_path)
                continue

            content = self._read_text(file_path)
            if not content.strip():
                skipped_paths.append(relative_path)
                continue

            document_id = store.upsert_document(
                KnowledgeDocumentRecord(
                    task_id=task_id,
                    path=relative_path,
                    file_type=file_type,
                    language=language,
                    size_bytes=file_size,
                    is_indexed=True,
                )
            )
            chunk_records = self._build_chunks(
                task_id=task_id,
                document_id=document_id,
                relative_path=relative_path,
                file_type=file_type,
                language=language,
                content=content,
            )
            store.insert_chunks(chunk_records)
            indexed_documents += 1
            indexed_chunks += len(chunk_records)

        return KnowledgeBuildResult(
            indexed_documents=indexed_documents,
            indexed_chunks=indexed_chunks,
            skipped_paths=sorted(skipped_paths),
        )

    def _iter_files(self, repo_root: Path) -> tuple[list[Path], list[str]]:
        files: list[Path] = []
        skipped: list[str] = []
        for dirpath, dirnames, filenames in os.walk(repo_root):
            nested_repo_dirs = [name for name in sorted(dirnames) if (Path(dirpath) / name / ".git").exists()]
            for dirname in nested_repo_dirs:
                nested_repo_path = Path(dirpath) / dirname
                for nested_file in nested_repo_path.rglob("*"):
                    if nested_file.is_file():
                        skipped.append(nested_file.relative_to(repo_root).as_posix())
            ignored_dirnames = [name for name in sorted(dirnames) if name in _IGNORED_DIRS]
            for dirname in ignored_dirnames:
                ignored_dir_path = Path(dirpath) / dirname
                for ignored_file in ignored_dir_path.rglob("*"):
                    if ignored_file.is_file():
                        skipped.append(ignored_file.relative_to(repo_root).as_posix())
            ignored_names = set(_IGNORED_DIRS) | set(nested_repo_dirs)
            dirnames[:] = [name for name in sorted(dirnames) if name not in ignored_names]
            for filename in sorted(filenames):
                file_path = Path(dirpath) / filename
                if any(file_path.name.endswith(suffix) for suffix in _IGNORED_FILE_SUFFIXES):
                    skipped.append(file_path.relative_to(repo_root).as_posix())
                    continue
                files.append(file_path)
        return files, skipped

    def _classify_file(self, file_path: Path) -> tuple[str | None, str | None]:
        name = file_path.name.lower()
        if name in _CONFIG_FILENAMES:
            return _CONFIG_FILENAMES[name]

        suffix = file_path.suffix.lower()
        if suffix in _SOURCE_EXTENSIONS:
            return _SOURCE_EXTENSIONS[suffix]
        if suffix in _CONFIG_EXTENSIONS:
            return _CONFIG_EXTENSIONS[suffix]
        return None, None

    def _safe_file_size(self, file_path: Path) -> int | None:
        try:
            return file_path.stat().st_size
        except OSError:
            return None

    def _read_text(self, file_path: Path) -> str:
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return file_path.read_text(encoding="utf-8", errors="ignore")

    def _build_chunks(
        self,
        *,
        task_id: str,
        document_id: int,
        relative_path: str,
        file_type: str,
        language: str | None,
        content: str,
    ) -> list[KnowledgeChunkRecord]:
        lines = content.splitlines()
        if not lines:
            lines = [content]
        step = max(1, self._chunk_size_lines - self._chunk_overlap_lines)
        chunks: list[KnowledgeChunkRecord] = []

        for chunk_index, start in enumerate(range(0, len(lines), step)):
            end = min(len(lines), start + self._chunk_size_lines)
            chunk_lines = lines[start:end]
            chunk_content = "\n".join(chunk_lines).strip()
            if not chunk_content:
                continue

            start_line = start + 1
            end_line = start + len(chunk_lines)
            symbol_name = self._find_symbol_name(chunk_lines)
            summary = self._build_summary(
                relative_path=relative_path,
                file_type=file_type,
                language=language,
                symbol_name=symbol_name,
                start_line=start_line,
                end_line=end_line,
                chunk_lines=chunk_lines,
            )
            chunks.append(
                KnowledgeChunkRecord(
                    task_id=task_id,
                    document_id=document_id,
                    chunk_index=chunk_index,
                    path=relative_path,
                    start_line=start_line,
                    end_line=end_line,
                    symbol_name=symbol_name,
                    chunk_kind="symbol" if symbol_name else file_type,
                    content=chunk_content + "\n",
                    summary=summary,
                    token_estimate=max(1, len(chunk_content) // 4),
                )
            )
            if end >= len(lines):
                break

        return chunks

    def _find_symbol_name(self, chunk_lines: list[str]) -> str | None:
        for line in chunk_lines:
            for pattern in _SYMBOL_PATTERNS:
                match = pattern.search(line)
                if match is not None:
                    return match.group("name")
        return None

    def _build_summary(
        self,
        *,
        relative_path: str,
        file_type: str,
        language: str | None,
        symbol_name: str | None,
        start_line: int,
        end_line: int,
        chunk_lines: list[str],
    ) -> str:
        first_code_line = next((line.strip() for line in chunk_lines if line.strip()), "")
        label = symbol_name or first_code_line[:80] or relative_path
        language_label = language or file_type
        return f"{relative_path}:{start_line}-{end_line} [{language_label}] {label}"
