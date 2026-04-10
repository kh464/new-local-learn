from __future__ import annotations

from app.services.chat.models import AgentToolCall, PlannerResult


class RuleFallbackPlanner:
    def plan(self, question: str) -> PlannerResult:
        normalized = question.strip()
        if any(keyword in normalized for keyword in ("后端", "前端", "请求", "接口", "调用链")):
            return PlannerResult(
                inferred_intent="定位前后端入口并整理调用链证据",
                answer_depth="detailed",
                current_hypothesis="需要先读取仓库认知图，再从入口、调用链和符号证据中组织回答。",
                gaps=["尚未加载仓库认知图"],
                ready_to_answer=False,
                tool_call=AgentToolCall(
                    name="load_repo_map",
                    arguments={},
                    reason="规则兜底先读取仓库认知图，避免直接用自然语言对子串匹配调用链。",
                ),
            )

        return PlannerResult(
            inferred_intent="定位用户问题相关代码位置",
            answer_depth="detailed",
            current_hypothesis="需要先搜索相关代码片段。",
            gaps=["尚未定位相关文件"],
            ready_to_answer=False,
            tool_call=AgentToolCall(
                name="search_code",
                arguments={"query": normalized},
                reason="规则兜底优先搜索代码片段。",
            ),
        )
