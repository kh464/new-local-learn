from app.services.chat.evidence_assembler import EvidenceAssembler
from app.services.chat.models import AgentObservation


def test_evidence_assembler_builds_findings_from_observations():
    assembler = EvidenceAssembler()

    pack = assembler.assemble(
        question="前端请求如何到后端？",
        planning_source="llm",
        observations=[
            AgentObservation(
                tool_name="trace_call_chain",
                success=True,
                summary="发现 1 条调用链",
                payload={
                    "chains": [
                        {
                            "summary": "web/src/services/api.ts -> POST /api/v1/tasks/{taskId}/chat -> app/api/routes/tasks.py:task_chat",
                            "backend_file": "app/api/routes/tasks.py",
                        }
                    ]
                },
            ),
            AgentObservation(
                tool_name="search_code",
                success=True,
                summary="命中 1 个代码片段",
                payload={
                    "hits": [
                        {
                            "path": "app/api/routes/tasks.py",
                            "start_line": 480,
                            "end_line": 510,
                            "summary": "task_chat route",
                            "snippet": "@router.post('/tasks/{task_id}/chat')",
                        }
                    ]
                },
            ),
        ],
    )

    assert pack.call_chains
    assert pack.citations
    assert pack.key_findings
    assert pack.confidence_basis
