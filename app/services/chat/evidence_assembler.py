from __future__ import annotations

from app.services.chat.models import AgentObservation, EvidenceItem, EvidencePack


class EvidenceAssembler:
    def assemble(
        self,
        *,
        question: str,
        planning_source: str,
        observations: list[AgentObservation],
    ) -> EvidencePack:
        entrypoints: list[EvidenceItem] = []
        call_chains: list[EvidenceItem] = []
        routes: list[EvidenceItem] = []
        files: list[EvidenceItem] = []
        symbols: list[EvidenceItem] = []
        citations: list[EvidenceItem] = []
        key_findings: list[str] = []
        confidence_basis: list[str] = []

        for observation in observations:
            if not observation.success:
                continue

            payload = observation.payload

            for chain in payload.get("chains", []) or payload.get("call_chains", []):
                summary = chain["summary"] if isinstance(chain, dict) else str(chain)
                path = str(chain.get("backend_file") or chain.get("frontend_file") or "") if isinstance(chain, dict) else ""
                call_chains.append(
                    EvidenceItem(
                        kind="call_chain",
                        title=summary,
                        summary=summary,
                        path=path,
                        node_ids=[f"file:{path}"] if path else [],
                    )
                )
                key_findings.append(f"已确认调用链：{summary}")

            entrypoint_payload = payload.get("entrypoints") or {}
            if isinstance(entrypoint_payload, dict):
                for layer, item in entrypoint_payload.items():
                    if not isinstance(item, dict):
                        continue
                    title = f"{layer} 入口"
                    path = str(item.get("file_path") or "")
                    detail = f"语言: {item.get('language')}" if item.get("language") else ""
                    entrypoints.append(
                        EvidenceItem(
                            kind="entrypoint",
                            title=title,
                            summary=detail,
                            path=path,
                            node_ids=[f"file:{path}"] if path else [],
                        )
                    )

            for hit in payload.get("hits", []):
                if not isinstance(hit, dict):
                    continue
                path = str(hit.get("path") or "")
                summary = str(hit.get("summary") or "")
                citations.append(
                    EvidenceItem(
                        kind="citation",
                        title=summary or path,
                        summary=summary,
                        path=path,
                        start_line=hit.get("start_line"),
                        end_line=hit.get("end_line"),
                        snippet=str(hit.get("snippet") or ""),
                        node_ids=[f"file:{path}"] if path else [],
                    )
                )
                if path:
                    files.append(
                        EvidenceItem(
                            kind="file",
                            title=path,
                            summary=summary,
                            path=path,
                            node_ids=[f"file:{path}"],
                        )
                    )
                symbol_name = str(hit.get("symbol_name") or hit.get("symbol") or "").strip()
                if symbol_name:
                    symbols.append(
                        EvidenceItem(
                            kind="symbol",
                            title=symbol_name,
                            summary=summary,
                            path=path,
                            node_ids=[f"file:{path}"] if path else [],
                        )
                    )

            for route in payload.get("routes", []):
                if not isinstance(route, dict):
                    continue
                method = str(route.get("method") or "")
                route_path = str(route.get("path") or route.get("route_path") or "")
                title = f"{method} {route_path}".strip()
                routes.append(
                    EvidenceItem(
                        kind="route",
                        title=title,
                        summary=str(route.get("summary") or title),
                        path=str(route.get("source_file") or ""),
                        node_ids=[f"file:{str(route.get('source_file') or '')}"] if route.get("source_file") else [],
                    )
                )

            confidence_basis.append(f"命中工具结果：{observation.tool_name}")

        return EvidencePack(
            question=question,
            planning_source=planning_source,
            entrypoints=entrypoints,
            call_chains=call_chains,
            routes=routes,
            files=files,
            symbols=symbols,
            citations=citations,
            key_findings=key_findings,
            reasoning_steps=["先整理 MCP 工具返回的证据，再生成回答。"],
            gaps=[],
            confidence_basis=confidence_basis,
        )
