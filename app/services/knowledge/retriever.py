from __future__ import annotations

import re
from pathlib import Path

from app.storage.knowledge_store import KnowledgeSearchResult, SQLiteKnowledgeStore

_WORD_PATTERN = re.compile(r"[A-Za-z0-9_./-]+")
_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_BACKEND_KEYWORDS = ("后端", "接口", "路由", "服务", "入口", "api")
_FRONTEND_KEYWORDS = ("前端", "页面", "组件", "界面", "调用", "ui")
_CONFIG_KEYWORDS = ("部署", "docker", "compose", "环境", "配置", "k8s", "yaml")
_ENTRY_FILES = {"main.py", "app.py", "App.vue", "App.tsx", "App.jsx", "docker-compose.yml", "Dockerfile"}
_QUESTION_TYPE_TERMS = {
    "backend": ["fastapi", "router", "route", "api", "app", "main"],
    "frontend": ["fetch", "axios", "component", "page", "view", "app", "frontend", "vue", "react"],
    "config": ["docker", "compose", "yaml", "service", "env", "deploy"],
}


class KnowledgeRetriever:
    def __init__(self, *, candidate_limit: int = 12) -> None:
        self._candidate_limit = max(1, candidate_limit)

    def retrieve(
        self,
        *,
        task_id: str,
        db_path: Path | str,
        question: str,
        limit: int = 6,
    ) -> list[KnowledgeSearchResult]:
        normalized_question = question.strip()
        if not normalized_question:
            return []

        question_type = self._classify_question(normalized_question)
        query_tokens = self._build_query_tokens(normalized_question, question_type)
        if not query_tokens:
            query_tokens = list(_QUESTION_TYPE_TERMS.get(question_type, []))
        if not query_tokens:
            return []

        return self._retrieve_from_tokens(
            task_id=task_id,
            db_path=db_path,
            question=normalized_question,
            query_tokens=query_tokens,
            question_type=question_type,
            limit=limit,
        )

    def retrieve_by_symbol(
        self,
        *,
        task_id: str,
        db_path: Path | str,
        symbol: str,
        limit: int = 6,
    ) -> list[KnowledgeSearchResult]:
        normalized_symbol = symbol.strip()
        if not normalized_symbol:
            return []
        query_tokens = self._build_query_tokens(normalized_symbol, "general") or [normalized_symbol.lower()]
        return self._retrieve_from_tokens(
            task_id=task_id,
            db_path=db_path,
            question=normalized_symbol,
            query_tokens=query_tokens,
            question_type="general",
            limit=limit,
        )

    def retrieve_by_path(
        self,
        *,
        task_id: str,
        db_path: Path | str,
        path: str,
        limit: int = 6,
    ) -> list[KnowledgeSearchResult]:
        normalized_path = path.strip()
        if not normalized_path:
            return []
        query_tokens = self._build_query_tokens(normalized_path, "general")
        if not query_tokens:
            query_tokens = [Path(normalized_path).name.lower()]
        results = self._retrieve_from_tokens(
            task_id=task_id,
            db_path=db_path,
            question=normalized_path,
            query_tokens=query_tokens,
            question_type="general",
            limit=max(limit, 1) * 2,
        )
        exact_matches = [result for result in results if result.path == normalized_path]
        if exact_matches:
            return exact_matches[: max(limit, 1)]
        return results[: max(limit, 1)]

    def _classify_question(self, question: str) -> str:
        lowered = question.lower()
        if any(keyword in question for keyword in _FRONTEND_KEYWORDS) or "frontend" in lowered:
            return "frontend"
        if any(keyword in question for keyword in _BACKEND_KEYWORDS) or "backend" in lowered:
            return "backend"
        if any(keyword in question for keyword in _CONFIG_KEYWORDS):
            return "config"
        return "general"

    def _retrieve_from_tokens(
        self,
        *,
        task_id: str,
        db_path: Path | str,
        question: str,
        query_tokens: list[str],
        question_type: str,
        limit: int,
    ) -> list[KnowledgeSearchResult]:
        query = " OR ".join(dict.fromkeys(query_tokens))
        store = SQLiteKnowledgeStore(db_path)
        results = store.search_chunks(query, task_id=task_id, limit=max(limit, 1) * self._candidate_limit)
        ranked = sorted(
            results,
            key=lambda item: self._score_result(item, question, query_tokens, question_type),
            reverse=True,
        )
        return ranked[: max(limit, 1)]

    def find_path(
        self,
        *,
        task_id: str,
        db_path: Path | str,
        path: str,
        limit: int = 5,
    ) -> KnowledgeSearchResult | None:
        normalized_path = path.strip()
        if not normalized_path or not Path(db_path).exists():
            return None

        candidates = self.retrieve(
            task_id=task_id,
            db_path=db_path,
            question=normalized_path,
            limit=limit,
        )
        lowered_path = normalized_path.lower()
        for candidate in candidates:
            if candidate.path.lower() == lowered_path:
                return candidate
        return candidates[0] if candidates else None

    def find_symbol(
        self,
        *,
        task_id: str,
        db_path: Path | str,
        symbol: str,
        limit: int = 5,
    ) -> KnowledgeSearchResult | None:
        normalized_symbol = symbol.strip()
        if not normalized_symbol or not Path(db_path).exists():
            return None

        candidates = self.retrieve(
            task_id=task_id,
            db_path=db_path,
            question=normalized_symbol,
            limit=limit,
        )
        lowered_symbol = normalized_symbol.lower()
        for candidate in candidates:
            if (candidate.symbol_name or "").lower() == lowered_symbol:
                return candidate
        return candidates[0] if candidates else None

    def _build_query_tokens(self, question: str, question_type: str) -> list[str]:
        extracted: list[str] = []
        for token in _WORD_PATTERN.findall(question):
            cleaned = token.strip("./-_")
            if not cleaned:
                continue
            parts = [part.lower() for part in re.split(r"[/._-]+", cleaned) if part]
            if len(parts) == 1:
                extracted.append(parts[0])
            extracted.extend(parts)
        extracted.extend(_QUESTION_TYPE_TERMS.get(question_type, []))
        return [token for token in dict.fromkeys(extracted) if token]

    def _score_result(
        self,
        result: KnowledgeSearchResult,
        question: str,
        query_tokens: list[str],
        question_type: str,
    ) -> tuple[float, float, int, int, int, int, str]:
        lowered_question = question.lower()
        lowered_path = result.path.lower()
        basename = Path(result.path).name.lower()
        symbol_name = (result.symbol_name or "").lower()
        lowered_content = result.content.lower()

        direct_path_hit = 1 if lowered_path in lowered_question else 0
        basename_hit = 1 if basename and basename in lowered_question else 0
        symbol_hit = 1 if symbol_name and symbol_name in lowered_question else 0
        entry_file_hit = 1 if Path(result.path).name in _ENTRY_FILES else 0
        token_hits = sum(
            1
            for token in query_tokens
            if token in lowered_path or token in symbol_name or token in lowered_content
        )
        type_boost = self._file_type_boost(result.path, question_type)
        bm25_score = -result.score
        return (
            direct_path_hit * 100.0
            + basename_hit * 40.0
            + symbol_hit * 30.0
            + type_boost * 10.0
            + entry_file_hit * 5.0
            + token_hits,
            bm25_score,
            direct_path_hit,
            basename_hit,
            type_boost,
            token_hits,
            result.path,
        )

    def _file_type_boost(self, path: str, question_type: str) -> int:
        lowered = path.lower()
        if question_type == "backend":
            return 3 if lowered.endswith(".py") else 0
        if question_type == "frontend":
            return 3 if lowered.endswith((".vue", ".tsx", ".jsx", ".ts", ".js")) else 0
        if question_type == "config":
            return 3 if lowered.endswith((".yml", ".yaml", ".toml", ".json", ".env")) or "dockerfile" in lowered else 0
        return 0

    def ensure_chinese(self, text: str) -> bool:
        return bool(_CJK_PATTERN.search(text))
