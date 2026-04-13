from __future__ import annotations

import json
import re

from app.services.chat.models import AgentObservation, PlannerResult


_SYSTEM_PROMPT = """你是代码仓库问答链路中的规划 Agent。
你的职责不是回答用户，而是先把问题稳定归一化，再决定下一步最合理的检索或阅读动作。

你必须严格输出 JSON，并且必须使用简体中文。绝不能直接回答用户问题，不能输出解释段落，不能输出 Markdown，也不能输出 JSON 之外的任何文本。

JSON 只允许包含以下字段：
- inferred_intent
- answer_depth
- current_hypothesis
- gaps
- question_type
- normalized_question
- retrieval_objective
- search_queries
- must_include_entities
- preferred_evidence_kinds
- ready_to_answer
- tool_call

其中：
- answer_depth 只能是 overview、detailed、code_walkthrough 之一。
- question_type 优先使用 capability_check、architecture_explanation、call_chain_trace、module_responsibility、code_walkthrough、config_analysis、init_state_explanation、frontend_backend_flow、api_inventory、entrypoint_lookup、symbol_explanation。
- tool_call 只能在需要继续调工具时返回，且 name 必须来自 available_tools。

规则：
1. 先做“问题归一化”，再做“工具决策”。
2. 对语义相同但表达不同的问题，尽量给出一致的 normalized_question、retrieval_objective、search_queries。
3. search_queries 不能只是复述原句，必须主动补充稳定的代码检索词，优先目录、文件、类名、函数名、接口名、配置名。
4. 如果问题属于前端、部署、docker compose、Helm、知识库、向量检索、Qdrant 等专题，优先锚定对应目录和文件，不要默认回落到 app/main.py。
5. 如果问题是在问“是否存在某能力/模块”，normalized_question 应归一成“确认仓库是否实现 X 能力，以及相关实现位置”这类稳定问法。
6. 对“知识库、认知图、检索、索引、问答、向量、仓库搜索”类问题，优先联想到 knowledge、retriever、index、repo_map、search、sqlite、rag 等实现词，但只在合理时使用。
7. 如果 planning_context 提供了 file_hints、symbol_hints、relation_hints、keyword_hints，优先利用这些线索稳定 question_type、search_queries、must_include_entities、preferred_evidence_kinds。
8. 如果 ready_to_answer 为 true，则 tool_call 必须为 null。
9. 如果 tool_call 不为 null，则 ready_to_answer 必须为 false。
10. tool_call.name 必须只能使用 available_tools。
11. 你的职责只是规划下一步，不是回答用户。"""

_STOPWORDS = {
    "请",
    "请问",
    "帮我",
    "帮忙",
    "想问",
    "一个",
    "这个",
    "这个项目",
    "该项目",
    "项目里",
    "项目中",
    "仓库项目",
    "是否",
    "是不是",
    "有没有",
    "具有",
}

_CONCEPT_HINTS: dict[str, list[str]] = {
    "知识库": ["知识库", "knowledge", "retriever", "repo_map", "index", "rag"],
    "认知图": ["认知图", "repo_map", "call_chain", "graph"],
    "调用链": ["调用链", "call_chain", "route", "request"],
    "登录": ["登录", "login", "auth", "signin"],
    "后端": ["后端", "backend", "api", "router"],
    "前端": ["前端", "frontend", "component", "page"],
    "docker": ["docker", "docker compose", "docker-compose.yml", "services"],
    "helm": ["helm", "ops/helm", "templates", "Chart.yaml"],
    "qdrant": ["qdrant", "QdrantKnowledgeIndex", "vector_store.py"],
}

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_./-]+|[\u4e00-\u9fff]{2,}")


class LlmPlanningAgent:
    def __init__(self, *, client) -> None:
        self._client = client

    async def plan(
        self,
        *,
        question: str,
        history: list[dict[str, str]],
        observations: list[AgentObservation],
        available_tools: list[str],
        loop_count: int,
        remaining_loops: int,
        planning_context: dict[str, object] | None = None,
    ) -> PlannerResult:
        payload = {
            "question": question,
            "history": history,
            "observations": [observation.model_dump(mode="json") for observation in observations],
            "available_tools": available_tools,
            "loop_count": loop_count,
            "remaining_loops": remaining_loops,
            "planning_context": planning_context or {},
        }
        raw = await self._client.complete_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=json.dumps(payload, ensure_ascii=False),
        )
        result = PlannerResult.model_validate(raw)
        result = self._normalize_result(result=result, question=question, planning_context=planning_context)
        self._validate_result(result, available_tools)
        return result

    def _normalize_result(
        self,
        *,
        result: PlannerResult,
        question: str,
        planning_context: dict[str, object] | None = None,
    ) -> PlannerResult:
        normalized_question = result.normalized_question.strip() or question.strip()
        retrieval_objective = result.retrieval_objective.strip() or result.inferred_intent.strip() or normalized_question
        question_type = result.question_type.strip() or "module_responsibility"
        must_include_entities = [item.strip() for item in result.must_include_entities if item and item.strip()]
        preferred_evidence_kinds = [item.strip() for item in result.preferred_evidence_kinds if item and item.strip()]
        search_queries = [query.strip() for query in result.search_queries if query and query.strip()]
        if not search_queries:
            search_queries = self._build_search_queries(
                question=question,
                normalized_question=normalized_question,
                retrieval_objective=retrieval_objective,
                planning_context=planning_context,
            )

        return result.model_copy(
            update={
                "question_type": question_type,
                "normalized_question": normalized_question,
                "retrieval_objective": retrieval_objective,
                "search_queries": search_queries[:6],
                "must_include_entities": must_include_entities,
                "preferred_evidence_kinds": preferred_evidence_kinds,
            }
        )

    def _build_search_queries(
        self,
        *,
        question: str,
        normalized_question: str,
        retrieval_objective: str,
        planning_context: dict[str, object] | None = None,
    ) -> list[str]:
        queries: list[str] = []
        combined = " ".join([question, normalized_question, retrieval_objective])
        lowered = combined.lower()
        queries.extend(self._extract_planning_context_queries(planning_context))
        for concept, expansions in _CONCEPT_HINTS.items():
            if concept in combined or concept.lower() in lowered:
                queries.extend(expansions)

        if "docker compose" in lowered or "docker-compose" in lowered:
            queries.extend(["docker-compose.yml", "services"])
        if "helm" in lowered or "chart" in lowered or "templates" in lowered:
            queries.extend(["ops/helm", "templates", "Chart.yaml"])
        if any(term in lowered for term in ("知识库", "knowledge", "retriever", "repo_map", "rag")):
            queries.extend(["知识库", "knowledge", "retriever", "repo_map", "index"])

        for token in _TOKEN_PATTERN.findall(combined):
            cleaned = token.strip().lower()
            if not cleaned or cleaned in _STOPWORDS:
                continue
            queries.append(token if any("\u4e00" <= char <= "\u9fff" for char in token) else cleaned)

        deduped: list[str] = []
        seen: set[str] = set()
        for item in queries:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _extract_planning_context_queries(self, planning_context: dict[str, object] | None) -> list[str]:
        if not isinstance(planning_context, dict):
            return []
        queries: list[str] = []
        file_hints = planning_context.get("file_hints")
        symbol_hints = planning_context.get("symbol_hints")
        relation_hints = planning_context.get("relation_hints")
        keyword_hints = planning_context.get("keyword_hints")
        if isinstance(file_hints, list):
            for item in file_hints[:4]:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "").strip()
                if path:
                    queries.append(path)
        if isinstance(symbol_hints, list):
            for item in symbol_hints[:4]:
                if not isinstance(item, dict):
                    continue
                qualified_name = str(item.get("qualified_name") or "").strip()
                file_path = str(item.get("file_path") or "").strip()
                if qualified_name:
                    queries.append(qualified_name)
                if file_path:
                    queries.append(file_path)
        if isinstance(relation_hints, list):
            for item in relation_hints[:4]:
                if not isinstance(item, dict):
                    continue
                from_name = str(item.get("from_qualified_name") or "").strip()
                to_name = str(item.get("to_qualified_name") or "").strip()
                source_path = str(item.get("source_path") or "").strip()
                if from_name:
                    queries.append(from_name)
                if to_name:
                    queries.append(to_name)
                if source_path:
                    queries.append(source_path)
        if isinstance(keyword_hints, list):
            for item in keyword_hints[:6]:
                text = str(item or "").strip()
                if text:
                    queries.append(text)
        return queries

    @staticmethod
    def _validate_result(result: PlannerResult, available_tools: list[str]) -> None:
        allowed_answer_depths = {"overview", "detailed", "code_walkthrough"}
        if result.answer_depth not in allowed_answer_depths:
            raise ValueError("Planner answer_depth must be one of overview, detailed, code_walkthrough.")

        if result.ready_to_answer and result.tool_call is not None:
            raise ValueError("Planner ready_to_answer=True cannot include a tool_call.")

        if not result.ready_to_answer and result.tool_call is None:
            raise ValueError("Planner ready_to_answer=False must include a tool_call.")

        if result.tool_call is not None and result.tool_call.name not in available_tools:
            raise ValueError("Planner tool_call.name must come from available_tools.")
