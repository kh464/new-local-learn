from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


_SYSTEM_PROMPT = """你是仓库问答系统的规划前问题分析器。
你的职责不是直接回答用户，而是把用户问题稳定归一化，输出后续检索需要的结构化结果。

你必须严格输出 JSON，对象字段只允许包含：
- normalized_question: string
- question_type: string
- answer_depth: "overview" | "detailed" | "code_walkthrough"
- retrieval_objective: string
- target_entities: string[]
- preferred_item_types: string[]
- search_queries: string[]
- raw_routes: string[]
- raw_symbols: string[]
- raw_files: string[]
- raw_keywords: string[]
- must_include_entities: string[]
- preferred_evidence_kinds: string[]

约束：
1. 所有自然语言内容必须使用简体中文，代码标识符和文件路径保持原样。
2. 不要直接回答用户问题。
3. search_queries 必须稳定、可检索、偏向短语级关键词，优先输出目录、文件、类名、函数名、接口名、配置名。
4. 对语义相同但表达不同的问题，要尽量输出一致的 normalized_question 与 search_queries。
5. 如果问题属于前端、部署、docker compose、Helm、知识库、向量检索、Qdrant 等专题，优先锚定对应目录和文件，不要默认回落到 app/main.py。
6. 如果 planning_context 提供了 file_hints、symbol_hints、relation_hints、keyword_hints，优先利用这些线索稳定 question_type、search_queries、must_include_entities、preferred_evidence_kinds。
7. 不要输出 Markdown，不要输出解释性文字，只返回 JSON。"""

_PATH_PATTERN = re.compile(r"[A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|jsx|vue|json|ya?ml|toml|md)")
_DOTTED_SYMBOL_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")
_IDENTIFIER_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_ROUTE_PATH_PATTERN = re.compile(r"/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.{}:-]+)*")
_HTTP_METHOD_PATTERN = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH)\b", re.IGNORECASE)
_CHINESE_PHRASE_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}")
_ENGLISH_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_./-]{1,}")

_CHINESE_STOPWORDS = (
    "请问",
    "请",
    "帮我",
    "一个",
    "详细",
    "逐行",
    "逐步",
    "解释",
    "说明",
    "分析",
    "介绍",
    "确认",
    "当前",
    "这个",
    "仓库",
    "项目",
    "代码",
    "里面",
    "是否",
    "有没有",
    "有无",
    "具有",
    "实现",
    "构建",
    "支持",
    "具备",
    "功能",
    "能力",
    "相关",
    "哪些",
    "哪个",
    "什么",
)
_QUESTION_TYPES = {
    "capability_check",
    "architecture_explanation",
    "call_chain_trace",
    "module_responsibility",
    "code_walkthrough",
    "config_analysis",
    "init_state_explanation",
    "frontend_backend_flow",
    "api_inventory",
    "entrypoint_lookup",
    "symbol_explanation",
}
_TASK_FLOW_HINTS = (
    "分析任务",
    "提交任务",
    "任务流程",
    "执行顺序",
    "核心步骤",
    "后端步骤",
    "处理流程",
)
_CALL_CHAIN_HINTS = ("调用链", "链路")
_HEALTH_HINTS = ("健康检查", "health")
_CAPABILITY_HINTS = ("是否", "有没有", "有无", "支持", "具备", "几种", "哪些")
_DOMAIN_KEYWORDS = (
    "知识库",
    "knowledge",
    "retriever",
    "repo_map",
    "index",
    "rag",
    "向量",
    "qdrant",
    "create_app",
    "app.state",
    "任务队列",
    "queue",
    "backend",
    "后端",
    "frontend",
    "前端",
    "websocket",
    "轮询",
    "实时",
    "任务状态",
    "docker",
    "compose",
    "docker-compose",
    "helm",
    "chart",
    "templates",
    "健康检查",
    "health",
)


@dataclass(frozen=True)
class QuestionAnalysis:
    normalized_question: str
    question_type: str
    answer_depth: str
    retrieval_objective: str
    target_entities: list[str] = field(default_factory=list)
    preferred_item_types: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    raw_routes: list[str] = field(default_factory=list)
    raw_symbols: list[str] = field(default_factory=list)
    raw_files: list[str] = field(default_factory=list)
    raw_keywords: list[str] = field(default_factory=list)
    must_include_entities: list[str] = field(default_factory=list)
    preferred_evidence_kinds: list[str] = field(default_factory=list)


class QuestionAnalyzer:
    def __init__(self, *, llm_client=None) -> None:
        self._llm_client = llm_client

    async def analyze(
        self,
        *,
        question: str,
        history: list[dict[str, str]],
        planning_context: dict[str, object] | None = None,
    ) -> QuestionAnalysis:
        if self._llm_client is not None:
            try:
                payload = await self._llm_client.complete_json(
                    system_prompt=_SYSTEM_PROMPT,
                    user_prompt=json.dumps(
                        {"question": question, "history": history[-6:], "planning_context": planning_context or {}},
                        ensure_ascii=False,
                    ),
                )
                return self._normalize_payload(payload, question, planning_context=planning_context)
            except Exception:
                pass
        return self._fallback(question, planning_context=planning_context)

    def _normalize_payload(
        self,
        payload: dict[str, object],
        question: str,
        *,
        planning_context: dict[str, object] | None = None,
    ) -> QuestionAnalysis:
        fallback = self._fallback(question, planning_context=planning_context)
        normalized_question = str(payload.get("normalized_question") or fallback.normalized_question).strip()
        llm_question_type = str(payload.get("question_type") or "").strip()
        question_type = self._select_question_type(llm_question_type=llm_question_type, fallback=fallback.question_type)
        answer_depth = str(payload.get("answer_depth") or fallback.answer_depth).strip() or fallback.answer_depth
        retrieval_objective = str(payload.get("retrieval_objective") or fallback.retrieval_objective).strip()

        raw_routes = self._merge_unique(self._as_clean_list(payload.get("raw_routes")), fallback.raw_routes)
        raw_symbols = self._merge_unique(self._as_clean_list(payload.get("raw_symbols")), fallback.raw_symbols)
        raw_files = self._merge_unique(self._as_clean_list(payload.get("raw_files")), fallback.raw_files)
        raw_keywords = self._merge_unique(self._as_clean_list(payload.get("raw_keywords")), fallback.raw_keywords)
        target_entities = self._merge_unique(
            self._as_clean_list(payload.get("target_entities")),
            fallback.target_entities,
        )
        must_include_entities = self._merge_unique(
            self._as_clean_list(payload.get("must_include_entities")),
            fallback.must_include_entities,
        )
        preferred_item_types = self._merge_unique(
            self._as_clean_list(payload.get("preferred_item_types")),
            fallback.preferred_item_types,
        )
        preferred_evidence_kinds = self._merge_unique(
            self._as_clean_list(payload.get("preferred_evidence_kinds")),
            fallback.preferred_evidence_kinds,
        )
        search_queries = self._merge_unique(
            self._build_search_queries(
                question=question,
                question_type=question_type,
                target_entities=target_entities,
                raw_routes=raw_routes,
                raw_symbols=raw_symbols,
                raw_files=raw_files,
                raw_keywords=raw_keywords,
                must_include_entities=must_include_entities,
            ),
            self._build_search_queries(
                question=normalized_question,
                question_type=question_type,
                target_entities=target_entities,
                raw_routes=raw_routes,
                raw_symbols=raw_symbols,
                raw_files=raw_files,
                raw_keywords=raw_keywords,
                must_include_entities=must_include_entities,
            ),
            self._as_clean_list(payload.get("search_queries")),
        )

        return QuestionAnalysis(
            normalized_question=normalized_question or fallback.normalized_question,
            question_type=question_type,
            answer_depth=answer_depth,
            retrieval_objective=retrieval_objective or fallback.retrieval_objective,
            target_entities=target_entities,
            preferred_item_types=preferred_item_types or fallback.preferred_item_types,
            search_queries=search_queries,
            raw_routes=raw_routes,
            raw_symbols=raw_symbols,
            raw_files=raw_files,
            raw_keywords=raw_keywords,
            must_include_entities=must_include_entities,
            preferred_evidence_kinds=preferred_evidence_kinds or fallback.preferred_evidence_kinds,
        )

    def _fallback(self, question: str, *, planning_context: dict[str, object] | None = None) -> QuestionAnalysis:
        normalized_question = question.strip()
        raw_routes = self._extract_route_queries(normalized_question)
        raw_files = self._extract_files(normalized_question)
        raw_symbols = self._extract_symbols(normalized_question)
        context_files, context_symbols, context_keywords = self._extract_planning_context_entities(planning_context)
        raw_files = self._merge_unique(raw_files, context_files)
        raw_symbols = self._merge_unique(raw_symbols, context_symbols)
        raw_keywords = self._extract_keywords(normalized_question, raw_symbols=raw_symbols, raw_files=raw_files)
        raw_keywords = self._merge_unique(raw_keywords, context_keywords)
        question_type = self._classify_question_type(
            question=normalized_question,
            raw_routes=raw_routes,
            raw_files=raw_files,
            raw_symbols=raw_symbols,
            raw_keywords=raw_keywords,
        )
        target_entities = self._merge_unique(raw_files, raw_symbols, raw_routes)
        answer_depth = (
            "code_walkthrough"
            if any(term in normalized_question for term in ("逐行", "逐步", "详细", "代码级别"))
            else "detailed"
        )
        must_include_entities = self._build_must_include_entities(
            question=normalized_question,
            raw_symbols=raw_symbols,
            raw_keywords=raw_keywords,
            question_type=question_type,
        )
        preferred_evidence_kinds = self._preferred_evidence_kinds(question_type=question_type, question=normalized_question)
        preferred_item_types = self._preferred_item_types(question_type)
        return QuestionAnalysis(
            normalized_question=normalized_question,
            question_type=question_type,
            answer_depth=answer_depth,
            retrieval_objective=self._build_objective(normalized_question, question_type),
            target_entities=target_entities,
            preferred_item_types=preferred_item_types,
            search_queries=self._build_search_queries(
                question=normalized_question,
                question_type=question_type,
                target_entities=target_entities,
                raw_routes=raw_routes,
                raw_symbols=raw_symbols,
                raw_files=raw_files,
                raw_keywords=raw_keywords,
                must_include_entities=must_include_entities,
            ),
            raw_routes=raw_routes,
            raw_symbols=raw_symbols,
            raw_files=raw_files,
            raw_keywords=raw_keywords,
            must_include_entities=must_include_entities,
            preferred_evidence_kinds=preferred_evidence_kinds,
        )

    def _extract_planning_context_entities(
        self,
        planning_context: dict[str, object] | None,
    ) -> tuple[list[str], list[str], list[str]]:
        if not isinstance(planning_context, dict):
            return [], [], []
        file_hints = planning_context.get("file_hints")
        symbol_hints = planning_context.get("symbol_hints")
        relation_hints = planning_context.get("relation_hints")
        keyword_hints = planning_context.get("keyword_hints")
        files: list[str] = []
        symbols: list[str] = []
        keywords: list[str] = []
        if isinstance(file_hints, list):
            for item in file_hints[:4]:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "").strip()
                if path:
                    files.append(path)
        if isinstance(symbol_hints, list):
            for item in symbol_hints[:4]:
                if not isinstance(item, dict):
                    continue
                qualified_name = str(item.get("qualified_name") or "").strip()
                file_path = str(item.get("file_path") or "").strip()
                if qualified_name:
                    symbols.append(qualified_name)
                if file_path:
                    files.append(file_path)
        if isinstance(relation_hints, list):
            for item in relation_hints[:4]:
                if not isinstance(item, dict):
                    continue
                from_name = str(item.get("from_qualified_name") or "").strip()
                to_name = str(item.get("to_qualified_name") or "").strip()
                source_path = str(item.get("source_path") or "").strip()
                if from_name:
                    symbols.append(from_name)
                if to_name:
                    symbols.append(to_name)
                if source_path:
                    files.append(source_path)
        if isinstance(keyword_hints, list):
            for item in keyword_hints[:6]:
                text = str(item or "").strip()
                if text:
                    keywords.append(text)
        return self._merge_unique(files), self._merge_unique(symbols), self._merge_unique(keywords)

    def _select_question_type(self, *, llm_question_type: str, fallback: str) -> str:
        if llm_question_type in {"", "unknown"}:
            return fallback
        if llm_question_type not in _QUESTION_TYPES:
            return fallback
        if fallback != "module_responsibility":
            return fallback
        return llm_question_type

    def _classify_question_type(
        self,
        *,
        question: str,
        raw_routes: list[str],
        raw_files: list[str],
        raw_symbols: list[str],
        raw_keywords: list[str],
    ) -> str:
        lowered = question.lower()
        keyword_text = " ".join(raw_keywords).lower()

        if self._is_init_state_question(question=question, raw_keywords=raw_keywords, raw_symbols=raw_symbols):
            return "init_state_explanation"
        if self._looks_like_task_flow(question):
            return "architecture_explanation"
        if self._is_deploy_or_config_question(question=question, raw_keywords=raw_keywords):
            return "config_analysis"
        if raw_routes:
            return "call_chain_trace"
        if any(term in question for term in _CALL_CHAIN_HINTS) or "route" in lowered or "call" in lowered:
            return "call_chain_trace"
        if self._is_api_inventory_question(question=question, raw_routes=raw_routes, raw_keywords=raw_keywords):
            return "api_inventory"
        if self._is_frontend_backend_flow_question(question=question, raw_keywords=raw_keywords):
            return "frontend_backend_flow"
        if self._is_frontend_entry_lookup_question(question):
            return "entrypoint_lookup"
        if any(term in question for term in ("入口", "启动", "运行", "整体架构")):
            return "entrypoint_lookup"
        if any(term in question for term in ("逐行", "逐步", "详细解释")):
            return "code_walkthrough"
        if self._is_capability_question(question=question, raw_keywords=raw_keywords):
            return "capability_check"
        if raw_files or raw_symbols or "职责" in question or "做什么" in question or "什么意思" in question:
            return "symbol_explanation" if raw_symbols else "module_responsibility"
        if "前端" in keyword_text or "后端" in keyword_text:
            return "architecture_explanation"
        return "module_responsibility"

    def _is_init_state_question(self, *, question: str, raw_keywords: list[str], raw_symbols: list[str]) -> bool:
        keyword_text = " ".join(raw_keywords)
        return (
            ("app.state" in raw_symbols or "app.state" in keyword_text)
            and ("create_app" in raw_symbols or "create_app" in keyword_text or "初始化" in question)
            and any(term in question for term in ("挂载", "初始化", "核心对象", "哪些对象"))
        )

    def _is_api_inventory_question(self, *, question: str, raw_routes: list[str], raw_keywords: list[str]) -> bool:
        keyword_text = " ".join(raw_keywords).lower()
        if raw_routes and any(term in question for term in ("哪个函数", "处理的", "文件位置")):
            return False
        if any(route.startswith("/health") or route.endswith("/health") for route in raw_routes):
            return True
        return (
            any(term in question for term in ("接口有哪些", "路由有哪些", "接口列表", "路由列表", "有哪些接口"))
            and any(term in keyword_text for term in _HEALTH_HINTS)
        )

    def _is_frontend_backend_flow_question(self, *, question: str, raw_keywords: list[str]) -> bool:
        keyword_text = " ".join(raw_keywords).lower()
        return (
            "前端" in question
            and any(term in question for term in ("实时", "状态更新", "任务状态", "如何获取"))
            and any(term in keyword_text for term in ("前端", "实时", "任务状态", "websocket", "轮询"))
        )

    def _is_capability_question(self, *, question: str, raw_keywords: list[str]) -> bool:
        keyword_text = " ".join(raw_keywords).lower()
        capability_domain_terms = (
            "任务队列",
            "queue",
            "backend",
            "后端",
            "能力",
            "支持",
            "知识库",
            "knowledge",
            "retriever",
            "index",
            "rag",
            "向量",
        )
        domain_hit = any(term in keyword_text for term in capability_domain_terms)
        if not domain_hit:
            return False
        if any(term in question for term in _CAPABILITY_HINTS):
            return True
        return "吗" in question and any(term in keyword_text for term in ("知识库", "knowledge", "retriever", "rag"))

    def _is_deploy_or_config_question(self, *, question: str, raw_keywords: list[str]) -> bool:
        lowered = question.lower()
        keyword_text = " ".join(raw_keywords).lower()
        return any(
            term in lowered or term in keyword_text
            for term in (
                "docker",
                "compose",
                "docker-compose",
                "helm",
                "chart",
                "templates",
                "部署",
                "deployment",
                "环境变量",
                "qdrant",
            )
        )

    def _is_frontend_entry_lookup_question(self, question: str) -> bool:
        return any(
            term in question
            for term in ("页面入口", "入口组件", "Vue 入口", "Vue入口", "用户侧主界面", "管理端主界面")
        )

    def _looks_like_task_flow(self, question: str) -> bool:
        return any(term in question for term in _TASK_FLOW_HINTS) and any(
            term in question for term in ("分析", "任务", "提交", "后端")
        )

    def _build_objective(self, question: str, question_type: str) -> str:
        if question_type == "capability_check":
            return f"确认仓库是否实现“{question}”相关能力，并定位核心实现模块"
        if question_type == "call_chain_trace":
            return f"定位与“{question}”相关的入口、调用链和下游函数"
        if question_type == "config_analysis":
            return f"定位与“{question}”相关的配置文件、目录和初始化逻辑"
        if question_type == "init_state_explanation":
            return f"定位“{question}”对应的初始化入口、app.state 挂载点与状态对象来源"
        if question_type == "frontend_backend_flow":
            return f"定位“{question}”对应的前端状态更新方式、请求入口与后端通知链路"
        if question_type == "api_inventory":
            return f"定位“{question}”对应的接口定义、路由与处理函数"
        if question_type == "entrypoint_lookup":
            return f"定位“{question}”对应的入口文件、启动流程和主调度函数"
        if question_type == "symbol_explanation":
            return f"定位“{question}”最相关的符号定义并解释职责"
        return f"定位与“{question}”最相关的文件、类和方法并解释职责"

    def _extract_files(self, question: str) -> list[str]:
        return self._merge_unique(match.group(0) for match in _PATH_PATTERN.finditer(question))

    def _extract_symbols(self, question: str) -> list[str]:
        dotted = [match.group(0) for match in _DOTTED_SYMBOL_PATTERN.finditer(question)]
        identifiers = []
        for match in _IDENTIFIER_PATTERN.finditer(question):
            token = match.group(0)
            if token.upper() in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                continue
            if token in {"app", "py", "ts", "js"}:
                continue
            if "_" in token:
                identifiers.append(token)
        return self._merge_unique(dotted, identifiers)

    def _extract_keywords(self, question: str, *, raw_symbols: list[str], raw_files: list[str]) -> list[str]:
        candidates: list[str] = []
        lowered = question.lower()
        for keyword in _DOMAIN_KEYWORDS:
            if keyword.lower() in lowered:
                candidates.append(keyword)
        for phrase in _CHINESE_PHRASE_PATTERN.findall(question):
            cleaned = self._clean_chinese_phrase(phrase)
            if len(cleaned) >= 2:
                candidates.append(cleaned)
        for token in _ENGLISH_TOKEN_PATTERN.findall(question):
            cleaned = token.strip()
            if len(cleaned) < 2:
                continue
            if cleaned.upper() in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                continue
            candidates.append(cleaned)
        return self._merge_unique(candidates, raw_symbols, raw_files)

    def _build_search_queries(
        self,
        *,
        question: str,
        question_type: str,
        target_entities: list[str],
        raw_routes: list[str],
        raw_symbols: list[str],
        raw_files: list[str],
        raw_keywords: list[str],
        must_include_entities: list[str],
    ) -> list[str]:
        candidates: list[str] = []
        max_queries = 12 if self._looks_like_task_flow(question) else 10

        candidates.extend(self._contextual_anchor_queries(question=question, raw_keywords=raw_keywords))
        candidates.extend(target_entities)
        candidates.extend(raw_routes)
        candidates.extend(raw_files)
        candidates.extend(raw_symbols)
        candidates.extend(must_include_entities)
        candidates.extend(raw_keywords)

        if question_type == "call_chain_trace":
            candidates.extend(["调用链", "调用路径"])
        if question_type == "init_state_explanation":
            candidates.extend(["create_app", "app.state", "state"])
        if question_type == "capability_check":
            candidates.extend(["任务队列", "task queue", "queue backend"])
            if self._mentions_knowledge(question=question, raw_keywords=raw_keywords):
                candidates.extend(["知识库", "knowledge", "retriever", "repo_map", "index", "rag"])
        if question_type == "frontend_backend_flow":
            candidates.extend(["前端", "任务状态", "websocket", "轮询"])
        if question_type == "api_inventory":
            candidates.extend(["健康检查", "/health", "health"])
        if self._looks_like_task_flow(question):
            candidates.extend(
                [
                    "task_queue.py",
                    "task_queue",
                    "enqueue",
                    "submit",
                    "_worker_loop",
                    "_execute",
                    "分析任务",
                    "任务队列",
                    "提交任务",
                    "执行流程",
                ]
            )

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = str(candidate).strip()
            if len(normalized) < 2:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
            if len(deduped) >= max_queries:
                break
        return deduped

    def _contextual_anchor_queries(self, *, question: str, raw_keywords: list[str]) -> list[str]:
        candidates: list[str] = []
        lowered = question.lower()
        keyword_text = " ".join(raw_keywords).lower()

        if self._mentions_knowledge(question=question, raw_keywords=raw_keywords):
            candidates.extend(["知识库", "knowledge", "retriever", "repo_map", "index", "rag"])
        if "docker compose" in lowered or "docker-compose" in lowered or "compose" in keyword_text:
            candidates.extend(["docker-compose.yml", "services", "app"])
        if "helm" in lowered or "chart" in lowered or "templates" in lowered:
            candidates.extend(["ops/helm", "templates", "Chart.yaml"])
        if "qdrant" in lowered or "qdrant" in keyword_text:
            candidates.extend(["qdrant", "QdrantKnowledgeIndex", "vector_store.py"])
        if self._is_frontend_entry_lookup_question(question):
            candidates.extend(["frontend/src/user-main.js", "frontend/src/admin-main.js", "UserApp.vue", "AdminApp.vue"])
        return candidates

    def _mentions_knowledge(self, *, question: str, raw_keywords: list[str]) -> bool:
        lowered = question.lower()
        keyword_text = " ".join(raw_keywords).lower()
        return any(term in lowered or term in keyword_text for term in ("知识库", "knowledge", "retriever", "repo_map", "rag"))

    def _extract_route_queries(self, question: str) -> list[str]:
        route_paths = [match.group(0) for match in _ROUTE_PATH_PATTERN.finditer(question)]
        methods = [match.group(1).upper() for match in _HTTP_METHOD_PATTERN.finditer(question)]
        candidates: list[str] = []
        for route_path in route_paths:
            if methods:
                for method in methods:
                    candidates.append(f"{method} {route_path}")
            candidates.append(route_path)
            candidates.append(route_path.lstrip("/"))
        return self._merge_unique(candidates)

    def _build_must_include_entities(
        self,
        *,
        question: str,
        raw_symbols: list[str],
        raw_keywords: list[str],
        question_type: str,
    ) -> list[str]:
        candidates: list[str] = []
        keyword_text = " ".join(raw_keywords)
        if question_type == "init_state_explanation":
            if "create_app" in keyword_text or "create_app" in raw_symbols or "create_app" in question:
                candidates.append("create_app")
            if "app.state" in keyword_text or "app.state" in raw_symbols:
                candidates.append("app.state")
        return self._merge_unique(candidates)

    def _preferred_item_types(self, question_type: str) -> list[str]:
        if question_type in {"call_chain_trace", "frontend_backend_flow", "architecture_explanation"}:
            return ["symbol", "file", "call_chain"]
        if question_type in {"api_inventory", "init_state_explanation"}:
            return ["symbol", "file"]
        if question_type == "config_analysis":
            return ["file", "symbol"]
        return ["symbol", "file"]

    def _preferred_evidence_kinds(self, *, question_type: str, question: str) -> list[str]:
        if question_type == "init_state_explanation":
            return ["state_assignment_fact", "symbol", "file"]
        if question_type == "capability_check":
            return ["capability_fact", "symbol", "file"]
        if question_type == "frontend_backend_flow":
            return ["frontend_api_fact", "route_fact", "call_chain"]
        if question_type == "api_inventory":
            if any(term in question.lower() for term in _HEALTH_HINTS):
                return ["health_fact", "route_fact", "symbol"]
            return ["route_fact", "symbol"]
        if question_type == "call_chain_trace":
            return ["route_fact", "call_chain", "symbol"]
        if question_type == "architecture_explanation":
            return ["call_chain", "symbol", "file"]
        if question_type == "config_analysis":
            return ["file", "symbol"]
        return ["symbol", "file"]

    def _clean_chinese_phrase(self, phrase: str) -> str:
        cleaned = phrase
        for stopword in _CHINESE_STOPWORDS:
            cleaned = cleaned.replace(stopword, " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = cleaned.replace(" ", "")
        return cleaned

    def _as_clean_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _merge_unique(self, *values) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for items in values:
            for item in items:
                normalized = str(item).strip()
                if len(normalized) < 2:
                    continue
                key = normalized.lower()
                if key in seen:
                    continue
                seen.add(key)
                merged.append(normalized)
        return merged
