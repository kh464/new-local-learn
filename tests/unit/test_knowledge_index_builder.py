from __future__ import annotations

import sqlite3

from app.services.knowledge.index_builder import KnowledgeIndexBuilder


def test_knowledge_index_builder_indexes_source_and_config_files_only(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app").mkdir(parents=True)
    (repo_path / "web").mkdir(parents=True)
    (repo_path / "dist").mkdir(parents=True)
    (repo_path / "node_modules" / "demo").mkdir(parents=True)

    (repo_path / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\nasync def health():\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    (repo_path / "web" / "App.vue").write_text(
        "<script setup lang=\"ts\">\nconst endpoint = '/health'\n</script>\n<template><div>Health</div></template>\n",
        encoding="utf-8",
    )
    (repo_path / "docker-compose.yml").write_text(
        "services:\n  api:\n    build: .\n    ports:\n      - \"8000:8000\"\n",
        encoding="utf-8",
    )
    (repo_path / "README.md").write_text("# should not be indexed\n", encoding="utf-8")
    (repo_path / "dist" / "bundle.js").write_text("console.log('skip build output')\n", encoding="utf-8")
    (repo_path / "node_modules" / "demo" / "index.js").write_text("export const x = 1\n", encoding="utf-8")
    (repo_path / "app" / "huge.py").write_text("x = 1\n" * 4000, encoding="utf-8")

    db_path = tmp_path / "knowledge.db"
    result = KnowledgeIndexBuilder(max_file_bytes=2_000).build(
        task_id="task-index-1",
        repo_path=repo_path,
        db_path=db_path,
    )

    assert result.indexed_documents == 3
    assert result.indexed_chunks >= 3
    assert sorted(result.skipped_paths) == [
        "README.md",
        "app/huge.py",
        "dist/bundle.js",
        "node_modules/demo/index.js",
    ]

    with sqlite3.connect(db_path) as connection:
        indexed_paths = [
            row[0]
            for row in connection.execute(
                "SELECT path FROM knowledge_document WHERE task_id = ? AND is_indexed = 1 ORDER BY path",
                ("task-index-1",),
            ).fetchall()
        ]

    assert indexed_paths == [
        "app/main.py",
        "docker-compose.yml",
        "web/App.vue",
    ]


def test_knowledge_index_builder_tracks_chunk_line_ranges_for_search_results(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app").mkdir(parents=True)
    lines = [f"# line {index}" for index in range(1, 25)]
    lines.extend(
        [
            "def target_handler():",
            "    payload = 'target-marker'",
            "    return payload",
        ]
    )
    lines.extend(f"# trailer {index}" for index in range(1, 25))
    (repo_path / "app" / "service.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

    db_path = tmp_path / "knowledge.db"
    KnowledgeIndexBuilder(chunk_size_lines=20, chunk_overlap_lines=5).build(
        task_id="task-index-2",
        repo_path=repo_path,
        db_path=db_path,
    )

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT kc.start_line, kc.end_line, kc.content
            FROM knowledge_chunk_fts
            JOIN knowledge_chunk kc ON kc.id = knowledge_chunk_fts.rowid
            WHERE knowledge_chunk_fts MATCH ? AND kc.task_id = ?
            ORDER BY bm25(knowledge_chunk_fts)
            LIMIT 1
            """,
            ("target_handler", "task-index-2"),
        ).fetchone()

    assert row is not None
    assert row[0] <= 25 <= row[1]
    assert "target-marker" in row[2]


def test_knowledge_index_builder_skips_temp_dirs_and_nested_repositories(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app").mkdir(parents=True)
    (repo_path / "tmpbase" / "noise").mkdir(parents=True)
    (repo_path / "nested-ui").mkdir(parents=True)

    (repo_path / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (repo_path / "tmpbase" / "noise" / "demo.py").write_text("def noisy():\n    return True\n", encoding="utf-8")
    (repo_path / "nested-ui" / ".git").write_text("gitdir: ../.git/worktrees/nested-ui\n", encoding="utf-8")
    (repo_path / "nested-ui" / "App.tsx").write_text("export function App() { return null }\n", encoding="utf-8")

    db_path = tmp_path / "knowledge.db"
    result = KnowledgeIndexBuilder().build(
        task_id="task-index-3",
        repo_path=repo_path,
        db_path=db_path,
    )

    assert result.indexed_documents == 1
    assert "tmpbase/noise/demo.py" in result.skipped_paths
    assert "nested-ui/App.tsx" in result.skipped_paths


def test_knowledge_index_builder_skips_test_directories_and_spec_files(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app").mkdir(parents=True)
    (repo_path / "tests").mkdir(parents=True)
    (repo_path / "web" / "src").mkdir(parents=True)

    (repo_path / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (repo_path / "tests" / "test_api.py").write_text("def test_api():\n    assert True\n", encoding="utf-8")
    (repo_path / "web" / "src" / "api.spec.ts").write_text("export const noisy = true\n", encoding="utf-8")

    db_path = tmp_path / "knowledge.db"
    result = KnowledgeIndexBuilder().build(
        task_id="task-index-4",
        repo_path=repo_path,
        db_path=db_path,
    )

    assert result.indexed_documents == 1
    assert "tests/test_api.py" in result.skipped_paths
    assert "web/src/api.spec.ts" in result.skipped_paths
