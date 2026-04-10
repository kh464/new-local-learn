from __future__ import annotations

from app.services.knowledge.retriever import KnowledgeRetriever
from app.storage.knowledge_store import KnowledgeChunkRecord, KnowledgeDocumentRecord, SQLiteKnowledgeStore


def test_knowledge_retriever_prioritizes_direct_path_hits(tmp_path):
    db_path = _build_knowledge_db(tmp_path)

    results = KnowledgeRetriever().retrieve(
        task_id="task-retrieval-1",
        db_path=db_path,
        question="请解释 app/main.py 这个后端入口文件",
        limit=3,
    )

    assert results
    assert results[0].path == "app/main.py"


def test_knowledge_retriever_applies_frontend_file_type_weighting(tmp_path):
    db_path = _build_knowledge_db(tmp_path)

    results = KnowledgeRetriever().retrieve(
        task_id="task-retrieval-1",
        db_path=db_path,
        question="前端页面是在哪里发起 /health 接口调用的？",
        limit=3,
    )

    assert results
    assert results[0].path == "web/App.vue"
    assert "/health" in results[0].content


def test_knowledge_retriever_falls_back_to_config_search_terms_for_chinese_questions(tmp_path):
    db_path = _build_knowledge_db(tmp_path)

    results = KnowledgeRetriever().retrieve(
        task_id="task-retrieval-1",
        db_path=db_path,
        question="docker 部署应该看哪里",
        limit=3,
    )

    assert results
    assert results[0].path == "docker-compose.yml"


def _build_knowledge_db(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(db_path)
    store.initialize()

    app_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-retrieval-1",
            path="app/main.py",
            file_type="source",
            language="python",
            size_bytes=120,
            is_indexed=True,
        )
    )
    web_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-retrieval-1",
            path="web/App.vue",
            file_type="source",
            language="vue",
            size_bytes=120,
            is_indexed=True,
        )
    )
    deploy_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-retrieval-1",
            path="docker-compose.yml",
            file_type="config",
            language="yaml",
            size_bytes=120,
            is_indexed=True,
        )
    )
    store.insert_chunks(
        [
            KnowledgeChunkRecord(
                task_id="task-retrieval-1",
                document_id=app_doc,
                chunk_index=0,
                path="app/main.py",
                start_line=1,
                end_line=8,
                symbol_name="health",
                chunk_kind="function",
                content="from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\nasync def health():\n    return {'ok': True}\n",
                summary="app/main.py backend entry FastAPI health",
                token_estimate=24,
            ),
            KnowledgeChunkRecord(
                task_id="task-retrieval-1",
                document_id=web_doc,
                chunk_index=0,
                path="web/App.vue",
                start_line=1,
                end_line=10,
                symbol_name="App",
                chunk_kind="component",
                content="<script setup>\nconst loadHealth = async () => fetch('/health')\n</script>\n",
                summary="web/App.vue frontend component fetch health",
                token_estimate=18,
            ),
            KnowledgeChunkRecord(
                task_id="task-retrieval-1",
                document_id=deploy_doc,
                chunk_index=0,
                path="docker-compose.yml",
                start_line=1,
                end_line=8,
                symbol_name="services",
                chunk_kind="config",
                content="services:\n  api:\n    build: .\n    ports:\n      - '8000:8000'\n",
                summary="docker compose deployment service api",
                token_estimate=16,
            ),
        ]
    )
    return db_path
