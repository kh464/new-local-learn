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


@pytest.mark.asyncio
async def test_answer_validator_requires_must_include_entities_when_evidence_exists():
    validator = AnswerValidator()

    result = await validator.validate(
        question="说明任务提交后的主链路",
        answer="当前主链路会进入任务队列的 submit 方法。",
        supplemental_notes=[],
        evidence_pack={
            "question": "说明任务提交后的主链路",
            "planning_source": "hybrid_rag",
            "question_type": "architecture_explanation",
            "retrieval_objective": "定位任务提交入口及下游主调用链",
            "must_include_entities": ["enqueue_turn_task"],
            "preferred_evidence_kinds": ["call_chain", "symbol"],
            "call_chains": [
                {
                    "kind": "call_chain",
                    "path": "app/main.py",
                    "title": "app.main.create_app.enqueue_turn_task -> app.task_queue.InMemoryTaskQueue.submit",
                    "summary": "主任务提交入口调用任务入队。",
                }
            ],
            "symbols": [
                {
                    "kind": "symbol",
                    "path": "app/main.py",
                    "title": "app.main.create_app.enqueue_turn_task",
                    "summary": "主任务提交入口。",
                }
            ],
            "key_findings": ["已确认主链路涉及 enqueue_turn_task。"],
            "citations": [],
            "gaps": [],
            "confidence_basis": ["已命中主调用链。"],
        },
    )

    assert result["passed"] is False
    assert "missing_must_include_entity" in result["issues"]


@pytest.mark.asyncio
async def test_answer_validator_allows_helm_templates_directory_derived_from_template_file_paths():
    validator = AnswerValidator()

    result = await validator.validate(
        question="Helm Chart 模板放在哪个目录？",
        answer="Helm Chart 模板目录在 ops/helm/learn-new/templates。",
        supplemental_notes=[],
        evidence_pack={
            "question": "Helm Chart 模板放在哪个目录？",
            "planning_source": "hybrid_rag",
            "files": [
                {
                    "kind": "file",
                    "path": "ops/helm/learn-new/templates/configmap.yaml",
                    "title": "ops/helm/learn-new/templates/configmap.yaml",
                    "summary": "Helm 模板文件",
                }
            ],
            "citations": [
                {
                    "kind": "citation",
                    "path": "ops/helm/learn-new/templates/configmap.yaml",
                    "title": "ops/helm/learn-new/templates/configmap.yaml",
                    "summary": "Helm 模板文件",
                    "start_line": 1,
                    "end_line": 5,
                    "snippet": "apiVersion: v1\nkind: ConfigMap\n",
                }
            ],
            "key_findings": ["已命中 Helm 模板文件。"],
            "gaps": [],
            "confidence_basis": ["命中了模板文件路径。"],
        },
    )

    assert result["passed"] is True
    assert result["issues"] == []
