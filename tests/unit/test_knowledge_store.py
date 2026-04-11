from __future__ import annotations

import sqlite3

from app.storage.knowledge_store import KnowledgeChunkRecord, KnowledgeDocumentRecord, SQLiteKnowledgeStore


def test_sqlite_knowledge_store_persists_documents_chunks_and_fts_search(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(db_path)
    store.initialize()

    document_id = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-knowledge-1",
            path="app/main.py",
            file_type="source",
            language="python",
            size_bytes=128,
            is_indexed=True,
        )
    )
    store.insert_chunks(
        [
            KnowledgeChunkRecord(
                task_id="task-knowledge-1",
                document_id=document_id,
                chunk_index=0,
                path="app/main.py",
                start_line=1,
                end_line=8,
                symbol_name="health",
                chunk_kind="function",
                content="from fastapi import FastAPI\n\n@app.get('/health')\nasync def health():\n    return {'ok': True}\n",
                summary="FastAPI 健康检查路由",
                token_estimate=32,
            )
        ]
    )

    results = store.search_chunks("health FastAPI", task_id="task-knowledge-1", limit=5)

    assert db_path.is_file() is True
    assert len(results) == 1
    assert results[0].path == "app/main.py"
    assert results[0].start_line == 1
    assert "FastAPI" in results[0].content


def test_sqlite_knowledge_store_initializes_code_graph_tables(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(db_path)

    store.initialize()

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()

    object_names = {row[0] for row in rows}
    assert "code_file" in object_names
    assert "code_symbol" in object_names
    assert "code_edge" in object_names
    assert "code_unresolved_call" in object_names
    assert "embedding_registry" in object_names
