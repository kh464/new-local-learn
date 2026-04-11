from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CodeFileNode:
    task_id: str
    path: str
    language: str
    file_kind: str
    summary_zh: str = ""
    entry_role: str | None = None
    responsibility_zh: str = ""
    upstream_zh: str = ""
    downstream_zh: str = ""
    keywords_zh: list[str] = field(default_factory=list)
    summary_source: str = "rule"
    summary_version: int = 0
    summary_confidence: str = "low"


@dataclass(frozen=True)
class CodeSymbolNode:
    task_id: str
    symbol_id: str
    symbol_kind: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    parent_symbol_id: str | None = None
    signature: str | None = None
    summary_zh: str = ""
    language: str = "python"
    input_output_zh: str = ""
    side_effects_zh: str = ""
    call_targets_zh: str = ""
    callers_zh: str = ""
    summary_source: str = "rule"
    summary_version: int = 0
    summary_confidence: str = "low"


@dataclass(frozen=True)
class CodeEdge:
    task_id: str
    from_symbol_id: str
    to_symbol_id: str
    edge_kind: str
    source_path: str
    line: int | None = None
    confidence: float = 1.0


@dataclass(frozen=True)
class UnresolvedCall:
    task_id: str
    caller_symbol_id: str
    callee_name: str
    source_path: str
    line: int | None = None
    raw_expr: str | None = None


@dataclass(frozen=True)
class SemanticDocument:
    task_id: str
    item_id: str
    item_type: str
    path: str | None
    qualified_name: str | None
    summary_zh: str
    language: str
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5


@dataclass(frozen=True)
class RetrievalCandidate:
    task_id: str
    item_id: str
    item_type: str
    path: str | None
    symbol_id: str | None
    qualified_name: str | None
    score: float
    source: str
    summary_zh: str | None = None


@dataclass(frozen=True)
class CodeSnippetEvidence:
    path: str
    start_line: int
    end_line: int
    snippet: str
    symbol_id: str | None = None
    qualified_name: str | None = None
