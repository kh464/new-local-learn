from __future__ import annotations

from dataclasses import dataclass, field

from app.services.code_graph.graph_expander import ExpandedSubgraph
from app.services.code_graph.models import CodeSnippetEvidence, RetrievalCandidate


@dataclass(frozen=True)
class EvidencePack:
    question: str
    normalized_question: str
    retrieval_objective: str
    seeds: list[RetrievalCandidate] = field(default_factory=list)
    snippets: list[CodeSnippetEvidence] = field(default_factory=list)
    graph_nodes: list[dict[str, object]] = field(default_factory=list)
    graph_edges: list[dict[str, object]] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)


class GraphEvidenceBuilder:
    def build(
        self,
        *,
        question: str,
        normalized_question: str,
        retrieval_objective: str,
        subgraph: ExpandedSubgraph,
        snippets: list[CodeSnippetEvidence],
    ) -> EvidencePack:
        graph_nodes = [
            {
                "kind": "file",
                "node_id": f"file:{file.language}:{file.path}",
                "path": file.path,
                "language": file.language,
                "summary_zh": file.summary_zh,
                "entry_role": file.entry_role,
            }
            for file in subgraph.files
        ] + [
            {
                "kind": symbol.symbol_kind,
                "node_id": symbol.symbol_id,
                "symbol_id": symbol.symbol_id,
                "name": symbol.name,
                "qualified_name": symbol.qualified_name,
                "path": symbol.file_path,
                "start_line": symbol.start_line,
                "end_line": symbol.end_line,
                "summary_zh": symbol.summary_zh,
                "language": symbol.language,
            }
            for symbol in subgraph.symbols
        ]
        graph_edges = [
            {
                "kind": edge.edge_kind,
                "from": edge.from_symbol_id,
                "to": edge.to_symbol_id,
                "path": edge.source_path,
                "line": edge.line,
            }
            for edge in subgraph.edges
        ]
        summaries = [seed.summary_zh for seed in subgraph.seeds if seed.summary_zh]
        return EvidencePack(
            question=question,
            normalized_question=normalized_question,
            retrieval_objective=retrieval_objective,
            seeds=subgraph.seeds,
            snippets=snippets,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            summaries=summaries,
        )
