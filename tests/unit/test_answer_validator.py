import pytest

from app.services.chat.answer_validator import AnswerValidator


@pytest.mark.asyncio
async def test_answer_validator_rejects_non_chinese_output():
    validator = AnswerValidator()

    result = await validator.validate(
        question="前端请求如何到后端？",
        answer="The backend entry is app/main.py",
        supplemental_notes=[],
        evidence_pack={
            "question": "前端请求如何到后端？",
            "planning_source": "llm",
            "call_chains": [],
            "key_findings": [],
            "citations": [],
            "gaps": [],
            "confidence_basis": [],
        },
    )

    assert result["passed"] is False
    assert "answer_not_chinese" in result["issues"]


@pytest.mark.asyncio
async def test_answer_validator_rejects_unsupported_entities():
    validator = AnswerValidator()

    result = await validator.validate(
        question="前端请求如何到后端？",
        answer="这个请求会进入 LearningOrchestrator，再交给 EventBroker 处理。",
        supplemental_notes=[],
        evidence_pack={
            "question": "前端请求如何到后端？",
            "planning_source": "llm",
            "call_chains": [],
            "key_findings": ["真实证据只提到 app/api/routes/tasks.py:task_chat"],
            "citations": [
                {
                    "kind": "citation",
                    "path": "app/api/routes/tasks.py",
                    "title": "task_chat",
                    "summary": "真实处理函数",
                    "start_line": 480,
                    "end_line": 510,
                    "snippet": "@router.post('/tasks/{task_id}/chat')\nasync def task_chat(task_id: str): ...",
                }
            ],
            "gaps": [],
            "confidence_basis": ["命中了真实代码片段"],
        },
    )

    assert result["passed"] is False
    assert "ungrounded_entity" in result["issues"]


@pytest.mark.asyncio
async def test_answer_validator_requires_evidence_disclosure_when_evidence_is_missing():
    validator = AnswerValidator()

    result = await validator.validate(
        question="登录流程具体怎么走？",
        answer="登录流程会先进入 app/auth/login.py，再调用 AuthService 完成认证。",
        supplemental_notes=[],
        evidence_pack={
            "question": "登录流程具体怎么走？",
            "planning_source": "llm",
            "call_chains": [],
            "entrypoints": [],
            "routes": [],
            "files": [],
            "symbols": [],
            "citations": [],
            "key_findings": [],
            "gaps": ["尚未定位登录调用链"],
            "confidence_basis": [],
        },
    )

    assert result["passed"] is False
    assert "missing_evidence_disclosure" in result["issues"]
