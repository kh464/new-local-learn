from __future__ import annotations

from app.services.code_graph.models import RetrievalCandidate


class HybridRanker:
    def rank(
        self,
        *,
        exact_hits: list[RetrievalCandidate],
        semantic_hits: list[RetrievalCandidate],
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

        ranked = sorted(
            merged.values(),
            key=lambda item: (-item.score, 0 if item.item_type == "symbol" else 1, item.item_id),
        )
        return ranked[:limit]
