from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


_SYSTEM_PROMPT = """你是仓库问答系统的提问分析器。你的职责不是直接回答问题，而是把用户问题稳定归一化，输出后续检索需要的结构化结果。

你必须严格输出 JSON，对象字段只允许包含：
- normalized_question: string
- question_type: "capability_check" | "architecture_explanation" | "call_chain_trace" | "module_responsibility" | "code_walkthrough" | "config_analysis"
- answer_depth: "overview" | "detailed" | "code_walkthrough"
- retrieval_objective: string
- target_entities: string[]
- preferred_item_types: string[]
- search_queries: string[]

约束：
1. 所有字符串内容必须使用简体中文，代码标识符和文件路径保持原样。
2. 不要直接回答用户问题。
3. search_queries 必须稳定、可检索、偏向短语级关键词，优先输出文件路径、类名、方法名、接口名、配置名、中文功能词。
4. 对语义相近但表述不同的问题，要尽量输出一致的 search_queries。
5. 不要输出 Markdown，不要输出解释性文字，只返回 JSON。"""

_PATH_PATTERN = re.compile(r"[A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|jsx|vue|json|ya?ml|toml|md)")
_SYMBOL_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")
_CHINESE_PHRASE_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}")
_ENGLISH_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_./-]{1,}")
_CHINESE_STOPWORDS = (
    "请问",
    "请",
    "帮我",
    "一下",
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
    "该",
    "仓库",
    "项目",
    "代码",
    "里面",
    "里",
    "中",
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
    "的",
    "是",
    "吗",
    "么",
    "呢",
    "呀",
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


class QuestionAnalyzer:
    def __init__(self, *, llm_client=None) -> None:
        self._llm_client = llm_client

    async def analyze(self, *, question: str, history: list[dict[str, str]]) -> QuestionAnalysis:
        if self._llm_client is not None:
            try:
                payload = await self._llm_client.complete_json(
                    system_prompt=_SYSTEM_PROMPT,
                    user_prompt=json.dumps({"question": question, "history": history[-6:]}, ensure_ascii=False),
                )
                return self._normalize_payload(payload, question)
            except Exception:
                pass
        return self._fallback(question)

    def _normalize_payload(self, payload: dict[str, object], question: str) -> QuestionAnalysis:
        normalized_question = str(payload.get("normalized_question") or question).strip()
        question_type = str(payload.get("question_type") or "module_responsibility")
        answer_depth = str(payload.get("answer_depth") or "detailed")
        retrieval_objective = str(payload.get("retrieval_objective") or normalized_question).strip()
        target_entities = [str(item).strip() for item in payload.get("target_entities") or [] if str(item).strip()]
        preferred_item_types = [str(item).strip() for item in payload.get("preferred_item_types") or [] if str(item).strip()]
        search_queries = [str(item).strip() for item in payload.get("search_queries") or [] if str(item).strip()]
        fallback_entities = target_entities or self._extract_entities(question)
        return QuestionAnalysis(
            normalized_question=normalized_question,
            question_type=question_type,
            answer_depth=answer_depth,
            retrieval_objective=retrieval_objective,
            target_entities=fallback_entities,
            preferred_item_types=preferred_item_types or self._preferred_item_types(question_type),
            search_queries=search_queries
            or self._build_search_queries(
                question=normalized_question,
                question_type=question_type,
                target_entities=fallback_entities,
            ),
        )

    def _fallback(self, question: str) -> QuestionAnalysis:
        normalized_question = question.strip()
        question_type = self._classify_question_type(normalized_question)
        target_entities = self._extract_entities(normalized_question)
        answer_depth = "code_walkthrough" if any(term in normalized_question for term in ("逐行", "详细", "逐步")) else "detailed"
        return QuestionAnalysis(
            normalized_question=normalized_question,
            question_type=question_type,
            answer_depth=answer_depth,
            retrieval_objective=self._build_objective(normalized_question, question_type),
            target_entities=target_entities,
            preferred_item_types=self._preferred_item_types(question_type),
            search_queries=self._build_search_queries(
                question=normalized_question,
                question_type=question_type,
                target_entities=target_entities,
            ),
        )

    def _classify_question_type(self, question: str) -> str:
        lowered = question.lower()
        if any(term in question for term in ("调用链", "链路", "流程")):
            return "call_chain_trace"
        if any(term in question for term in ("逐行", "逐步", "详细解释")):
            return "code_walkthrough"
        if any(term in question for term in ("配置", "部署", "环境变量", "docker", "qdrant")):
            return "config_analysis"
        if any(term in question for term in ("是否", "有没有", "具备", "支持")):
            return "capability_check"
        if any(term in question for term in ("入口", "架构", "整体", "运行")):
            return "architecture_explanation"
        if "call" in lowered or "route" in lowered:
            return "call_chain_trace"
        return "module_responsibility"

    def _build_objective(self, question: str, question_type: str) -> str:
        if question_type == "capability_check":
            return f"确认仓库是否实现“{question}”相关能力，并定位核心实现模块"
        if question_type == "call_chain_trace":
            return f"定位与“{question}”相关的入口、调用链和下游函数"
        if question_type == "config_analysis":
            return f"定位与“{question}”相关的配置文件和初始化逻辑"
        return f"定位与“{question}”最相关的文件、类和方法并解释职责"

    def _extract_entities(self, question: str) -> list[str]:
        entities = [match.group(0) for match in _PATH_PATTERN.finditer(question)]
        entities.extend(match.group(0) for match in _SYMBOL_PATTERN.finditer(question))
        deduped: list[str] = []
        seen: set[str] = set()
        for entity in entities:
            if entity in seen:
                continue
            seen.add(entity)
            deduped.append(entity)
        return deduped

    def _build_search_queries(self, *, question: str, question_type: str, target_entities: list[str]) -> list[str]:
        candidates: list[str] = []
        candidates.extend(target_entities)

        for phrase in _CHINESE_PHRASE_PATTERN.findall(question):
            cleaned = self._clean_chinese_phrase(phrase)
            if len(cleaned) >= 2:
                candidates.append(cleaned)
            if 2 <= len(phrase) <= 12:
                candidates.append(phrase)

        for token in _ENGLISH_TOKEN_PATTERN.findall(question):
            if len(token) >= 2:
                candidates.append(token)

        if question_type == "call_chain_trace":
            candidates.extend(["调用链", "调用路径"])

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = candidate.strip()
            if len(normalized) < 2:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
            if len(deduped) >= 8:
                break
        return deduped

    def _clean_chinese_phrase(self, phrase: str) -> str:
        cleaned = phrase
        for stopword in _CHINESE_STOPWORDS:
            cleaned = cleaned.replace(stopword, " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = cleaned.replace(" ", "")
        return cleaned

    def _preferred_item_types(self, question_type: str) -> list[str]:
        if question_type == "call_chain_trace":
            return ["symbol", "file", "call_chain"]
        if question_type == "config_analysis":
            return ["file", "symbol"]
        return ["symbol", "file"]
