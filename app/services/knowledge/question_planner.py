from __future__ import annotations

from dataclasses import dataclass, field


_QUESTION_HINTS = {
    "知识库": ["knowledge", "index", "retriever", "repo_map", "sqlite"],
    "认知图": ["repo_map", "call_chain", "entrypoint", "graph"],
    "前端": ["frontend", "web", "vue", "react", "client"],
    "后端": ["backend", "app", "api", "fastapi", "server"],
    "入口": ["entry", "main", "app/main.py", "web/src/main.ts"],
    "调用链": ["call_chain", "maps_to_backend", "request", "route"],
    "流程": ["call_chain", "request", "route"],
    "接口": ["api", "route", "/api/"],
    "路由": ["api", "route", "router"],
}


@dataclass(slots=True)
class QuestionPlan:
    question_type: str
    entrypoint_hits: list[dict[str, object]] = field(default_factory=list)
    symbol_hits: list[dict[str, object]] = field(default_factory=list)
    edge_hits: list[dict[str, object]] = field(default_factory=list)
    call_chain_hits: list[dict[str, object]] = field(default_factory=list)


class QuestionPlanner:
    def __init__(self, repo_map_payload: dict[str, object]) -> None:
        self._repo_map = repo_map_payload

    def plan(self, question: str) -> QuestionPlan:
        question_type = self._classify(question)
        return QuestionPlan(
            question_type=question_type,
            entrypoint_hits=self._find_entrypoints(question_type, question),
            symbol_hits=self._find_symbols(question, question_type),
            edge_hits=self._find_edges(question_type, question),
            call_chain_hits=self._find_call_chains(question_type, question),
        )

    def _classify(self, question: str) -> str:
        lowered = question.lower()
        if "入口" in question:
            return "entrypoint"
        if any(keyword in question for keyword in ("调用链", "怎么到后端", "如何到后端", "请求如何", "流程")):
            return "call_chain"
        if any(keyword in question for keyword in ("页面", "组件", "触发")) and "请求" in question:
            return "call_chain"
        if any(keyword in question for keyword in ("是否存在", "有没有", "支持什么", "知识库", "能力")):
            return "capability"
        if "/api/" in lowered or "接口" in question or "路由" in question:
            return "route"
        return "general"

    def _find_entrypoints(self, question_type: str, question: str) -> list[dict[str, object]]:
        entrypoints = self._repo_map.get("entrypoints") or {}
        hits: list[dict[str, object]] = []
        if question_type == "entrypoint":
            if "前端" in question and entrypoints.get("frontend"):
                hits.append(entrypoints["frontend"])
            elif "后端" in question and entrypoints.get("backend"):
                hits.append(entrypoints["backend"])
            else:
                for key in ("backend", "frontend"):
                    if entrypoints.get(key):
                        hits.append(entrypoints[key])
        elif question_type in {"call_chain", "capability", "general"}:
            for key in ("backend", "frontend"):
                if entrypoints.get(key):
                    hits.append(entrypoints[key])
        return hits

    def _find_symbols(self, question: str, question_type: str) -> list[dict[str, object]]:
        symbols = list(self._repo_map.get("symbol_nodes") or [])
        ranked = sorted(
            symbols,
            key=lambda symbol: self._score_payload(question, question_type, symbol),
            reverse=True,
        )
        ranked = [symbol for symbol in ranked if self._score_payload(question, question_type, symbol) > 0]
        if ranked:
            return ranked[:5]
        return symbols[:5]

    def _find_edges(self, question_type: str, question: str) -> list[dict[str, object]]:
        edges = list(self._repo_map.get("edges") or [])
        if question_type == "call_chain":
            return [edge for edge in edges if edge.get("type") == "maps_to_backend"][:5]

        ranked = sorted(
            edges,
            key=lambda edge: self._score_payload(question, question_type, edge),
            reverse=True,
        )
        ranked = [edge for edge in ranked if self._score_payload(question, question_type, edge) > 0]
        if ranked:
            return ranked[:5]
        return edges[:5]

    def _find_call_chains(self, question_type: str, question: str) -> list[dict[str, object]]:
        call_chains = list(self._repo_map.get("call_chains") or [])
        if question_type == "call_chain":
            return call_chains[:5]

        ranked = sorted(
            call_chains,
            key=lambda chain: self._score_payload(question, question_type, chain),
            reverse=True,
        )
        return [chain for chain in ranked if self._score_payload(question, question_type, chain) > 0][:5]

    def _score_payload(self, question: str, question_type: str, payload: dict[str, object]) -> int:
        text = " ".join(str(value) for value in payload.values() if value is not None).lower()
        keywords = self._expand_keywords(question, question_type)
        score = 0
        for keyword in keywords:
            if keyword and keyword in text:
                score += 3
        if question_type == "capability" and "knowledge" in text:
            score += 10
        if question_type == "call_chain" and any(term in text for term in ("maps_to_backend", "/api/", "call_chain")):
            score += 6
        if question_type == "entrypoint" and any(term in text for term in ("main.py", "main.ts", "entry")):
            score += 6
        return score

    def _expand_keywords(self, question: str, question_type: str) -> list[str]:
        lowered = question.lower()
        keywords: list[str] = []

        for token in self._tokenize(lowered):
            keywords.append(token)

        for hint, expansions in _QUESTION_HINTS.items():
            if hint in question:
                keywords.extend(expansions)

        if question_type == "capability":
            keywords.extend(["feature", "support", "knowledge"])
        elif question_type == "call_chain":
            keywords.extend(["call_chain", "maps_to_backend", "request", "route"])
        elif question_type == "entrypoint":
            keywords.extend(["entry", "main", "bootstrap"])
        elif question_type == "route":
            keywords.extend(["api", "route", "router"])

        return list(dict.fromkeys(keyword for keyword in keywords if keyword))

    def _tokenize(self, question: str) -> list[str]:
        normalized = (
            question.replace("？", " ")
            .replace("?", " ")
            .replace("，", " ")
            .replace(",", " ")
            .replace("。", " ")
            .replace("：", " ")
            .replace(":", " ")
        )
        return [token for token in normalized.split() if token]
