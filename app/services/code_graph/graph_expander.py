from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSymbolNode, RetrievalCandidate


@dataclass(frozen=True)
class ExpandedSubgraph:
    seeds: list[RetrievalCandidate] = field(default_factory=list)
    files: list[CodeFileNode] = field(default_factory=list)
    symbols: list[CodeSymbolNode] = field(default_factory=list)
    edges: list[CodeEdge] = field(default_factory=list)


class GraphExpander:
    def __init__(self, *, graph_store) -> None:
        self._graph_store = graph_store

    def expand(
        self,
        *,
        task_id: str,
        seeds: list[RetrievalCandidate],
        max_hops: int = 2,
        max_nodes: int = 30,
    ) -> ExpandedSubgraph:
        files_by_path = {file.path: file for file in self._graph_store.list_files(task_id=task_id)}
        symbols_by_id = {symbol.symbol_id: symbol for symbol in self._graph_store.list_symbols(task_id=task_id)}
        symbols_by_name: dict[str, list[CodeSymbolNode]] = {}
        for symbol in symbols_by_id.values():
            symbols_by_name.setdefault(symbol.name.lower(), []).append(symbol)

        visited_symbols: set[str] = set()
        collected_edges: list[CodeEdge] = []
        queue: list[tuple[str, int]] = []

        for seed in seeds:
            if seed.symbol_id:
                queue.append((seed.symbol_id, 0))
            elif seed.path:
                for symbol in self._graph_store.list_symbols(task_id=task_id, file_path=seed.path):
                    queue.append((symbol.symbol_id, 0))

        while queue and len(visited_symbols) < max_nodes:
            symbol_id, hop = queue.pop(0)
            if symbol_id in visited_symbols:
                continue
            visited_symbols.add(symbol_id)
            if hop >= max_hops:
                continue
            related_edges = self._graph_store.list_out_edges(task_id=task_id, symbol_id=symbol_id) + self._graph_store.list_in_edges(
                task_id=task_id,
                symbol_id=symbol_id,
            )
            for edge in related_edges:
                collected_edges.append(edge)
                neighbor = edge.to_symbol_id if edge.from_symbol_id == symbol_id else edge.from_symbol_id
                if neighbor in symbols_by_id and neighbor not in visited_symbols:
                    queue.append((neighbor, hop + 1))

            for edge in self._resolve_unresolved_neighbors(
                task_id=task_id,
                caller_symbol_id=symbol_id,
                symbols_by_name=symbols_by_name,
            ):
                collected_edges.append(edge)
                if edge.to_symbol_id in symbols_by_id and edge.to_symbol_id not in visited_symbols:
                    queue.append((edge.to_symbol_id, hop + 1))

        collected_symbols = [symbols_by_id[symbol_id] for symbol_id in visited_symbols if symbol_id in symbols_by_id]
        collected_paths = {symbol.file_path for symbol in collected_symbols}
        for seed in seeds:
            if seed.path:
                collected_paths.add(seed.path)
        collected_files = [files_by_path[path] for path in sorted(collected_paths) if path in files_by_path]

        dedup_edges: list[CodeEdge] = []
        seen_edges: set[tuple[str, str, str, str, int | None]] = set()
        for edge in collected_edges:
            key = (edge.edge_kind, edge.from_symbol_id, edge.to_symbol_id, edge.source_path, edge.line)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            dedup_edges.append(edge)

        return ExpandedSubgraph(
            seeds=seeds,
            files=collected_files,
            symbols=sorted(collected_symbols, key=lambda item: (item.file_path, item.start_line, item.qualified_name)),
            edges=dedup_edges,
        )

    def _resolve_unresolved_neighbors(
        self,
        *,
        task_id: str,
        caller_symbol_id: str,
        symbols_by_name: dict[str, list[CodeSymbolNode]],
    ) -> list[CodeEdge]:
        matches: list[CodeEdge] = []
        unresolved_calls = self._graph_store.list_unresolved_calls(task_id=task_id, caller_symbol_id=caller_symbol_id)
        seen_targets: set[tuple[str, str, int | None]] = set()

        for unresolved in unresolved_calls:
            candidates = list(symbols_by_name.get(unresolved.callee_name.lower(), []))
            if not candidates:
                continue
            ranked_candidates = self._rank_unresolved_candidates(
                unresolved_raw_expr=unresolved.raw_expr,
                candidates=candidates,
            )
            for symbol in ranked_candidates[:5]:
                key = (unresolved.caller_symbol_id, symbol.symbol_id, unresolved.line)
                if key in seen_targets or symbol.symbol_id == unresolved.caller_symbol_id:
                    continue
                seen_targets.add(key)
                matches.append(
                    CodeEdge(
                        task_id=task_id,
                        from_symbol_id=unresolved.caller_symbol_id,
                        to_symbol_id=symbol.symbol_id,
                        edge_kind="calls",
                        source_path=unresolved.source_path,
                        line=unresolved.line,
                        confidence=0.6,
                    )
                )
        return matches

    def _rank_unresolved_candidates(
        self,
        *,
        unresolved_raw_expr: str | None,
        candidates: list[CodeSymbolNode],
    ) -> list[CodeSymbolNode]:
        hint = self._extract_unresolved_owner_hint(unresolved_raw_expr)
        if not hint:
            return sorted(candidates, key=lambda item: (item.file_path, item.start_line, item.qualified_name))
        return sorted(
            candidates,
            key=lambda item: (
                -self._unresolved_candidate_score(symbol=item, owner_hint=hint),
                item.file_path,
                item.start_line,
                item.qualified_name,
            ),
        )

    def _extract_unresolved_owner_hint(self, raw_expr: str | None) -> str:
        if not raw_expr or "." not in raw_expr:
            return ""
        owner = raw_expr.rsplit(".", 1)[0].strip().lower()
        if not owner:
            return ""
        return owner.split(".")[-1]

    def _unresolved_candidate_score(self, *, symbol: CodeSymbolNode, owner_hint: str) -> int:
        basename = Path(symbol.file_path).stem.lower()
        qualified = symbol.qualified_name.lower()
        score = 0
        if owner_hint and owner_hint == basename:
            score += 3
        if owner_hint and owner_hint in qualified:
            score += 2
        if owner_hint and owner_hint in symbol.file_path.lower():
            score += 1
        return score
