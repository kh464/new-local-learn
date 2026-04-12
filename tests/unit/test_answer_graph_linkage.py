from app.services.chat.models import EvidenceItem, EvidencePack


def test_answer_debug_contains_related_graph_node_ids():
    from app.services.chat.orchestrator import TaskChatOrchestrator

    orchestrator = TaskChatOrchestrator(
        planning_agent=None,
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=None,
        answer_composer=None,
        answer_validator=None,
    )

    debug = orchestrator._build_answer_debug(
        EvidencePack(
            question="说明健康检查主链路",
            planning_source="hybrid_rag",
            call_chains=[
                EvidenceItem(
                    kind="call_chain",
                    title="app.main.health -> app.services.health.build_payload",
                    node_ids=[
                        "function:python:app/main.py:app.main.health",
                        "function:python:app/services/health.py:app.services.health.build_payload",
                    ],
                )
            ],
            symbols=[
                EvidenceItem(
                    kind="symbol",
                    title="app.main.health",
                    node_ids=["function:python:app/main.py:app.main.health"],
                )
            ],
            key_findings=["已确认 health 会调用 build_payload"],
        )
    )

    assert debug is not None
    assert debug.related_node_ids == [
        "function:python:app/main.py:app.main.health",
        "function:python:app/services/health.py:app.services.health.build_payload",
    ]
