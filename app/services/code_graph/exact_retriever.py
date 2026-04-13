from __future__ import annotations

import re
from pathlib import Path

from app.services.code_graph.models import RetrievalCandidate
from app.services.code_graph.storage import CodeGraphStore


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")
_CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}")
_PATHLIKE_QUERY_PATTERN = re.compile(r"(?:/|\\|\.(?:py|ts|tsx|js|jsx|vue|json|ya?ml|toml|md)$)", re.IGNORECASE)
_SPECIAL_PATH_QUERIES = {
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "dockerfile",
    "chart.yaml",
    "values.yaml",
    "templates",
    "ops/helm",
}
_PLANNING_KEYWORDS = (
    "知识库",
    "认知图",
    "任务队列",
    "分析任务",
    "任务提交",
    "提交任务",
    "调用链",
    "链路",
    "健康检查",
    "前端",
    "后端",
    "页面入口",
    "入口组件",
    "docker",
    "compose",
    "helm",
    "templates",
    "app.state",
    "create_app",
    "health",
    "retriever",
    "repo_map",
)


class ExactRetriever:
    def __init__(self, *, graph_store: CodeGraphStore, chunk_retriever, repo_root: Path | str | None = None) -> None:
        self._graph_store = graph_store
        self._chunk_retriever = chunk_retriever
        self._repo_root = Path(repo_root).resolve() if repo_root is not None else None
        self._repo_files_cache: list[str] | None = None

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
            candidates.extend(self.retrieve_by_repo_path(task_id=task_id, path=entity, limit=limit))

        for query in search_queries or []:
            candidates.extend(self.retrieve_by_symbol(task_id=task_id, symbol_name=query, limit=limit))
            candidates.extend(self.retrieve_by_path(task_id=task_id, path=query, limit=limit))
            candidates.extend(self.retrieve_by_repo_path(task_id=task_id, path=query, limit=limit))
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
            ranked.append(
                RetrievalCandidate(
                    task_id=candidate.task_id,
                    item_id=candidate.item_id,
                    item_type=candidate.item_type,
                    path=candidate.path,
                    symbol_id=candidate.symbol_id,
                    qualified_name=candidate.qualified_name,
                    score=(
                        candidate.score
                        + self._explicit_query_path_boost(
                            candidate=candidate,
                            queries=[*target_entities, *(search_queries or [])],
                        )
                        + self._question_anchor_boost(
                            candidate=candidate,
                            question_text=" ".join(part for part in (question, normalized_question) if part),
                        )
                    ),
                    source=candidate.source,
                    summary_zh=candidate.summary_zh,
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.item_type, item.item_id))
        return ranked[:limit]

    def build_planning_context(self, *, task_id: str, question: str, limit: int = 6) -> dict[str, list[dict[str, object]]]:
        terms = self._extract_planning_terms(question)
        files = self._graph_store.list_files(task_id=task_id)
        symbols = self._graph_store.list_symbols(task_id=task_id)
        symbols_by_id = {symbol.symbol_id: symbol for symbol in symbols}

        ranked_files: list[tuple[float, object]] = []
        for file_node in files:
            score = self._score_file_hint(file_node=file_node, terms=terms)
            if score <= 0:
                continue
            ranked_files.append((score, file_node))

        ranked_symbols: list[tuple[float, object]] = []
        for symbol in symbols:
            score = self._score_symbol_hint(symbol=symbol, terms=terms)
            if score <= 0:
                continue
            ranked_symbols.append((score, symbol))

        if ranked_files or ranked_symbols:
            ranked_files = self._extend_with_fallback_files(ranked_files=ranked_files, files=files, limit=max(limit, 1))
            ranked_symbols = self._extend_with_fallback_symbols(
                ranked_symbols=ranked_symbols,
                symbols=symbols,
                limit=max(limit, 1),
            )
        if not ranked_symbols and ranked_files:
            ranked_symbols = self._derive_symbols_from_ranked_files(
                task_id=task_id,
                ranked_files=ranked_files,
                limit=max(limit, 1),
            )

        ranked_files.sort(key=lambda item: (-item[0], item[1].path))
        ranked_symbols.sort(key=lambda item: (-item[0], item[1].file_path, item[1].start_line))

        relation_hints = self._build_relation_hints(
            task_id=task_id,
            ranked_symbols=[symbol for _, symbol in ranked_symbols[: max(limit, 1)]],
            symbols_by_id=symbols_by_id,
        )
        keyword_hints = self._build_keyword_hints(
            ranked_files=[file_node for _, file_node in ranked_files[: max(limit, 1)]],
            ranked_symbols=[symbol for _, symbol in ranked_symbols[: max(limit, 1)]],
        )

        return {
            "file_hints": [
                {
                    "path": file_node.path,
                    "summary_zh": file_node.summary_zh,
                    "entry_role": file_node.entry_role,
                    "keywords_zh": list(file_node.keywords_zh),
                }
                for _, file_node in ranked_files[: max(limit, 1)]
            ],
            "symbol_hints": [
                {
                    "qualified_name": symbol.qualified_name,
                    "file_path": symbol.file_path,
                    "symbol_kind": symbol.symbol_kind,
                    "summary_zh": symbol.summary_zh,
                }
                for _, symbol in ranked_symbols[: max(limit, 1)]
            ],
            "relation_hints": relation_hints,
            "keyword_hints": keyword_hints,
        }

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

    def _extract_planning_terms(self, question: str) -> list[str]:
        normalized = question.strip().lower()
        terms: list[str] = []
        for keyword in _PLANNING_KEYWORDS:
            lowered = keyword.lower()
            if lowered in normalized:
                terms.append(lowered)
        for token in _TOKEN_PATTERN.findall(question):
            lowered = token.strip().lower()
            if len(lowered) >= 2:
                terms.append(lowered)
        for phrase in _CHINESE_PATTERN.findall(question):
            lowered = phrase.strip().lower()
            if 2 <= len(lowered) <= 8:
                terms.append(lowered)
        deduped: list[str] = []
        seen: set[str] = set()
        for term in terms:
            if term in seen:
                continue
            seen.add(term)
            deduped.append(term)
        return deduped

    def _score_file_hint(self, *, file_node, terms: list[str]) -> float:
        text = " ".join(
            [
                file_node.path,
                file_node.summary_zh,
                file_node.responsibility_zh,
                file_node.upstream_zh,
                file_node.downstream_zh,
                *list(file_node.keywords_zh),
            ]
        ).lower()
        score = 0.0
        for term in terms:
            if term in file_node.path.lower():
                score += 5.0
            elif term in text:
                score += 3.0
        return score

    def _score_symbol_hint(self, *, symbol, terms: list[str]) -> float:
        text = " ".join(
            [
                symbol.name,
                symbol.qualified_name,
                symbol.summary_zh,
                symbol.input_output_zh,
                symbol.side_effects_zh,
                symbol.call_targets_zh,
                symbol.callers_zh,
            ]
        ).lower()
        kind_boost = {"route": 4.0, "class": 3.0, "method": 2.5, "function": 2.0}.get(symbol.symbol_kind, 1.0)
        score = 0.0
        for term in terms:
            if term in symbol.qualified_name.lower() or term == symbol.name.lower():
                score += 5.0 + kind_boost
            elif term in text:
                score += 3.0 + min(kind_boost, 1.5)
        return score

    def _build_relation_hints(self, *, task_id: str, ranked_symbols: list, symbols_by_id: dict[str, object]) -> list[dict[str, object]]:
        relation_hints: list[dict[str, object]] = []
        seen: set[tuple[str, str, str]] = set()
        for symbol in ranked_symbols:
            for edge in self._graph_store.list_out_edges(task_id=task_id, symbol_id=symbol.symbol_id):
                if edge.edge_kind not in {"calls", "routes_to"}:
                    continue
                target = symbols_by_id.get(edge.to_symbol_id)
                if target is None:
                    continue
                key = (edge.edge_kind, symbol.symbol_id, target.symbol_id)
                if key in seen:
                    continue
                seen.add(key)
                relation_hints.append(
                    {
                        "edge_kind": edge.edge_kind,
                        "from_qualified_name": symbol.qualified_name,
                        "to_qualified_name": target.qualified_name,
                        "source_path": edge.source_path,
                    }
                )
                if len(relation_hints) >= 6:
                    return relation_hints
        return relation_hints

    def _build_keyword_hints(self, *, ranked_files: list, ranked_symbols: list) -> list[str]:
        keywords: list[str] = []
        for file_node in ranked_files:
            keywords.extend(list(getattr(file_node, "keywords_zh", []) or []))
        for symbol in ranked_symbols:
            summary = str(getattr(symbol, "summary_zh", "") or "")
            for phrase in _CHINESE_PATTERN.findall(summary):
                if 2 <= len(phrase) <= 8:
                    keywords.append(phrase)
        deduped: list[str] = []
        seen: set[str] = set()
        for keyword in keywords:
            normalized = str(keyword).strip()
            if len(normalized) < 2:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped[:8]

    def _extend_with_fallback_files(self, *, ranked_files: list[tuple[float, object]], files: list, limit: int) -> list[tuple[float, object]]:
        seen_paths = {file_node.path for _, file_node in ranked_files}
        extended = list(ranked_files)
        for file_node in files:
            if file_node.path in seen_paths:
                continue
            if not (file_node.entry_role or file_node.summary_zh):
                continue
            extended.append((1.0 if file_node.entry_role else 0.2, file_node))
            seen_paths.add(file_node.path)
            if len(extended) >= limit:
                break
        return extended

    def _extend_with_fallback_symbols(
        self,
        *,
        ranked_symbols: list[tuple[float, object]],
        symbols: list,
        limit: int,
    ) -> list[tuple[float, object]]:
        seen_ids = {symbol.symbol_id for _, symbol in ranked_symbols}
        extended = list(ranked_symbols)
        for symbol in symbols:
            if symbol.symbol_id in seen_ids:
                continue
            if not symbol.summary_zh:
                continue
            base_score = {"route": 1.0, "class": 0.8, "method": 0.6, "function": 0.5}.get(symbol.symbol_kind, 0.1)
            extended.append((base_score, symbol))
            seen_ids.add(symbol.symbol_id)
            if len(extended) >= limit:
                break
        return extended

    def _derive_symbols_from_ranked_files(
        self,
        *,
        task_id: str,
        ranked_files: list[tuple[float, object]],
        limit: int,
    ) -> list[tuple[float, object]]:
        derived: list[tuple[float, object]] = []
        seen_ids: set[str] = set()
        for score, file_node in ranked_files:
            for symbol in self._graph_store.list_symbols(task_id=task_id, file_path=file_node.path):
                if symbol.symbol_id in seen_ids:
                    continue
                seen_ids.add(symbol.symbol_id)
                derived.append((max(score - 1.0, 0.1), symbol))
                if len(derived) >= limit:
                    return derived
        return derived

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

    def retrieve_by_repo_path(self, *, task_id: str, path: str, limit: int = 8) -> list[RetrievalCandidate]:
        normalized = path.strip().replace("\\", "/").lower()
        if not normalized or self._repo_root is None:
            return []
        results: list[RetrievalCandidate] = []
        for repo_path in self._list_repo_files():
            repo_path_lower = repo_path.lower()
            basename = Path(repo_path).name.lower()
            if normalized not in {repo_path_lower, basename} and normalized not in repo_path_lower:
                continue
            score = 145.0 if normalized == repo_path_lower else 118.0
            results.append(
                RetrievalCandidate(
                    task_id=task_id,
                    item_id=repo_path,
                    item_type="file",
                    path=repo_path,
                    symbol_id=None,
                    qualified_name=None,
                    score=score,
                    source="exact",
                    summary_zh="",
                )
            )
        results.sort(key=lambda item: -item.score)
        return results[:limit]

    def _list_repo_files(self) -> list[str]:
        if self._repo_root is None:
            return []
        if self._repo_files_cache is not None:
            return self._repo_files_cache
        files: list[str] = []
        for path in self._repo_root.rglob("*"):
            if not path.is_file():
                continue
            try:
                relative = path.resolve().relative_to(self._repo_root)
            except ValueError:
                continue
            files.append(relative.as_posix())
        self._repo_files_cache = sorted(files)
        return self._repo_files_cache

    def _explicit_query_path_boost(self, *, candidate: RetrievalCandidate, queries: list[str]) -> float:
        path = str(candidate.path or "").replace("\\", "/").lower()
        if not path:
            return 0.0
        basename = Path(path).name.lower()
        score = 0.0
        for query in queries:
            normalized = str(query or "").strip().replace("\\", "/").lower()
            if len(normalized) < 2 or not self._looks_pathlike_query(normalized):
                continue
            score += self._score_path_query_match(path=path, basename=basename, query=normalized)
        return score

    def _looks_pathlike_query(self, query: str) -> bool:
        return bool(_PATHLIKE_QUERY_PATTERN.search(query) or query in _SPECIAL_PATH_QUERIES)

    def _score_path_query_match(self, *, path: str, basename: str, query: str) -> float:
        if query == path:
            return 120.0
        if query == basename:
            return 100.0
        if "/" in query and path.startswith(query.rstrip("/") + "/"):
            return 95.0
        if "/" in query and query in path:
            return 75.0
        if query == "templates" and "/templates/" in f"/{path}":
            return 85.0
        if query in basename and len(query) >= 5:
            return 40.0
        return 0.0

    def _question_anchor_boost(self, *, candidate: RetrievalCandidate, question_text: str) -> float:
        normalized_question = str(question_text or "").lower()
        path = str(candidate.path or "").replace("\\", "/").lower()
        basename = Path(path).name.lower()
        score = 0.0

        if self._is_docker_compose_question(normalized_question):
            if basename in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
                score += 180.0
            elif basename == "dockerfile":
                score += 120.0
            elif "docker" in path:
                score += 18.0

        if self._is_helm_templates_question(normalized_question):
            if "/templates/" in f"/{path}":
                score += 180.0
            elif path.startswith("ops/helm/"):
                score += 120.0
            elif basename in {"chart.yaml", "values.yaml"}:
                score += 100.0

        return score

    def _is_docker_compose_question(self, question_text: str) -> bool:
        return "docker compose" in question_text or "docker-compose" in question_text

    def _is_helm_templates_question(self, question_text: str) -> bool:
        return "helm" in question_text or "chart" in question_text or "templates" in question_text
