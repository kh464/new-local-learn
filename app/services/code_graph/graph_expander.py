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
        must_include_entities: list[str] | None = None,
        preferred_evidence_kinds: list[str] | None = None,
    ) -> ExpandedSubgraph:
        files_by_path = {file.path: file for file in self._graph_store.list_files(task_id=task_id)}
        symbols_by_id = {symbol.symbol_id: symbol for symbol in self._graph_store.list_symbols(task_id=task_id)}
        symbols_by_name: dict[str, list[CodeSymbolNode]] = {}
        for symbol in symbols_by_id.values():
            symbols_by_name.setdefault(symbol.name.lower(), []).append(symbol)

        visited_symbols: set[str] = set()
        collected_edges: list[CodeEdge] = []
        queue: list[tuple[int, float, str]] = []
        must_include_entities = list(must_include_entities or [])
        preferred_evidence_kinds = list(preferred_evidence_kinds or [])

        for seed in seeds:
            if seed.symbol_id:
                self._enqueue_symbol(
                    queue=queue,
                    symbol_id=seed.symbol_id,
                    hop=0,
                    priority=self._symbol_priority_score(
                        symbol=symbols_by_id.get(seed.symbol_id),
                        must_include_entities=must_include_entities,
                        preferred_evidence_kinds=preferred_evidence_kinds,
                    )
                    + 100.0,
                )
            elif seed.path:
                for symbol in self._graph_store.list_symbols(task_id=task_id, file_path=seed.path):
                    self._enqueue_symbol(
                        queue=queue,
                        symbol_id=symbol.symbol_id,
                        hop=0,
                        priority=self._symbol_priority_score(
                            symbol=symbol,
                            must_include_entities=must_include_entities,
                            preferred_evidence_kinds=preferred_evidence_kinds,
                        ),
                    )

        while queue and len(visited_symbols) < max_nodes:
            queue.sort(key=lambda item: (item[0], -item[1], item[2]))
            hop, _, symbol_id = queue.pop(0)
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
                    self._enqueue_symbol(
                        queue=queue,
                        symbol_id=neighbor,
                        hop=hop + 1,
                        priority=self._symbol_priority_score(
                            symbol=symbols_by_id.get(neighbor),
                            must_include_entities=must_include_entities,
                            preferred_evidence_kinds=preferred_evidence_kinds,
                        ),
                    )

            for edge in self._resolve_unresolved_neighbors(
                task_id=task_id,
                caller_symbol_id=symbol_id,
                symbols_by_name=symbols_by_name,
            ):
                collected_edges.append(edge)
                if edge.to_symbol_id in symbols_by_id and edge.to_symbol_id not in visited_symbols:
                    self._enqueue_symbol(
                        queue=queue,
                        symbol_id=edge.to_symbol_id,
                        hop=hop + 1,
                        priority=self._symbol_priority_score(
                            symbol=symbols_by_id.get(edge.to_symbol_id),
                            must_include_entities=must_include_entities,
                            preferred_evidence_kinds=preferred_evidence_kinds,
                        ),
                    )

        collected_symbols = [symbols_by_id[symbol_id] for symbol_id in visited_symbols if symbol_id in symbols_by_id]
        collected_paths = {symbol.file_path for symbol in collected_symbols}
        for seed in seeds:
            if seed.path:
                collected_paths.add(seed.path)
        collected_files: list[CodeFileNode] = []
        for path in sorted(collected_paths):
            file_node = files_by_path.get(path)
            if file_node is None:
                file_node = CodeFileNode(
                    task_id=task_id,
                    path=path,
                    language=self._infer_language_from_path(path),
                    file_kind="source",
                    summary_zh="",
                )
            collected_files.append(file_node)

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

    def _infer_language_from_path(self, path: str) -> str:
        lowered = path.lower()
        if lowered.endswith(".py"):
            return "python"
        if lowered.endswith(".js"):
            return "javascript"
        if lowered.endswith(".ts"):
            return "typescript"
        if lowered.endswith(".vue"):
            return "vue"
        if lowered.endswith(".yaml") or lowered.endswith(".yml"):
            return "yaml"
        if lowered.endswith(".json"):
            return "json"
        return "text"

    def _enqueue_symbol(self, *, queue: list[tuple[int, float, str]], symbol_id: str, hop: int, priority: float) -> None:
        queue.append((hop, priority, symbol_id))

    def _symbol_priority_score(
        self,
        *,
        symbol: CodeSymbolNode | None,
        must_include_entities: list[str],
        preferred_evidence_kinds: list[str],
    ) -> float:
        if symbol is None:
            return 0.0
        text = " ".join(
            part.lower()
            for part in (
                symbol.name,
                symbol.qualified_name,
                symbol.file_path,
                symbol.summary_zh,
            )
            if part
        )
        score = 0.0
        for entity in must_include_entities:
            normalized = str(entity or "").strip().lower()
            if len(normalized) < 2:
                continue
            if normalized == symbol.name.lower() or normalized == symbol.qualified_name.lower():
                score += 40.0
                continue
            if normalized in text:
                score += 20.0

        evidence_kinds = {str(kind or "").strip().lower() for kind in preferred_evidence_kinds if str(kind or "").strip()}
        if "route_fact" in evidence_kinds and symbol.symbol_kind == "route":
            score += 18.0
        if "call_chain" in evidence_kinds and symbol.symbol_kind in {"route", "function", "method"}:
            score += 6.0
        if "state_assignment_fact" in evidence_kinds and (
            "create_app" in text or "app.state" in text or "state" in text
        ):
            score += 10.0
        return score

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
