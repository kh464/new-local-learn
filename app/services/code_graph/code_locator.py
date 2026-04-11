from __future__ import annotations

from pathlib import Path

from app.services.code_graph.graph_expander import ExpandedSubgraph
from app.services.code_graph.models import CodeSnippetEvidence


class CodeLocator:
    def __init__(self, *, repo_root: Path, max_lines_per_snippet: int = 80, max_snippets: int = 8) -> None:
        self._repo_root = Path(repo_root)
        self._max_lines_per_snippet = max_lines_per_snippet
        self._max_snippets = max_snippets

    def locate(self, *, subgraph: ExpandedSubgraph) -> list[CodeSnippetEvidence]:
        snippets: list[CodeSnippetEvidence] = []
        for symbol in subgraph.symbols[: self._max_snippets]:
            snippet = self.locate_symbol(
                path=symbol.file_path,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                qualified_name=symbol.qualified_name,
                symbol_id=symbol.symbol_id,
            )
            if snippet is not None:
                snippets.append(snippet)
        return snippets

    def locate_symbol(
        self,
        *,
        path: str,
        start_line: int,
        end_line: int,
        qualified_name: str | None = None,
        symbol_id: str | None = None,
    ) -> CodeSnippetEvidence | None:
        absolute_path = (self._repo_root / path).resolve()
        repo_root = self._repo_root.resolve()
        try:
            absolute_path.relative_to(repo_root)
        except ValueError:
            return None
        if not absolute_path.is_file():
            return None
        lines = absolute_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if not lines:
            return None
        bounded_start = max(start_line, 1)
        bounded_end = min(max(end_line, bounded_start), bounded_start + self._max_lines_per_snippet - 1, len(lines))
        snippet = "\n".join(lines[bounded_start - 1 : bounded_end])
        return CodeSnippetEvidence(
            path=path,
            start_line=bounded_start,
            end_line=bounded_end,
            snippet=snippet,
            symbol_id=symbol_id,
            qualified_name=qualified_name,
        )

