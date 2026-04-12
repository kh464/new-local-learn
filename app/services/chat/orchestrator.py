from __future__ import annotations

import inspect
import re
from typing import Any

from app.core.chat_models import PlannerMetadata
from app.core.models import AnswerDebug, TaskChatCitation, TaskChatResponse, TaskGraphEvidence
from app.services.chat.models import AgentObservation, EvidenceItem, EvidencePack, PlannerResult

_ROUTE_PATH_PATTERN = re.compile(r"/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.{}:-]+)*")
_SYMBOL_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")
_ENGLISH_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_./-]{1,}")
_CHINESE_PHRASE_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}")
_FOLLOWUP_MARKERS = (
    "继续",
    "展开",
    "细说",
    "详细说",
    "再讲",
    "接着",
    "上一问",
    "前面说的",
    "刚才说的",
    "上面提到的",
    "那它",
    "它的",
    "该函数",
    "该接口",
    "该路由",
    "这个函数",
    "这个接口",
    "这个路由",
)
_TOPIC_STOPWORDS = (
    "请",
    "请问",
    "帮我",
    "一下",
    "这个项目",
    "该项目",
    "项目",
    "仓库",
    "代码",
    "是否",
    "是不是",
    "实现",
    "请只基于代码证据回答",
    "只基于代码证据回答",
    "基于代码证据回答",
    "回答",
    "说明",
    "分析",
    "一下",
)


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
        question_analyzer=None,
        exact_retriever=None,
        semantic_retriever=None,
        hybrid_ranker=None,
        graph_expander=None,
        code_locator=None,
        graph_evidence_builder=None,
        max_loops: int = 5,
    ) -> None:
        self._planning_agent = planning_agent
        self._fallback_planner = fallback_planner
        self._mcp_gateway = mcp_gateway
        self._evidence_assembler = evidence_assembler
        self._answer_composer = answer_composer
        self._answer_validator = answer_validator
        self._question_analyzer = question_analyzer
        self._exact_retriever = exact_retriever
        self._semantic_retriever = semantic_retriever
        self._hybrid_ranker = hybrid_ranker
        self._graph_expander = graph_expander
        self._code_locator = code_locator
        self._graph_evidence_builder = graph_evidence_builder
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
        del repo_map_path

        if self._can_use_hybrid_graph_pipeline():
            return await self._answer_with_hybrid_graph_pipeline(
                task_id=task_id,
                db_path=db_path,
                question=question,
                history=history,
            )

        observations: list[AgentObservation] = []
        used_tools: list[str] = []
        planning_source = "llm"
        fallback_used = False
        scoped_history = self._scope_history_for_question(question=question, history=history)
        history_payload = [{"role": item.role, "content": item.content} for item in scoped_history]
        available_tools = await self._list_available_tools()
        planning_context = await self._build_planning_context(task_id=task_id, question=question)
        del task_id, db_path

        last_plan = None
        plan_count = 0
        for loop_index in range(self._max_loops):
            try:
                if self._planning_agent is None:
                    raise RuntimeError("Planning agent is unavailable.")
                plan = await self._plan_with_context(
                    question=question,
                    history=history_payload,
                    observations=observations,
                    available_tools=available_tools,
                    loop_count=loop_index,
                    remaining_loops=self._max_loops - loop_index,
                    planning_context=planning_context,
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

        draft, validation, answer_debug_meta = await self._compose_and_validate_answer(
            question=question,
            evidence_pack=evidence_pack,
            history=scoped_history,
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
            answer_debug=self._build_answer_debug(evidence_pack, answer_debug_meta),
            planner_metadata=PlannerMetadata(
                planning_source=planning_source,
                loop_count=loop_count,
                used_tools=used_tools,
                fallback_used=fallback_used,
                search_queries=list(getattr(last_plan, "search_queries", []) or []),
                question_type=str(getattr(last_plan, "question_type", "") or "") or None,
                retrieval_objective=str(getattr(last_plan, "retrieval_objective", "") or "") or None,
                must_include_entities=list(getattr(last_plan, "must_include_entities", []) or []),
                preferred_evidence_kinds=list(getattr(last_plan, "preferred_evidence_kinds", []) or []),
            ),
        )

    def _can_use_hybrid_graph_pipeline(self) -> bool:
        return all(
            item is not None
            for item in (
                self._question_analyzer,
                self._exact_retriever,
                self._hybrid_ranker,
                self._graph_expander,
                self._code_locator,
                self._graph_evidence_builder,
            )
        )

    async def _answer_with_hybrid_graph_pipeline(
        self,
        *,
        task_id: str,
        db_path,
        question: str,
        history: list,
    ) -> TaskChatResponse:
        scoped_history = self._scope_history_for_question(question=question, history=history)
        history_payload = [{"role": item.role, "content": item.content} for item in scoped_history]
        planning_context = await self._build_planning_context(task_id=task_id, question=question)
        analysis = await self._analyze_question(
            question=question,
            history_payload=history_payload,
            planning_context=planning_context,
        )
        exact_hits = self._exact_retriever.retrieve(
            task_id=task_id,
            db_path=db_path,
            question=question,
            normalized_question=analysis.normalized_question,
            target_entities=list(analysis.target_entities),
            search_queries=list(analysis.search_queries),
            limit=8,
        )
        semantic_hits = []
        if self._semantic_retriever is not None:
            semantic_hits = await self._maybe_await(
                self._semantic_retriever.retrieve(
                    task_id=task_id,
                    question=analysis.normalized_question,
                    item_types=list(analysis.preferred_item_types),
                    language="python",
                    limit=8,
                )
            )
        ranked_hits = self._hybrid_ranker.rank(
            exact_hits=exact_hits,
            semantic_hits=semantic_hits,
            question_type=analysis.question_type,
            search_queries=list(analysis.search_queries),
            must_include_entities=list(getattr(analysis, "must_include_entities", []) or []),
            preferred_evidence_kinds=list(getattr(analysis, "preferred_evidence_kinds", []) or []),
            limit=8,
        )
        max_hops = 3 if analysis.question_type == "architecture_explanation" else 2
        subgraph = self._graph_expander.expand(
            task_id=task_id,
            seeds=ranked_hits,
            max_hops=max_hops,
            max_nodes=20,
            must_include_entities=list(getattr(analysis, "must_include_entities", []) or []),
            preferred_evidence_kinds=list(getattr(analysis, "preferred_evidence_kinds", []) or []),
        )
        snippets = self._code_locator.locate(subgraph=subgraph)
        graph_evidence_pack = self._graph_evidence_builder.build(
            question=question,
            normalized_question=analysis.normalized_question,
            retrieval_objective=analysis.retrieval_objective,
            subgraph=subgraph,
            snippets=snippets,
        )
        chat_evidence_pack = self._convert_graph_evidence(
            graph_evidence_pack,
            question_type=analysis.question_type,
            must_include_entities=list(getattr(analysis, "must_include_entities", []) or []),
            preferred_evidence_kinds=list(getattr(analysis, "preferred_evidence_kinds", []) or []),
        )
        draft, validation, answer_debug_meta = await self._compose_and_validate_answer(
            question=question,
            evidence_pack=chat_evidence_pack,
            history=scoped_history,
        )
        confidence = draft["confidence"]
        confidence_override = validation.get("confidence_override")
        if confidence_override in {"high", "medium", "low"}:
            confidence = confidence_override

        used_tools = ["exact_retriever", "graph_expander", "code_locator"]
        if semantic_hits:
            used_tools.insert(1, "semantic_retriever")

        return TaskChatResponse(
            answer=draft["answer"],
            citations=self._build_citations(chat_evidence_pack),
            graph_evidence=self._build_graph_evidence(chat_evidence_pack),
            supplemental_notes=list(draft["supplemental_notes"]),
            confidence=confidence,
            answer_source=draft["answer_source"],
            answer_debug=self._build_answer_debug(chat_evidence_pack, answer_debug_meta),
            planner_metadata=PlannerMetadata(
                planning_source="hybrid_rag",
                loop_count=1,
                used_tools=used_tools,
                fallback_used=False,
                search_queries=list(analysis.search_queries),
                question_type=analysis.question_type,
                retrieval_objective=analysis.retrieval_objective,
                must_include_entities=list(getattr(analysis, "must_include_entities", []) or []),
                preferred_evidence_kinds=list(getattr(analysis, "preferred_evidence_kinds", []) or []),
            ),
        )

    async def _build_planning_context(self, *, task_id: str, question: str) -> dict[str, object] | None:
        if self._exact_retriever is None or not hasattr(self._exact_retriever, "build_planning_context"):
            return None
        return await self._maybe_await(
            self._exact_retriever.build_planning_context(task_id=task_id, question=question, limit=6)
        )

    async def _plan_with_context(self, **kwargs):
        plan = self._planning_agent.plan
        parameters = inspect.signature(plan).parameters
        if "planning_context" in parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        ):
            return await self._maybe_await(plan(**kwargs))
        kwargs.pop("planning_context", None)
        return await self._maybe_await(plan(**kwargs))

    async def _analyze_question(
        self,
        *,
        question: str,
        history_payload: list[dict[str, str]],
        planning_context: dict[str, object] | None,
    ):
        analyze = self._question_analyzer.analyze
        parameters = inspect.signature(analyze).parameters
        if "planning_context" in parameters:
            return await self._maybe_await(
                analyze(question=question, history=history_payload, planning_context=planning_context)
            )
        return await self._maybe_await(analyze(question=question, history=history_payload))

    def _convert_graph_evidence(
        self,
        graph_pack,
        *,
        question_type: str | None = None,
        must_include_entities: list[str] | None = None,
        preferred_evidence_kinds: list[str] | None = None,
    ) -> EvidencePack:
        node_items_by_id: dict[str, EvidenceItem] = {}
        node_meta_by_id: dict[str, dict[str, object]] = {}
        seed_ids = {str(seed.symbol_id) for seed in list(getattr(graph_pack, "seeds", []) or []) if getattr(seed, "symbol_id", None)}
        seed_paths = {str(seed.path) for seed in list(getattr(graph_pack, "seeds", []) or []) if getattr(seed, "path", None)}
        must_include_entities = list(must_include_entities or [])
        preferred_evidence_kinds = list(preferred_evidence_kinds or [])
        question_text = " ".join(
            part.strip()
            for part in (
                str(getattr(graph_pack, "question", "") or ""),
                str(getattr(graph_pack, "normalized_question", "") or ""),
                str(getattr(graph_pack, "retrieval_objective", "") or ""),
                " ".join(must_include_entities),
            )
            if part and str(part).strip()
        )
        entrypoints: list[EvidenceItem] = []
        files = [
            EvidenceItem(
                kind="file",
                path=str(node.get("path") or ""),
                title=str(node.get("path") or node.get("kind") or ""),
                summary=str(node.get("summary_zh") or ""),
                start_line=self._coerce_int(node.get("start_line")),
                end_line=self._coerce_int(node.get("end_line")),
                node_ids=[f"file:{str(node.get('path') or '')}"] if str(node.get("path") or "").strip() else [],
            )
            for node in graph_pack.graph_nodes
            if node.get("kind") == "file"
        ]
        routes: list[EvidenceItem] = []
        symbols: list[EvidenceItem] = []
        for node in graph_pack.graph_nodes:
            kind = str(node.get("kind") or "")
            node_id = self._infer_graph_node_id(node)
            item = EvidenceItem(
                kind="route" if kind == "route" else ("file" if kind == "file" else "symbol"),
                path=str(node.get("path") or ""),
                title=self._resolve_graph_item_title(kind=kind, node=node),
                summary=str(node.get("summary_zh") or ""),
                start_line=self._coerce_int(node.get("start_line")),
                end_line=self._coerce_int(node.get("end_line")),
                node_ids=[node_id] if node_id else ([f"file:{str(node.get('path') or '')}"] if str(node.get("path") or "").strip() else []),
            )
            if kind == "file":
                if node.get("entry_role"):
                    entrypoints.append(
                        EvidenceItem(
                            kind="entrypoint",
                            path=item.path,
                            title=item.title,
                            summary=item.summary,
                            start_line=item.start_line,
                            end_line=item.end_line,
                            node_ids=list(item.node_ids),
                        )
                    )
                if node_id:
                    node_items_by_id[node_id] = item
                    node_meta_by_id[node_id] = node
                continue
            if kind == "route":
                routes.append(item)
            else:
                symbols.append(item)
            if node_id:
                node_items_by_id[node_id] = item
                node_meta_by_id[node_id] = node

        citations = [
            EvidenceItem(
                kind="citation",
                path=item.path,
                title=item.qualified_name or item.path,
                summary=item.qualified_name or "",
                start_line=item.start_line,
                end_line=item.end_line,
                snippet=item.snippet,
                node_ids=[f"file:{item.path}"] if item.path else [],
            )
            for item in graph_pack.snippets
        ]
        call_chains = self._build_call_chain_evidence(
            graph_edges=list(getattr(graph_pack, "graph_edges", []) or []),
            node_items_by_id=node_items_by_id,
            seed_ids=seed_ids,
            seed_paths=seed_paths,
            question_text=question_text,
            question_type=question_type,
            must_include_entities=must_include_entities,
            preferred_evidence_kinds=preferred_evidence_kinds,
        )
        key_findings = self._merge_unique_strings(
            self._build_graph_key_findings(
                graph_edges=list(getattr(graph_pack, "graph_edges", []) or []),
                node_items_by_id=node_items_by_id,
                node_meta_by_id=node_meta_by_id,
                entrypoints=entrypoints,
                routes=routes,
                seed_ids=seed_ids,
                seed_paths=seed_paths,
                question_text=question_text,
                question_type=question_type,
                must_include_entities=must_include_entities,
                preferred_evidence_kinds=preferred_evidence_kinds,
            ),
            list(graph_pack.summaries),
        )
        confidence_basis = []
        if call_chains:
            confidence_basis.append("已命中 route 节点及 routes_to 关系，可直接确认路由到处理函数的映射。")
        if citations:
            confidence_basis.append("已命中真实代码片段，可用于确认文件位置和函数定义。")
        return EvidencePack(
            question=graph_pack.question,
            planning_source="hybrid_rag",
            question_type=question_type,
            retrieval_objective=str(getattr(graph_pack, "retrieval_objective", "") or ""),
            must_include_entities=must_include_entities,
            preferred_evidence_kinds=preferred_evidence_kinds,
            entrypoints=entrypoints,
            call_chains=call_chains,
            routes=routes,
            files=files,
            symbols=symbols,
            citations=citations,
            key_findings=key_findings,
            reasoning_steps=self._build_reasoning_steps(call_chains=call_chains, routes=routes, citations=citations),
            confidence_basis=confidence_basis,
        )

    def _build_call_chain_evidence(
        self,
        *,
        graph_edges: list[dict[str, object]],
        node_items_by_id: dict[str, EvidenceItem],
        seed_ids: set[str],
        seed_paths: set[str],
        question_text: str,
        question_type: str | None,
        must_include_entities: list[str],
        preferred_evidence_kinds: list[str],
    ) -> list[EvidenceItem]:
        ranked_call_chains: list[tuple[int, EvidenceItem]] = []
        for edge in graph_edges:
            edge_kind = str(edge.get("kind") or "")
            if edge_kind not in {"routes_to", "calls"}:
                continue
            route_id = str(edge.get("from") or "")
            target_id = str(edge.get("to") or "")
            route_item = node_items_by_id.get(route_id)
            target_item = node_items_by_id.get(target_id)
            if route_item is None or target_item is None:
                continue
            relevance = self._graph_edge_relevance(
                edge_kind=edge_kind,
                source_id=route_id,
                target_id=target_id,
                source_item=route_item,
                target_item=target_item,
                seed_ids=seed_ids,
                seed_paths=seed_paths,
                question_text=question_text,
                question_type=question_type,
                must_include_entities=must_include_entities,
                preferred_evidence_kinds=preferred_evidence_kinds,
            )
            if edge_kind == "calls" and relevance < 3:
                continue
            route_location = self._format_item_location(route_item)
            target_location = self._format_item_location(target_item)
            if edge_kind == "routes_to":
                summary_parts = [f"路由 {route_item.title}"]
                if route_location:
                    summary_parts.append(f"定义在 {route_location}")
                summary_parts.append(f"并指向处理函数 {target_item.title}")
                if target_location and target_location != route_location:
                    summary_parts.append(f"（位于 {target_location}）")
            else:
                summary_parts = [f"函数 {route_item.title}"]
                if route_location:
                    summary_parts.append(f"位于 {route_location}")
                summary_parts.append(f"调用 {target_item.title}")
                if target_location and target_location != route_location:
                    summary_parts.append(f"（位于 {target_location}）")
            item = EvidenceItem(
                    kind="call_chain",
                    path=target_item.path or route_item.path,
                    title=f"{route_item.title} -> {target_item.title}",
                    summary="，".join(summary_parts) + "。",
                    start_line=target_item.start_line or route_item.start_line,
                    end_line=target_item.end_line or route_item.end_line,
                    node_ids=self._merge_unique_strings(list(route_item.node_ids), list(target_item.node_ids)),
                )
            ranked_call_chains.append(
                (
                    relevance,
                    item,
                )
            )
        ranked_call_chains.sort(key=lambda pair: (-pair[0], pair[1].title))
        return [item for _, item in ranked_call_chains]

    def _build_graph_key_findings(
        self,
        *,
        graph_edges: list[dict[str, object]],
        node_items_by_id: dict[str, EvidenceItem],
        node_meta_by_id: dict[str, dict[str, object]],
        entrypoints: list[EvidenceItem],
        routes: list[EvidenceItem],
        seed_ids: set[str],
        seed_paths: set[str],
        question_text: str,
        question_type: str | None,
        must_include_entities: list[str],
        preferred_evidence_kinds: list[str],
    ) -> list[str]:
        findings: list[str] = []
        ranked_route_findings: list[tuple[int, list[str]]] = []
        route_ids_with_handler: set[str] = set()
        for edge in graph_edges:
            edge_kind = str(edge.get("kind") or "")
            if edge_kind not in {"routes_to", "calls"}:
                continue
            route_id = str(edge.get("from") or "")
            target_id = str(edge.get("to") or "")
            route_item = node_items_by_id.get(route_id)
            target_item = node_items_by_id.get(target_id)
            if route_item is None or target_item is None:
                continue
            relevance = self._graph_edge_relevance(
                edge_kind=edge_kind,
                source_id=route_id,
                target_id=target_id,
                source_item=route_item,
                target_item=target_item,
                seed_ids=seed_ids,
                seed_paths=seed_paths,
                question_text=question_text,
                question_type=question_type,
                must_include_entities=must_include_entities,
                preferred_evidence_kinds=preferred_evidence_kinds,
            )
            if edge_kind == "calls" and relevance < 3:
                continue
            target_location = self._format_item_location(target_item)
            items = []
            if edge_kind == "routes_to":
                route_ids_with_handler.add(route_id)
                if target_location:
                    items.append(f"已确认 {route_item.title} 由 {target_item.title} 处理，函数位置在 {target_location}。")
                else:
                    items.append(f"已确认 {route_item.title} 由 {target_item.title} 处理。")
                route_meta = node_meta_by_id.get(route_id, {})
                owner = str(route_meta.get("qualified_name") or "").strip()
                if owner:
                    items.append(f"对应路由节点为 {owner}。")
                scope_finding = self._build_scope_key_finding(target_item.title)
                if scope_finding:
                    items.append(scope_finding)
            else:
                if target_location:
                    items.append(f"已确认 {route_item.title} 调用 {target_item.title}，目标位置在 {target_location}。")
                else:
                    items.append(f"已确认 {route_item.title} 调用 {target_item.title}。")
            ranked_route_findings.append(
                (
                    relevance,
                    items,
                )
            )
        ranked_route_findings.sort(key=lambda pair: -pair[0])
        for _, items in ranked_route_findings:
            findings.extend(items)
        for item in entrypoints:
            findings.append(f"已确认 {item.path} 是仓库入口文件。")
        for route in routes:
            location = self._format_item_location(route)
            if location:
                message = f"已确认路由 {route.title} 定义在 {location}。"
            else:
                message = f"已确认存在路由 {route.title}。"
            route_id = next(
                (
                    node_id
                    for node_id, node in node_items_by_id.items()
                    if node.kind == "route" and node.title == route.title and node.path == route.path
                ),
                "",
            )
            if route_id in route_ids_with_handler:
                continue
            findings.append(message)
        return findings

    def _build_reasoning_steps(
        self,
        *,
        call_chains: list[EvidenceItem],
        routes: list[EvidenceItem],
        citations: list[EvidenceItem],
    ) -> list[str]:
        steps: list[str] = []
        if routes:
            steps.append("先根据检索结果命中了 route 节点。")
        if call_chains:
            steps.append("再依据 routes_to 图边将路由节点映射到具体处理函数。")
        if citations:
            steps.append("最后结合真实代码片段确认文件位置与函数定义。")
        return steps

    def _merge_unique_strings(self, *groups: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for item in group:
                text = str(item or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                result.append(text)
        return result

    def _format_item_location(self, item: EvidenceItem) -> str:
        path = item.path.strip()
        if not path:
            return ""
        if item.start_line is not None:
            return f"{path}:{item.start_line}"
        return path

    def _coerce_int(self, value):
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    def _infer_graph_node_id(self, node: dict[str, object]) -> str:
        explicit = str(node.get("node_id") or node.get("symbol_id") or "").strip()
        if explicit:
            return explicit
        kind = str(node.get("kind") or "").strip()
        path = str(node.get("path") or "").strip()
        language = str(node.get("language") or self._infer_language_from_path(path) or "python").strip()
        if kind == "file" and path:
            return f"file:{language}:{path}"
        qualified_name = str(node.get("qualified_name") or "").strip()
        if kind and path and qualified_name:
            return f"{kind}:{language}:{path}:{qualified_name}"
        return ""

    def _infer_language_from_path(self, path: str) -> str:
        if path.endswith(".py"):
            return "python"
        if path.endswith(".java"):
            return "java"
        if path.endswith(".cpp") or path.endswith(".cc") or path.endswith(".cxx"):
            return "cpp"
        if path.endswith(".c"):
            return "c"
        return ""

    def _resolve_graph_item_title(self, *, kind: str, node: dict[str, object]) -> str:
        if kind == "file":
            return str(node.get("path") or node.get("kind") or "")
        if kind == "route":
            return str(node.get("name") or node.get("qualified_name") or node.get("path") or "")
        return str(node.get("qualified_name") or node.get("name") or node.get("path") or node.get("kind") or "")

    def _graph_edge_relevance(
        self,
        *,
        edge_kind: str,
        source_id: str,
        target_id: str,
        source_item: EvidenceItem,
        target_item: EvidenceItem,
        seed_ids: set[str],
        seed_paths: set[str],
        question_text: str,
        question_type: str | None,
        must_include_entities: list[str],
        preferred_evidence_kinds: list[str],
    ) -> int:
        question_score = self._question_match_score(question_text=question_text, source_item=source_item, target_item=target_item)
        must_include_score = self._must_include_edge_score(
            source_item=source_item,
            target_item=target_item,
            must_include_entities=must_include_entities,
        )
        evidence_score = self._preferred_evidence_edge_score(
            edge_kind=edge_kind,
            source_item=source_item,
            target_item=target_item,
            question_type=question_type,
            preferred_evidence_kinds=preferred_evidence_kinds,
        )
        if question_score or must_include_score or evidence_score:
            return 4 + question_score + must_include_score + evidence_score
        if edge_kind == "calls":
            if source_id in seed_ids:
                return 3
            if target_id in seed_ids:
                return 2
            if source_item.path in seed_paths or target_item.path in seed_paths:
                return 1
            return 0
        if source_id in seed_ids or target_id in seed_ids:
            return 3
        if source_item.path in seed_paths or target_item.path in seed_paths:
            return 2
        return 1

    def _must_include_edge_score(
        self,
        *,
        source_item: EvidenceItem,
        target_item: EvidenceItem,
        must_include_entities: list[str],
    ) -> int:
        if not must_include_entities:
            return 0
        text = " ".join(
            part.lower()
            for part in (
                source_item.title,
                source_item.summary,
                source_item.path,
                target_item.title,
                target_item.summary,
                target_item.path,
            )
            if part
        )
        score = 0
        for entity in must_include_entities:
            normalized = str(entity or "").strip().lower()
            if len(normalized) < 2:
                continue
            if normalized in text:
                score += 3
        return score

    def _preferred_evidence_edge_score(
        self,
        *,
        edge_kind: str,
        source_item: EvidenceItem,
        target_item: EvidenceItem,
        question_type: str | None,
        preferred_evidence_kinds: list[str],
    ) -> int:
        evidence_kinds = {str(kind or "").strip().lower() for kind in preferred_evidence_kinds if str(kind or "").strip()}
        score = 0
        combined_text = " ".join(
            part.lower()
            for part in (
                source_item.title,
                source_item.summary,
                target_item.title,
                target_item.summary,
            )
            if part
        )
        if "call_chain" in evidence_kinds and edge_kind == "calls":
            score += 2
        if "route_fact" in evidence_kinds and edge_kind == "routes_to":
            score += 2
        if "state_assignment_fact" in evidence_kinds and (
            question_type == "init_state_explanation" or "app.state" in combined_text or "create_app" in combined_text
        ):
            score += 2
        return score

    def _scope_history_for_question(self, *, question: str, history: list) -> list:
        if not history:
            return []
        recent_history = list(history[-4:])
        question_tokens = self._extract_topic_tokens(question)
        history_tokens = self._extract_history_tokens(recent_history)
        if question_tokens and question_tokens.intersection(history_tokens):
            return recent_history
        if self._looks_like_followup(question=question, question_tokens=question_tokens):
            return recent_history
        return []

    def _extract_history_tokens(self, history: list) -> set[str]:
        tokens: set[str] = set()
        for item in history:
            tokens.update(self._extract_topic_tokens(getattr(item, "content", "") or ""))
        return tokens

    def _extract_topic_tokens(self, text: str) -> set[str]:
        tokens: set[str] = set()
        for pattern in (_ROUTE_PATH_PATTERN, _SYMBOL_PATTERN, _ENGLISH_TOKEN_PATTERN):
            for match in pattern.finditer(text):
                value = match.group(0).strip().lower()
                if len(value) >= 2:
                    tokens.add(value)
        for phrase in _CHINESE_PHRASE_PATTERN.findall(text):
            cleaned = phrase
            for stopword in _TOPIC_STOPWORDS:
                cleaned = cleaned.replace(stopword, " ")
            cleaned = re.sub(r"\s+", " ", cleaned).strip().replace(" ", "")
            if len(cleaned) >= 2:
                tokens.add(cleaned.lower())
        return tokens

    def _looks_like_followup(self, *, question: str, question_tokens: set[str]) -> bool:
        if any(marker in question for marker in _FOLLOWUP_MARKERS):
            return True
        if any(token in {"它", "它的", "其", "这个函数", "这个接口", "这个路由"} for token in question_tokens):
            return True
        return False

    def _question_match_score(self, *, question_text: str, source_item: EvidenceItem, target_item: EvidenceItem) -> int:
        normalized = question_text.lower()
        if not normalized:
            return 0
        candidates = [source_item.title, target_item.title]
        route_path = self._extract_route_path(source_item.title)
        if route_path:
            candidates.append(route_path)
        for candidate in candidates:
            text = candidate.lower().strip()
            if text and text in normalized:
                return 2
        target_leaf = target_item.title.split(".")[-1].lower().strip()
        if target_leaf and target_leaf in normalized:
            return 1
        return 0

    def _extract_route_path(self, title: str) -> str:
        if " " not in title:
            return ""
        return title.split(" ", 1)[1].strip()

    def _build_scope_key_finding(self, qualified_name: str) -> str:
        parts = [part.strip() for part in qualified_name.split(".") if part.strip()]
        if len(parts) < 4:
            return ""
        parent_scope = parts[-2]
        symbol_name = parts[-1]
        if not parent_scope or not symbol_name:
            return ""
        return f"在当前代码图谱命名中，{qualified_name} 表示 {symbol_name} 属于 {parent_scope} 的内部符号作用域。"

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

    async def _compose_answer(
        self,
        *,
        question: str,
        evidence_pack: EvidencePack,
        history: list,
        validation_feedback: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        compose = self._answer_composer.compose
        parameters = inspect.signature(compose).parameters
        kwargs = {
            "question": question,
            "evidence_pack": evidence_pack,
            "history": history,
        }
        if "validation_feedback" in parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        ):
            kwargs["validation_feedback"] = validation_feedback or {}
        result = await self._maybe_await(compose(**kwargs))
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

    async def _compose_and_validate_answer(
        self,
        *,
        question: str,
        evidence_pack: EvidencePack,
        history: list,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        draft = await self._compose_answer(question=question, evidence_pack=evidence_pack, history=history)
        validation = await self._validate_answer(
            question=question,
            answer=draft["answer"],
            supplemental_notes=draft["supplemental_notes"],
            evidence_pack=evidence_pack,
        )
        initial_validation = dict(validation)
        retry_attempted = False
        retry_succeeded = False
        answer_attempts = 1
        if validation.get("retryable") and not validation.get("passed"):
            retry_attempted = True
            answer_attempts = 2
            retry_feedback = {
                "issues": list(validation.get("issues") or []),
                "confidence_override": validation.get("confidence_override"),
                "must_include_entities": list(getattr(evidence_pack, "must_include_entities", []) or []),
                "preferred_evidence_kinds": list(getattr(evidence_pack, "preferred_evidence_kinds", []) or []),
                "evidence_gaps": list(getattr(evidence_pack, "gaps", []) or []),
            }
            draft = await self._compose_answer(
                question=question,
                evidence_pack=evidence_pack,
                history=history,
                validation_feedback=retry_feedback,
            )
            validation = await self._validate_answer(
                question=question,
                answer=draft["answer"],
                supplemental_notes=draft["supplemental_notes"],
                evidence_pack=evidence_pack,
            )
            retry_succeeded = bool(validation.get("passed"))
        debug_meta = {
            "validation_issues": list(initial_validation.get("issues") or validation.get("issues") or []),
            "retry_attempted": retry_attempted,
            "retry_succeeded": retry_succeeded,
            "answer_attempts": answer_attempts,
        }
        return draft, validation, debug_meta

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

    def _build_answer_debug(self, evidence_pack: EvidencePack, debug_meta: dict[str, Any] | None = None) -> AnswerDebug | None:
        confirmed_facts = [item.strip() for item in evidence_pack.key_findings if item and item.strip()]
        evidence_gaps = [item.strip() for item in evidence_pack.gaps if item and item.strip()]
        validation_issues = [item.strip() for item in list((debug_meta or {}).get("validation_issues") or []) if item and item.strip()]
        retry_attempted = bool((debug_meta or {}).get("retry_attempted"))
        retry_succeeded = bool((debug_meta or {}).get("retry_succeeded"))
        answer_attempts = int((debug_meta or {}).get("answer_attempts") or 1)
        related_node_ids = self._build_related_node_ids(evidence_pack)
        if not confirmed_facts and not evidence_gaps and not validation_issues and not retry_attempted and not related_node_ids:
            return None
        return AnswerDebug(
            confirmed_facts=confirmed_facts[:5],
            evidence_gaps=evidence_gaps[:5],
            validation_issues=validation_issues[:5],
            retry_attempted=retry_attempted,
            retry_succeeded=retry_succeeded,
            answer_attempts=max(1, answer_attempts),
            related_node_ids=related_node_ids[:12],
        )

    def _build_related_node_ids(self, evidence_pack: EvidencePack) -> list[str]:
        related: list[str] = []
        for item in (
            evidence_pack.call_chains
            + evidence_pack.routes
            + evidence_pack.symbols
            + evidence_pack.entrypoints
            + evidence_pack.files
            + evidence_pack.citations
        ):
            for node_id in list(getattr(item, "node_ids", []) or []):
                normalized = str(node_id or "").strip()
                if not normalized or normalized in related:
                    continue
                related.append(normalized)
        return related

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
