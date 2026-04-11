from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSymbolNode, UnresolvedCall


@dataclass(frozen=True)
class ExtractionResult:
    files: list[CodeFileNode] = field(default_factory=list)
    symbols: list[CodeSymbolNode] = field(default_factory=list)
    edges: list[CodeEdge] = field(default_factory=list)
    unresolved_calls: list[UnresolvedCall] = field(default_factory=list)


class BaseLanguageAdapter:
    language: str = "text"

    def supports(self, path: Path) -> bool:
        raise NotImplementedError

    def extract_file(self, *, task_id: str, repo_root: Path, file_path: Path) -> ExtractionResult:
        raise NotImplementedError

