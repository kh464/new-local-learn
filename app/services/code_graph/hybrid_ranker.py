from __future__ import annotations

from dataclasses import replace

from app.services.code_graph.models import RetrievalCandidate


class HybridRanker:
    def rank(
        self,
        *,
        exact_hits: list[RetrievalCandidate],
        semantic_hits: list[RetrievalCandidate],
        question_type: str | None = None,
        search_queries: list[str] | None = None,
        limit: int = 10,
    ) -> list[RetrievalCandidate]:
        merged: dict[tuple[str, str], RetrievalCandidate] = {}
        for candidate in exact_hits:
            merged[(candidate.item_type, candidate.item_id)] = candidate
        for candidate in semantic_hits:
            key = (candidate.item_type, candidate.item_id)
            existing = merged.get(key)
            if existing is None:
                merged[key] = candidate
                continue
            merged[key] = RetrievalCandidate(
                task_id=existing.task_id,
                item_id=existing.item_id,
                item_type=existing.item_type,
                path=existing.path or candidate.path,
                symbol_id=existing.symbol_id or candidate.symbol_id,
                qualified_name=existing.qualified_name or candidate.qualified_name,
                score=existing.score + candidate.score + 40.0,
                source="hybrid",
                summary_zh=existing.summary_zh or candidate.summary_zh,
            )

        adjusted = [
            replace(
                candidate,
                score=candidate.score + self._contextual_score_adjustment(
                    candidate=candidate,
                    question_type=question_type,
                    search_queries=search_queries or [],
                ),
            )
            for candidate in merged.values()
        ]
        ranked = sorted(
            adjusted,
            key=lambda item: (-item.score, 0 if item.item_type == "symbol" else 1, item.item_id),
        )
        return ranked[:limit]

    def _contextual_score_adjustment(
        self,
        *,
        candidate: RetrievalCandidate,
        question_type: str | None,
        search_queries: list[str],
    ) -> float:
        if question_type != "architecture_explanation":
            return 0.0

        text = " ".join(
            part.lower()
            for part in (
                candidate.path or "",
                candidate.qualified_name or "",
                candidate.item_id or "",
                candidate.summary_zh or "",
            )
            if part
        )
        score = 0.0

        if candidate.item_id.startswith(("route:", "function:", "method:")):
            score += 18.0
        elif candidate.item_id.startswith("class:"):
            score -= 4.0

        if "/schemas.py" in text or ".schemas." in text:
            score -= 28.0
        if "/config.py" in text or ".config." in text:
            score -= 18.0
        if "alembic/" in text or "migration" in text or ".upgrade" in text or ".downgrade" in text:
            score -= 36.0

        symbol_text = " ".join(part.lower() for part in (candidate.qualified_name or "", candidate.item_id or "") if part)
        for query in search_queries:
            normalized = str(query or "").strip().lower()
            if len(normalized) < 2:
                continue
            if "/" in normalized or normalized.endswith(".py"):
                score += self._path_query_match_score(candidate=candidate, query=normalized)
                continue
            if normalized in symbol_text:
                score += self._symbol_query_match_score(normalized)

        score += self._utility_symbol_penalty(candidate)

        return score

    def _path_query_match_score(self, *, candidate: RetrievalCandidate, query: str) -> float:
        path = (candidate.path or "").lower()
        if not path:
            return 0.0
        if candidate.item_type == "file" and path == query:
            return 10.0
        if path == query:
            return 3.0
        if query in path:
            return 1.0
        return 0.0

    def _symbol_query_match_score(self, query: str) -> float:
        if query == "enqueue":
            return 22.0
        if query == "submit":
            return 18.0
        if query in {"_worker_loop", "_execute"}:
            return 16.0
        return 8.0

    def _utility_symbol_penalty(self, candidate: RetrievalCandidate) -> float:
        qualified_name = (candidate.qualified_name or "").strip()
        if not qualified_name:
            return 0.0
        leaf_name = qualified_name.split(".")[-1].lower()
        if leaf_name.startswith("__"):
            return -16.0
        if leaf_name in {"_emit", "_public_record"}:
            return -12.0
        if leaf_name in {"get", "list_tasks", "list_dead_letters", "snapshot", "shutdown"}:
            return -8.0
        return 0.0
