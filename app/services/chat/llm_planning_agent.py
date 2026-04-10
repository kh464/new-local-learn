from __future__ import annotations

import json
import re

from app.services.chat.models import AgentObservation, PlannerResult


_SYSTEM_PROMPT = """你是一个代码仓库分析规划 Agent。
你的职责不是回答用户，而是先把用户问题归一化，再决定下一步最合理的检索或阅读动作。

你必须严格输出 JSON，且必须使用简体中文。
你绝不能直接回答用户问题，不能输出解释性段落，不能输出 Markdown，不能输出 JSON 之外的任何文本。

你输出的 JSON 必须且只能包含以下字段：
- inferred_intent: 字符串。概括用户真正想解决的问题。
- answer_depth: 字符串。只能是 overview、detailed、code_walkthrough 之一。
- current_hypothesis: 字符串。当前最可能的分析方向。
- gaps: 字符串数组。当前还缺失的关键信息；没有则输出 []。
- normalized_question: 字符串。把用户原问题归一化后的稳定问法。对语义相同、表述不同的问题，这个字段应尽量保持一致。
- retrieval_objective: 字符串。说明本轮检索到底要确认什么事实、定位什么实现、排除什么歧义。
- search_queries: 字符串数组。3 到 6 个稳定检索词，按重要性排序。必须优先包含适合代码检索的中文概念词、英文实现词、可能的标识符或模块名。
- ready_to_answer: 布尔值。若信息已充分且无需继续调用工具，则为 true。
- tool_call: 对象或 null。只有在需要继续调用工具时才允许为对象。

tool_call 对象必须包含：
- name: 字符串。tool_call.name 必须只能使用 available_tools。
- arguments: 对象。传给工具的 JSON 参数。
- reason: 字符串。说明为什么下一步要调用这个工具。

你必须先做“问题归一化”，再做“工具决策”：
1. 去掉口语、重复字样、礼貌词和无检索价值的描述。
2. 保留仓库分析真正需要的实体、模块、能力、路径、接口、函数、数据流目标。
3. 如果问题是在问“是否存在某能力/模块”，normalized_question 要收敛成“确认仓库是否实现 X 能力，以及相关实现位置”这类稳定表述。
4. search_queries 不能只是复述原句，必须主动补充更稳定的代码检索词。
5. 对“知识库、认知图、检索、索引、问答、向量、仓库搜索”这类问题，要优先联想到 knowledge、retriever、index、repo_map、search、sqlite、rag 等实现词，但只能在合理时使用。
6. 对语义相同的问题，即使用户换一种说法，也应尽量给出相近的 normalized_question、retrieval_objective、search_queries。

必须遵守以下约束：
- 如果 ready_to_answer 为 true，则 tool_call 必须为 null。
- 如果 tool_call 不为 null，则 ready_to_answer 必须为 false。
- 如果可用工具不足以支持当前判断，也必须在现有 available_tools 中选择最合理的工具，不能虚构工具名。
- 你的职责只是规划下一步，不是回答用户。
"""

_STOPWORDS = {
    "请",
    "请问",
    "帮我",
    "帮忙",
    "想问",
    "一下",
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
    "具备",
}

_CONCEPT_HINTS: dict[str, list[str]] = {
    "知识库": ["知识库", "knowledge", "retriever", "repo_map", "index"],
    "认知图": ["认知图", "repo_map", "call_chain", "graph"],
    "调用链": ["调用链", "call_chain", "route", "request"],
    "登录": ["登录", "login", "auth", "signin"],
    "后端": ["后端", "backend", "api", "router"],
    "前端": ["前端", "frontend", "component", "page"],
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
    ) -> PlannerResult:
        payload = {
            "question": question,
            "history": history,
            "observations": [observation.model_dump(mode="json") for observation in observations],
            "available_tools": available_tools,
            "loop_count": loop_count,
            "remaining_loops": remaining_loops,
        }
        raw = await self._client.complete_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=json.dumps(payload, ensure_ascii=False),
        )
        result = PlannerResult.model_validate(raw)
        result = self._normalize_result(result=result, question=question)
        self._validate_result(result, available_tools)
        return result

    def _normalize_result(self, *, result: PlannerResult, question: str) -> PlannerResult:
        normalized_question = result.normalized_question.strip() or question.strip()
        retrieval_objective = result.retrieval_objective.strip() or result.inferred_intent.strip() or normalized_question
        search_queries = [query.strip() for query in result.search_queries if query and query.strip()]
        if not search_queries:
            search_queries = self._build_search_queries(
                question=question,
                normalized_question=normalized_question,
                retrieval_objective=retrieval_objective,
            )

        return result.model_copy(
            update={
                "normalized_question": normalized_question,
                "retrieval_objective": retrieval_objective,
                "search_queries": search_queries[:6],
            }
        )

    def _build_search_queries(
        self,
        *,
        question: str,
        normalized_question: str,
        retrieval_objective: str,
    ) -> list[str]:
        queries: list[str] = []
        combined = " ".join([question, normalized_question, retrieval_objective])
        for concept, expansions in _CONCEPT_HINTS.items():
            if concept in combined:
                queries.extend(expansions)

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

    @staticmethod
    def _validate_result(result: PlannerResult, available_tools: list[str]) -> None:
        allowed_answer_depths = {"overview", "detailed", "code_walkthrough"}
        if result.answer_depth not in allowed_answer_depths:
            raise ValueError(
                "Planner answer_depth must be one of overview, detailed, code_walkthrough."
            )

        if result.ready_to_answer and result.tool_call is not None:
            raise ValueError("Planner ready_to_answer=True cannot include a tool_call.")

        if not result.ready_to_answer and result.tool_call is None:
            raise ValueError("Planner ready_to_answer=False must include a tool_call.")

        if result.tool_call is not None and result.tool_call.name not in available_tools:
            raise ValueError("Planner tool_call.name must come from available_tools.")
