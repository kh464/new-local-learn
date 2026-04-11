from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.services.code_graph.adapters.base import ExtractionResult
from app.services.code_graph.adapters.python import PythonCodeGraphAdapter
from app.services.code_graph.storage import CodeGraphStore
from app.services.code_graph.summary_builder import CodeSummaryBuilder


_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".pytest_cache",
    "__pycache__",
    "artifacts",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "tests",
    "tmp",
    "tmpbase",
}


@dataclass(frozen=True)
class CodeGraphBuildResult:
    files_count: int
    symbols_count: int
    edges_count: int
    unresolved_calls_count: int
    skipped_paths: list[str]


class CodeGraphBuildPipeline:
    def __init__(self, *, adapters: list | None = None, summary_builder: CodeSummaryBuilder | None = None) -> None:
        self._adapters = adapters or [PythonCodeGraphAdapter()]
        self._summary_builder = summary_builder or CodeSummaryBuilder()

    def build(self, *, task_id: str, repo_root: Path | str, db_path: Path | str) -> CodeGraphBuildResult:
        repo_root = Path(repo_root)
        store = CodeGraphStore(db_path)
        store.initialize()

        aggregate = ExtractionResult()
        skipped_paths: list[str] = []

        for dirpath, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [name for name in sorted(dirnames) if name not in _IGNORED_DIRS]
            for filename in sorted(filenames):
                file_path = Path(dirpath) / filename
                adapter = next((item for item in self._adapters if item.supports(file_path)), None)
                if adapter is None:
                    skipped_paths.append(file_path.relative_to(repo_root).as_posix())
                    continue
                result = adapter.extract_file(task_id=task_id, repo_root=repo_root, file_path=file_path)
                aggregate = ExtractionResult(
                    files=[*aggregate.files, *result.files],
                    symbols=[*aggregate.symbols, *result.symbols],
                    edges=[*aggregate.edges, *result.edges],
                    unresolved_calls=[*aggregate.unresolved_calls, *result.unresolved_calls],
                )

        store.upsert_files(aggregate.files)
        store.upsert_symbols(aggregate.symbols)
        store.insert_edges(aggregate.edges)
        store.insert_unresolved_calls(aggregate.unresolved_calls)
        self._populate_summaries(task_id=task_id, store=store)

        return CodeGraphBuildResult(
            files_count=len(aggregate.files),
            symbols_count=len(aggregate.symbols),
            edges_count=len(aggregate.edges),
            unresolved_calls_count=len(aggregate.unresolved_calls),
            skipped_paths=sorted(skipped_paths),
        )

    def _populate_summaries(self, *, task_id: str, store: CodeGraphStore) -> None:
        files = store.list_files(task_id=task_id)
        symbols = store.list_symbols(task_id=task_id)
        symbols_by_file: dict[str, list] = {}
        for symbol in symbols:
            symbols_by_file.setdefault(symbol.file_path, []).append(symbol)

        for file_node in files:
            summary = self._summary_builder.build_file_summary(
                file_node=file_node,
                symbols=symbols_by_file.get(file_node.path, []),
            )
            store.update_file_summary(task_id=task_id, path=file_node.path, summary_zh=summary)

        for symbol in symbols:
            summary = self._summary_builder.build_symbol_summary(
                symbol=symbol,
                outgoing_edges=store.list_out_edges(task_id=task_id, symbol_id=symbol.symbol_id),
            )
            store.update_symbol_summary(task_id=task_id, symbol_id=symbol.symbol_id, summary_zh=summary)
