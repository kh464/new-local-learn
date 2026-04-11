from __future__ import annotations

import re
from pathlib import Path

from app.services.code_graph.models import RetrievalCandidate
from app.services.code_graph.storage import CodeGraphStore


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")
_CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}")


class ExactRetriever:
    def __init__(self, *, graph_store: CodeGraphStore, chunk_retriever) -> None:
        self._graph_store = graph_store
        self._chunk_retriever = chunk_retriever

    def retrieve(
        self,
        *,
        task_id: str,
        db_path,
        question: str,
        normalized_question: str,
        target_entities: list[str],
        search_queries: list[str] | None = None,
        limit: int = 12,
    ) -> list[RetrievalCandidate]:
        del db_path
        candidates: list[RetrievalCandidate] = []
        seen: set[tuple[str, str]] = set()

        for entity in target_entities:
            candidates.extend(self.retrieve_by_symbol(task_id=task_id, symbol_name=entity, limit=limit))
            candidates.extend(self.retrieve_by_path(task_id=task_id, path=entity, limit=limit))

        for query in search_queries or []:
            candidates.extend(self.retrieve_by_summary_substring(task_id=task_id, term=query, limit=limit))

        fts_queries = self._build_fts_queries(
            [question, normalized_question, *(search_queries or []), *target_entities]
        )
        for fts_query in fts_queries:
            candidates.extend(self._graph_store.search_symbols_fts(task_id=task_id, query=fts_query, limit=limit))
            candidates.extend(self._graph_store.search_files_fts(task_id=task_id, query=fts_query, limit=limit))

        ranked: list[RetrievalCandidate] = []
        for candidate in candidates:
            key = (candidate.item_type, candidate.item_id)
            if key in seen:
                continue
            seen.add(key)
            ranked.append(candidate)
        ranked.sort(key=lambda item: (-item.score, item.item_type, item.item_id))
        return ranked[:limit]

    def retrieve_by_symbol(self, *, task_id: str, symbol_name: str, limit: int = 8) -> list[RetrievalCandidate]:
        normalized = symbol_name.strip().lower()
        if not normalized:
            return []
        results: list[RetrievalCandidate] = []
        for symbol in self._graph_store.list_symbols(task_id=task_id):
            direct_match = (
                symbol.name.lower() == normalized
                or symbol.qualified_name.lower() == normalized
                or normalized in symbol.qualified_name.lower()
            )
            if not direct_match:
                continue
            score = 160.0 if symbol.qualified_name.lower() == normalized else 130.0
            results.append(
                RetrievalCandidate(
                    task_id=task_id,
                    item_id=symbol.symbol_id,
                    item_type="symbol",
                    path=symbol.file_path,
                    symbol_id=symbol.symbol_id,
                    qualified_name=symbol.qualified_name,
                    score=score,
                    source="exact",
                    summary_zh=symbol.summary_zh,
                )
            )
        results.sort(key=lambda item: -item.score)
        return results[:limit]

    def retrieve_by_summary_substring(self, *, task_id: str, term: str, limit: int = 8) -> list[RetrievalCandidate]:
        normalized = term.strip()
        if len(normalized) < 2 or not _CHINESE_PATTERN.search(normalized):
            return []

        results: list[RetrievalCandidate] = []
        for symbol in self._graph_store.list_symbols(task_id=task_id):
            if normalized not in (symbol.summary_zh or ""):
                continue
            results.append(
                RetrievalCandidate(
                    task_id=task_id,
                    item_id=symbol.symbol_id,
                    item_type="symbol",
                    path=symbol.file_path,
                    symbol_id=symbol.symbol_id,
                    qualified_name=symbol.qualified_name,
                    score=110.0,
                    source="exact",
                    summary_zh=symbol.summary_zh,
                )
            )
        for file_node in self._graph_store.list_files(task_id=task_id):
            if normalized not in (file_node.summary_zh or ""):
                continue
            results.append(
                RetrievalCandidate(
                    task_id=task_id,
                    item_id=file_node.path,
                    item_type="file",
                    path=file_node.path,
                    symbol_id=None,
                    qualified_name=None,
                    score=100.0,
                    source="exact",
                    summary_zh=file_node.summary_zh,
                )
            )
        results.sort(key=lambda item: -item.score)
        return results[:limit]

    def _build_fts_queries(self, texts: list[str]) -> list[str]:
        queries: list[str] = []
        seen: set[str] = set()
        for text in texts:
            normalized = str(text or "").strip()
            if not normalized:
                continue

            token_text = re.sub(r"[./:-]+", " ", normalized)
            token_query = " OR ".join(dict.fromkeys(token for token in _TOKEN_PATTERN.findall(token_text) if token))
            if token_query and token_query not in seen:
                seen.add(token_query)
                queries.append(token_query)

            for phrase in _CHINESE_PATTERN.findall(normalized):
                if phrase in seen:
                    continue
                seen.add(phrase)
                queries.append(phrase)
        return queries

    def retrieve_by_path(self, *, task_id: str, path: str, limit: int = 8) -> list[RetrievalCandidate]:
        normalized = path.strip().lower()
        if not normalized:
            return []
        results: list[RetrievalCandidate] = []
        for file_node in self._graph_store.list_files(task_id=task_id):
            file_path = file_node.path.lower()
            basename = Path(file_node.path).name.lower()
            if normalized not in {file_path, basename} and normalized not in file_path:
                continue
            score = 150.0 if normalized == file_path else 120.0
            results.append(
                RetrievalCandidate(
                    task_id=task_id,
                    item_id=file_node.path,
                    item_type="file",
                    path=file_node.path,
                    symbol_id=None,
                    qualified_name=None,
                    score=score,
                    source="exact",
                    summary_zh=file_node.summary_zh,
                )
            )
        results.sort(key=lambda item: -item.score)
        return results[:limit]
