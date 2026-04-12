from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from app.services.code_graph.models import CodeFileNode, CodeSymbolNode
from app.services.code_graph.storage import CodeGraphStore
from app.services.code_graph.summary_builder import CodeSummaryBuilder


class SummaryGenerationService:
    def __init__(
        self,
        *,
        graph_store: CodeGraphStore | None = None,
        llm_summary_service=None,
        summary_builder: CodeSummaryBuilder | None = None,
        max_snippet_chars: int = 1200,
        max_llm_file_summaries: int | None = 8,
        max_llm_symbol_summaries: int | None = 24,
        max_llm_parallelism: int = 4,
    ) -> None:
        self._graph_store = graph_store
        self._llm_summary_service = llm_summary_service
        self._summary_builder = summary_builder or CodeSummaryBuilder()
        self._max_snippet_chars = max(200, max_snippet_chars)
        self._max_llm_file_summaries = max_llm_file_summaries
        self._max_llm_symbol_summaries = max_llm_symbol_summaries
        self._max_llm_parallelism = max(1, max_llm_parallelism)

    async def build(self, *, task_id: str, db_path, repo_root) -> None:
        store = self._graph_store or CodeGraphStore(db_path)
        store.initialize()
        repo_root = Path(repo_root)

        files = store.list_files(task_id=task_id)
        symbols = store.list_symbols(task_id=task_id)
        symbols_by_file: dict[str, list[CodeSymbolNode]] = {}
        for symbol in symbols:
            symbols_by_file.setdefault(symbol.file_path, []).append(symbol)
        symbols_by_id = {symbol.symbol_id: symbol for symbol in symbols}
        llm_file_paths = self._select_llm_file_paths(files=files, symbols_by_file=symbols_by_file)
        llm_symbol_ids = self._select_llm_symbol_ids(symbols=symbols, files_by_path={item.path: item for item in files})

        file_tasks = [
            self._summarize_file_node(
                file_node=file_node,
                symbols=symbols_by_file.get(file_node.path, []),
                repo_root=repo_root,
                use_llm=file_node.path in llm_file_paths,
            )
            for file_node in files
        ]
        updated_files = list(await self._gather_with_limit(file_tasks))
        store.upsert_files(updated_files)

        symbol_tasks = [
            self._summarize_symbol_node(
                symbol=symbol,
                repo_root=repo_root,
                outgoing_edges=store.list_out_edges(task_id=task_id, symbol_id=symbol.symbol_id),
                incoming_edges=store.list_in_edges(task_id=task_id, symbol_id=symbol.symbol_id),
                symbols_by_id=symbols_by_id,
                use_llm=symbol.symbol_id in llm_symbol_ids,
            )
            for symbol in symbols
        ]
        updated_symbols = list(await self._gather_with_limit(symbol_tasks))
        store.upsert_symbols(updated_symbols)

    async def _summarize_file_node(
        self,
        *,
        file_node: CodeFileNode,
        symbols: list[CodeSymbolNode],
        repo_root: Path,
        use_llm: bool,
    ) -> CodeFileNode:
        payload, source = await self._build_file_payload(
            file_node=file_node,
            symbols=symbols,
            repo_root=repo_root,
            use_llm=use_llm,
        )
        return replace(
            file_node,
            summary_zh=str(payload.get("summary_zh", file_node.summary_zh)),
            responsibility_zh=str(payload.get("responsibility_zh", "")),
            upstream_zh=str(payload.get("upstream_zh", "")),
            downstream_zh=str(payload.get("downstream_zh", "")),
            keywords_zh=list(payload.get("keywords_zh", [])),
            summary_source=source,
            summary_version=1 if source == "llm" else 0,
            summary_confidence=str(payload.get("summary_confidence", "low")),
        )

    async def _summarize_symbol_node(
        self,
        *,
        symbol: CodeSymbolNode,
        repo_root: Path,
        outgoing_edges,
        incoming_edges,
        symbols_by_id: dict[str, CodeSymbolNode],
        use_llm: bool,
    ) -> CodeSymbolNode:
        payload, source = await self._build_symbol_payload(
            symbol=symbol,
            repo_root=repo_root,
            outgoing_edges=outgoing_edges,
            incoming_edges=incoming_edges,
            symbols_by_id=symbols_by_id,
            use_llm=use_llm,
        )
        return replace(
            symbol,
            summary_zh=str(payload.get("summary_zh", symbol.summary_zh)),
            input_output_zh=str(payload.get("input_output_zh", "")),
            side_effects_zh=str(payload.get("side_effects_zh", "")),
            call_targets_zh=str(payload.get("call_targets_zh", "")),
            callers_zh=str(payload.get("callers_zh", "")),
            summary_source=source,
            summary_version=1 if source == "llm" else 0,
            summary_confidence=str(payload.get("summary_confidence", "low")),
        )

    async def _build_file_payload(
        self,
        *,
        file_node: CodeFileNode,
        symbols: list[CodeSymbolNode],
        repo_root: Path,
        use_llm: bool,
    ) -> tuple[dict[str, object], str]:
        evidence = {
            "path": file_node.path,
            "entry_role": file_node.entry_role,
            "symbol_facts": [f"{symbol.symbol_kind}:{symbol.qualified_name}" for symbol in symbols[:20]],
            "code_snippets": [self._read_file_snippet(repo_root, file_node.path)],
        }
        if use_llm and self._llm_summary_service is not None:
            try:
                payload = await self._llm_summary_service.generate_file_summary(
                    file_path=file_node.path,
                    language=file_node.language,
                    evidence=evidence,
                )
                return self._to_dict(payload), "llm"
            except Exception:
                pass
        return self._summary_builder.build_file_payload(file_node=file_node, symbols=symbols), "rule"

    async def _build_symbol_payload(
        self,
        *,
        symbol: CodeSymbolNode,
        repo_root: Path,
        outgoing_edges,
        incoming_edges,
        symbols_by_id: dict[str, CodeSymbolNode],
        use_llm: bool,
    ) -> tuple[dict[str, object], str]:
        evidence = {
            "qualified_name": symbol.qualified_name,
            "signature": symbol.signature,
            "code_snippet": self._read_symbol_snippet(repo_root, symbol),
            "call_targets": [
                symbols_by_id[edge.to_symbol_id].qualified_name
                for edge in outgoing_edges
                if edge.edge_kind == "calls" and edge.to_symbol_id in symbols_by_id
            ],
            "callers": [
                symbols_by_id[edge.from_symbol_id].qualified_name
                for edge in incoming_edges
                if edge.edge_kind == "calls" and edge.from_symbol_id in symbols_by_id
            ],
        }
        if use_llm and self._llm_summary_service is not None:
            try:
                payload = await self._llm_summary_service.generate_symbol_summary(
                    symbol_name=symbol.qualified_name,
                    symbol_kind=symbol.symbol_kind,
                    file_path=symbol.file_path,
                    language=symbol.language,
                    evidence=evidence,
                )
                return self._to_dict(payload), "llm"
            except Exception:
                pass
        return (
            self._summary_builder.build_symbol_payload(
                symbol=symbol,
                outgoing_edges=outgoing_edges,
                incoming_edges=incoming_edges,
            ),
            "rule",
        )

    def _read_file_snippet(self, repo_root: Path, relative_path: str) -> str:
        file_path = repo_root / relative_path
        if not file_path.exists():
            return ""
        return self._clip_text(file_path.read_text(encoding="utf-8", errors="ignore"))

    def _read_symbol_snippet(self, repo_root: Path, symbol: CodeSymbolNode) -> str:
        file_path = repo_root / symbol.file_path
        if not file_path.exists():
            return ""
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        start = max(symbol.start_line - 1, 0)
        end = max(symbol.end_line, start)
        return self._clip_text("\n".join(lines[start:end]))

    def _clip_text(self, text: str) -> str:
        if len(text) <= self._max_snippet_chars:
            return text
        return text[: self._max_snippet_chars]

    def _to_dict(self, payload) -> dict[str, object]:
        if hasattr(payload, "model_dump"):
            return payload.model_dump()
        if isinstance(payload, dict):
            return payload
        return dict(vars(payload))

    async def _gather_with_limit(self, coroutines: list):
        semaphore = asyncio.Semaphore(self._max_llm_parallelism)

        async def run(coro):
            async with semaphore:
                return await coro

        return await asyncio.gather(*(run(coro) for coro in coroutines))

    def _select_llm_file_paths(
        self,
        *,
        files: list[CodeFileNode],
        symbols_by_file: dict[str, list[CodeSymbolNode]],
    ) -> set[str]:
        if self._llm_summary_service is None or self._max_llm_file_summaries == 0:
            return set()
        ranked = sorted(
            files,
            key=lambda item: (
                0 if item.entry_role else 1,
                -sum(1 for symbol in symbols_by_file.get(item.path, []) if symbol.symbol_kind == "route"),
                -len(symbols_by_file.get(item.path, [])),
                item.path,
            ),
        )
        limit = len(ranked) if self._max_llm_file_summaries is None else max(0, self._max_llm_file_summaries)
        return {item.path for item in ranked[:limit]}

    def _select_llm_symbol_ids(
        self,
        *,
        symbols: list[CodeSymbolNode],
        files_by_path: dict[str, CodeFileNode],
    ) -> set[str]:
        if self._llm_summary_service is None or self._max_llm_symbol_summaries == 0:
            return set()
        kind_priority = {"route": 0, "class": 1, "method": 2, "function": 3}
        ranked = sorted(
            symbols,
            key=lambda item: (
                0 if files_by_path.get(item.file_path) is not None and files_by_path[item.file_path].entry_role else 1,
                kind_priority.get(item.symbol_kind, 9),
                item.file_path,
                item.start_line,
                item.qualified_name,
            ),
        )
        limit = len(ranked) if self._max_llm_symbol_summaries is None else max(0, self._max_llm_symbol_summaries)
        return {item.symbol_id for item in ranked[:limit]}
