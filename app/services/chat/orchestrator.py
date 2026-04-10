from __future__ import annotations

import inspect
from typing import Any

from app.core.chat_models import PlannerMetadata
from app.core.models import TaskChatCitation, TaskChatResponse, TaskGraphEvidence
from app.services.chat.models import AgentObservation, EvidencePack, PlannerResult


class TaskChatOrchestrator:
    def __init__(
        self,
        *,
        planning_agent,
        fallback_planner,
        mcp_gateway,
        evidence_assembler,
        answer_composer,
        answer_validator,
        max_loops: int = 5,
    ) -> None:
        self._planning_agent = planning_agent
        self._fallback_planner = fallback_planner
        self._mcp_gateway = mcp_gateway
        self._evidence_assembler = evidence_assembler
        self._answer_composer = answer_composer
        self._answer_validator = answer_validator
        self._max_loops = max(1, max_loops)

    async def answer_question(
        self,
        *,
        task_id: str,
        db_path,
        repo_map_path,
        question: str,
        history: list,
    ) -> TaskChatResponse:
        del task_id, db_path, repo_map_path

        observations: list[AgentObservation] = []
        used_tools: list[str] = []
        planning_source = "llm"
        fallback_used = False
        history_payload = [{"role": item.role, "content": item.content} for item in history]
        available_tools = await self._list_available_tools()

        last_plan = None
        plan_count = 0
        for loop_index in range(self._max_loops):
            try:
                if self._planning_agent is None:
                    raise RuntimeError("Planning agent is unavailable.")
                plan = await self._planning_agent.plan(
                    question=question,
                    history=history_payload,
                    observations=observations,
                    available_tools=available_tools,
                    loop_count=loop_index,
                    remaining_loops=self._max_loops - loop_index,
                )
            except Exception:
                if self._fallback_planner is None:
                    raise
                if observations:
                    plan = PlannerResult(
                        inferred_intent=question,
                        answer_depth="detailed",
                        current_hypothesis="Fallback evidence is available; stop tool expansion and answer conservatively.",
                        gaps=[],
                        ready_to_answer=True,
                        tool_call=None,
                    )
                else:
                    plan = await self._maybe_await(self._fallback_planner.plan(question))
                planning_source = "rule"
                fallback_used = True

            last_plan = plan
            plan_count += 1
            if plan.ready_to_answer or plan.tool_call is None or self._mcp_gateway is None:
                break
            if loop_index >= self._max_loops - 1:
                break

            tool_arguments = self._normalize_tool_arguments(plan)
            observation = await self._mcp_gateway.call_tool(plan.tool_call.name, tool_arguments)
            observations.append(observation)
            used_tools.append(observation.tool_name)

        loop_count = max(1, plan_count)
        evidence_pack = await self._assemble_evidence(
            question=question,
            planning_source=planning_source,
            observations=observations,
        )

        draft = await self._compose_answer(question=question, evidence_pack=evidence_pack, history=history)
        validation = await self._validate_answer(
            question=question,
            answer=draft["answer"],
            supplemental_notes=draft["supplemental_notes"],
            evidence_pack=evidence_pack,
        )
        confidence = draft["confidence"]
        confidence_override = validation.get("confidence_override")
        if confidence_override in {"high", "medium", "low"}:
            confidence = confidence_override

        return TaskChatResponse(
            answer=draft["answer"],
            citations=self._build_citations(evidence_pack),
            graph_evidence=self._build_graph_evidence(evidence_pack),
            supplemental_notes=list(draft["supplemental_notes"]),
            confidence=confidence,
            answer_source=draft["answer_source"],
            planner_metadata=PlannerMetadata(
                planning_source=planning_source,
                loop_count=loop_count,
                used_tools=used_tools,
                fallback_used=fallback_used,
                search_queries=list(getattr(last_plan, "search_queries", []) or []),
            ),
        )

    async def _list_available_tools(self) -> list[str]:
        if self._mcp_gateway is None:
            return []
        tools = await self._mcp_gateway.list_tools()
        return [str(tool.get("name")) for tool in tools if isinstance(tool, dict) and tool.get("name")]

    async def _assemble_evidence(
        self,
        *,
        question: str,
        planning_source: str,
        observations: list[AgentObservation],
    ) -> EvidencePack:
        assembler = self._evidence_assembler
        if assembler is None:
            return EvidencePack(question=question, planning_source=planning_source)

        if hasattr(assembler, "assemble"):
            result = assembler.assemble(
                question=question,
                planning_source=planning_source,
                observations=observations,
            )
        else:
            result = assembler(
                question=question,
                planning_source=planning_source,
                observations=observations,
            )
        result = await self._maybe_await(result)
        if isinstance(result, EvidencePack):
            return result
        if isinstance(result, dict):
            return EvidencePack.model_validate(result)
        return EvidencePack(question=question, planning_source=planning_source)

    async def _compose_answer(self, *, question: str, evidence_pack: EvidencePack, history: list) -> dict[str, Any]:
        result = await self._maybe_await(
            self._answer_composer.compose(question=question, evidence_pack=evidence_pack, history=history)
        )
        payload = dict(result or {})
        answer_source = str(payload.get("answer_source") or "local")
        if answer_source not in {"llm", "local"}:
            answer_source = "local"
        return {
            "answer": str(payload.get("answer") or ""),
            "supplemental_notes": list(payload.get("supplemental_notes") or []),
            "confidence": str(payload.get("confidence") or "medium"),
            "answer_source": answer_source,
        }

    def _normalize_tool_arguments(self, plan: PlannerResult) -> dict[str, object]:
        if plan.tool_call is None:
            return {}

        arguments = dict(plan.tool_call.arguments)
        if plan.tool_call.name == "search_code" and plan.search_queries:
            arguments["query"] = " ".join(query.strip() for query in plan.search_queries if query and query.strip())
        elif plan.tool_call.name == "trace_call_chain":
            if not arguments.get("query") and plan.normalized_question:
                arguments["query"] = plan.normalized_question
        return arguments

    async def _validate_answer(
        self,
        *,
        question: str,
        answer: str,
        supplemental_notes: list[str],
        evidence_pack: EvidencePack,
    ) -> dict[str, Any]:
        if self._answer_validator is None:
            return {"passed": True, "confidence_override": None}
        result = await self._maybe_await(
            self._answer_validator.validate(
                question=question,
                answer=answer,
                supplemental_notes=supplemental_notes,
                evidence_pack=evidence_pack,
            )
        )
        return dict(result or {})

    def _build_citations(self, evidence_pack: EvidencePack) -> list[TaskChatCitation]:
        citations: list[TaskChatCitation] = []
        for item in evidence_pack.citations:
            if not item.path or item.start_line is None or item.end_line is None or not item.snippet:
                continue
            citations.append(
                TaskChatCitation(
                    path=item.path,
                    start_line=item.start_line,
                    end_line=item.end_line,
                    reason=item.summary or item.title,
                    snippet=item.snippet,
                )
            )
        return citations

    def _build_graph_evidence(self, evidence_pack: EvidencePack) -> list[TaskGraphEvidence]:
        evidence: list[TaskGraphEvidence] = []
        for item in (
            evidence_pack.entrypoints
            + evidence_pack.call_chains
            + evidence_pack.routes
            + evidence_pack.files
            + evidence_pack.symbols
        ):
            evidence.append(
                TaskGraphEvidence(
                    kind=self._graph_kind(item.kind),
                    label=item.title,
                    detail=item.summary or None,
                    path=item.path or None,
                )
            )
        return evidence

    def _graph_kind(self, kind: str) -> str:
        if kind in {"entrypoint", "call_chain", "edge", "symbol"}:
            return kind
        if kind == "route":
            return "edge"
        if kind == "file":
            return "symbol"
        return "symbol"

    async def _maybe_await(self, value):
        if inspect.isawaitable(value):
            return await value
        return value
