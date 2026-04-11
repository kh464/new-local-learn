from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


_SQLITE_KNOWLEDGE_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS knowledge_document (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    language TEXT,
    size_bytes INTEGER NOT NULL,
    is_indexed INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task_id, path)
);

CREATE TABLE IF NOT EXISTS knowledge_chunk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    symbol_name TEXT,
    chunk_kind TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT NOT NULL,
    token_estimate INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(document_id) REFERENCES knowledge_document(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunk_fts USING fts5(
    task_id,
    path,
    symbol_name,
    summary,
    content
);

CREATE TABLE IF NOT EXISTS code_file (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    path TEXT NOT NULL,
    language TEXT NOT NULL,
    file_kind TEXT NOT NULL,
    summary_zh TEXT NOT NULL DEFAULT '',
    entry_role TEXT,
    responsibility_zh TEXT NOT NULL DEFAULT '',
    upstream_zh TEXT NOT NULL DEFAULT '',
    downstream_zh TEXT NOT NULL DEFAULT '',
    keywords_zh TEXT NOT NULL DEFAULT '[]',
    summary_source TEXT NOT NULL DEFAULT 'rule',
    summary_version INTEGER NOT NULL DEFAULT 0,
    summary_confidence TEXT NOT NULL DEFAULT 'low',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task_id, path)
);

CREATE TABLE IF NOT EXISTS code_symbol (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    symbol_id TEXT NOT NULL,
    symbol_kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    parent_symbol_id TEXT,
    signature TEXT,
    summary_zh TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL,
    input_output_zh TEXT NOT NULL DEFAULT '',
    side_effects_zh TEXT NOT NULL DEFAULT '',
    call_targets_zh TEXT NOT NULL DEFAULT '',
    callers_zh TEXT NOT NULL DEFAULT '',
    summary_source TEXT NOT NULL DEFAULT 'rule',
    summary_version INTEGER NOT NULL DEFAULT 0,
    summary_confidence TEXT NOT NULL DEFAULT 'low',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task_id, symbol_id)
);

CREATE TABLE IF NOT EXISTS code_edge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    from_symbol_id TEXT NOT NULL,
    to_symbol_id TEXT NOT NULL,
    edge_kind TEXT NOT NULL,
    source_path TEXT NOT NULL,
    line INTEGER,
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS code_unresolved_call (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    caller_symbol_id TEXT NOT NULL,
    callee_name TEXT NOT NULL,
    source_path TEXT NOT NULL,
    line INTEGER,
    raw_expr TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS embedding_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    item_ref_id TEXT NOT NULL,
    vector_store TEXT NOT NULL,
    collection_name TEXT NOT NULL,
    vector_point_id TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task_id, item_type, item_ref_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS code_file_fts USING fts5(
    task_id,
    path,
    summary_zh
);

CREATE VIRTUAL TABLE IF NOT EXISTS code_symbol_fts USING fts5(
    task_id,
    symbol_id,
    name,
    qualified_name,
    signature,
    summary_zh
);
"""


@dataclass(frozen=True)
class KnowledgeDocumentRecord:
    task_id: str
    path: str
    file_type: str
    language: str | None
    size_bytes: int
    is_indexed: bool


@dataclass(frozen=True)
class KnowledgeChunkRecord:
    task_id: str
    document_id: int
    chunk_index: int
    path: str
    start_line: int
    end_line: int
    symbol_name: str | None
    chunk_kind: str
    content: str
    summary: str
    token_estimate: int


@dataclass(frozen=True)
class KnowledgeSearchResult:
    chunk_id: int
    task_id: str
    path: str
    start_line: int
    end_line: int
    symbol_name: str | None
    chunk_kind: str
    content: str
    summary: str
    score: float


class SQLiteKnowledgeStore:
    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SQLITE_KNOWLEDGE_SCHEMA)

    def upsert_document(self, record: KnowledgeDocumentRecord) -> int:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_document(task_id, path, file_type, language, size_bytes, is_indexed)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, path) DO UPDATE SET
                    file_type = excluded.file_type,
                    language = excluded.language,
                    size_bytes = excluded.size_bytes,
                    is_indexed = excluded.is_indexed
                """,
                (
                    record.task_id,
                    record.path,
                    record.file_type,
                    record.language,
                    record.size_bytes,
                    1 if record.is_indexed else 0,
                ),
            )
            row = connection.execute(
                "SELECT id FROM knowledge_document WHERE task_id = ? AND path = ?",
                (record.task_id, record.path),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to load upserted knowledge document.")
            return int(row["id"])

    def insert_chunks(self, records: list[KnowledgeChunkRecord]) -> None:
        if not records:
            return
        with self._connect() as connection:
            for record in records:
                cursor = connection.execute(
                    """
                    INSERT INTO knowledge_chunk(
                        task_id, document_id, chunk_index, path, start_line, end_line,
                        symbol_name, chunk_kind, content, summary, token_estimate
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.task_id,
                        record.document_id,
                        record.chunk_index,
                        record.path,
                        record.start_line,
                        record.end_line,
                        record.symbol_name,
                        record.chunk_kind,
                        record.content,
                        record.summary,
                        record.token_estimate,
                    ),
                )
                chunk_id = cursor.lastrowid
                connection.execute(
                    """
                    INSERT INTO knowledge_chunk_fts(rowid, task_id, path, symbol_name, summary, content)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        record.task_id,
                        record.path,
                        record.symbol_name or "",
                        record.summary,
                        record.content,
                    ),
                )

    def search_chunks(self, query: str, *, task_id: str, limit: int = 8) -> list[KnowledgeSearchResult]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    kc.id,
                    kc.task_id,
                    kc.path,
                    kc.start_line,
                    kc.end_line,
                    kc.symbol_name,
                    kc.chunk_kind,
                    kc.content,
                    kc.summary,
                    bm25(knowledge_chunk_fts) AS score
                FROM knowledge_chunk_fts
                JOIN knowledge_chunk kc ON kc.id = knowledge_chunk_fts.rowid
                WHERE knowledge_chunk_fts MATCH ? AND kc.task_id = ?
                ORDER BY score
                LIMIT ?
                """,
                (normalized_query, task_id, max(limit, 1)),
            ).fetchall()
        return [
            KnowledgeSearchResult(
                chunk_id=int(row["id"]),
                task_id=str(row["task_id"]),
                path=str(row["path"]),
                start_line=int(row["start_line"]),
                end_line=int(row["end_line"]),
                symbol_name=str(row["symbol_name"]) if row["symbol_name"] is not None else None,
                chunk_kind=str(row["chunk_kind"]),
                content=str(row["content"]),
                summary=str(row["summary"]),
                score=float(row["score"]),
            )
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection
