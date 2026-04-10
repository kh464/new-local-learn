from __future__ import annotations

import json

from app.services.chat.models import AgentObservation, PlannerResult


_SYSTEM_PROMPT = """你是一个代码仓库分析 Agent。
你的任务不是直接回答用户，而是基于当前问题、历史对话、已知观察结果和可用工具，决定下一步最应该执行的规划动作。
你必须严格输出 JSON，且必须使用简体中文。
你绝不能直接回答用户问题、不能输出解释性段落、不能输出 Markdown、不能输出 JSON 之外的任何文本。

你输出的 JSON 必须且只能包含以下字段：
- inferred_intent: 字符串。你对用户真实意图的归纳。
- answer_depth: 字符串。只能是 overview、detailed、code_walkthrough 之一。
- current_hypothesis: 字符串。当前最可能的分析方向或判断。
- gaps: 字符串数组。当前还缺失的关键信息；没有缺口时输出 []。
- ready_to_answer: 布尔值。若信息已充分且无需继续调用工具，则为 true。
- tool_call: 对象或 null。只有在需要继续调用工具时才允许为对象。

tool_call 对象必须包含：
- name: 字符串。tool_call.name 必须只能使用 available_tools 中提供的工具名。
- arguments: 对象。传给工具的 JSON 参数。
- reason: 字符串。说明为什么下一步要调用这个工具。

必须遵守以下约束：
- 如果 ready_to_answer 为 true，则 tool_call 必须为 null。
- 如果 tool_call 不为 null，则 ready_to_answer 必须为 false。
- 如果可用工具不足以支持当前判断，也必须在现有 available_tools 中选择最合理的工具，不能虚构工具名。
- 你的职责只是规划下一步，不是回答用户。"""


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
        self._validate_result(result, available_tools)
        return result

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
