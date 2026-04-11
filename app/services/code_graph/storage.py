from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSymbolNode, RetrievalCandidate, UnresolvedCall
from app.storage.knowledge_store import SQLiteKnowledgeStore


class CodeGraphStore:
    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

    def initialize(self) -> None:
        SQLiteKnowledgeStore(self._db_path).initialize()

    def has_graph_index(self, *, task_id: str) -> bool:
        required_tables = {"code_file", "code_symbol"}
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name IN ('code_file', 'code_symbol')
                """
            ).fetchall()
            existing_tables = {str(row["name"]) for row in rows}
            if not required_tables.issubset(existing_tables):
                return False
            count = connection.execute(
                """
                SELECT COUNT(*)
                FROM code_file
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        return bool(count is not None and int(count[0]) > 0)

    def upsert_files(self, files: list[CodeFileNode]) -> None:
        if not files:
            return
        with self._connect() as connection:
            for file_node in files:
                connection.execute(
                    """
                    INSERT INTO code_file(
                        task_id, path, language, file_kind, summary_zh, entry_role,
                        responsibility_zh, upstream_zh, downstream_zh, keywords_zh,
                        summary_source, summary_version, summary_confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id, path) DO UPDATE SET
                        language = excluded.language,
                        file_kind = excluded.file_kind,
                        summary_zh = excluded.summary_zh,
                        entry_role = excluded.entry_role,
                        responsibility_zh = excluded.responsibility_zh,
                        upstream_zh = excluded.upstream_zh,
                        downstream_zh = excluded.downstream_zh,
                        keywords_zh = excluded.keywords_zh,
                        summary_source = excluded.summary_source,
                        summary_version = excluded.summary_version,
                        summary_confidence = excluded.summary_confidence,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        file_node.task_id,
                        file_node.path,
                        file_node.language,
                        file_node.file_kind,
                        file_node.summary_zh,
                        file_node.entry_role,
                        file_node.responsibility_zh,
                        file_node.upstream_zh,
                        file_node.downstream_zh,
                        json.dumps(file_node.keywords_zh, ensure_ascii=False),
                        file_node.summary_source,
                        file_node.summary_version,
                        file_node.summary_confidence,
                    ),
                )
                self._upsert_file_fts(
                    connection,
                    task_id=file_node.task_id,
                    path=file_node.path,
                    summary_zh=file_node.summary_zh,
                )

    def upsert_symbols(self, symbols: list[CodeSymbolNode]) -> None:
        if not symbols:
            return
        with self._connect() as connection:
            for symbol in symbols:
                connection.execute(
                    """
                    INSERT INTO code_symbol(
                        task_id, symbol_id, symbol_kind, name, qualified_name, file_path,
                        start_line, end_line, parent_symbol_id, signature, summary_zh, language,
                        input_output_zh, side_effects_zh, call_targets_zh, callers_zh,
                        summary_source, summary_version, summary_confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id, symbol_id) DO UPDATE SET
                        symbol_kind = excluded.symbol_kind,
                        name = excluded.name,
                        qualified_name = excluded.qualified_name,
                        file_path = excluded.file_path,
                        start_line = excluded.start_line,
                        end_line = excluded.end_line,
                        parent_symbol_id = excluded.parent_symbol_id,
                        signature = excluded.signature,
                        summary_zh = excluded.summary_zh,
                        language = excluded.language,
                        input_output_zh = excluded.input_output_zh,
                        side_effects_zh = excluded.side_effects_zh,
                        call_targets_zh = excluded.call_targets_zh,
                        callers_zh = excluded.callers_zh,
                        summary_source = excluded.summary_source,
                        summary_version = excluded.summary_version,
                        summary_confidence = excluded.summary_confidence,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        symbol.task_id,
                        symbol.symbol_id,
                        symbol.symbol_kind,
                        symbol.name,
                        symbol.qualified_name,
                        symbol.file_path,
                        symbol.start_line,
                        symbol.end_line,
                        symbol.parent_symbol_id,
                        symbol.signature,
                        symbol.summary_zh,
                        symbol.language,
                        symbol.input_output_zh,
                        symbol.side_effects_zh,
                        symbol.call_targets_zh,
                        symbol.callers_zh,
                        symbol.summary_source,
                        symbol.summary_version,
                        symbol.summary_confidence,
                    ),
                )
                self._upsert_symbol_fts(
                    connection,
                    task_id=symbol.task_id,
                    symbol_id=symbol.symbol_id,
                    name=symbol.name,
                    qualified_name=symbol.qualified_name,
                    signature=symbol.signature or "",
                    summary_zh=symbol.summary_zh,
                )

    def insert_edges(self, edges: list[CodeEdge]) -> None:
        if not edges:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO code_edge(task_id, from_symbol_id, to_symbol_id, edge_kind, source_path, line, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        edge.task_id,
                        edge.from_symbol_id,
                        edge.to_symbol_id,
                        edge.edge_kind,
                        edge.source_path,
                        edge.line,
                        edge.confidence,
                    )
                    for edge in edges
                ],
            )

    def insert_unresolved_calls(self, calls: list[UnresolvedCall]) -> None:
        if not calls:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO code_unresolved_call(task_id, caller_symbol_id, callee_name, source_path, line, raw_expr)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        call.task_id,
                        call.caller_symbol_id,
                        call.callee_name,
                        call.source_path,
                        call.line,
                        call.raw_expr,
                    )
                    for call in calls
                ],
            )

    def update_file_summary(self, *, task_id: str, path: str, summary_zh: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE code_file
                SET summary_zh = ?, updated_at = CURRENT_TIMESTAMP
                WHERE task_id = ? AND path = ?
                """,
                (summary_zh, task_id, path),
            )
            self._upsert_file_fts(connection, task_id=task_id, path=path, summary_zh=summary_zh)

    def update_symbol_summary(self, *, task_id: str, symbol_id: str, summary_zh: str) -> None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT name, qualified_name, signature
                FROM code_symbol
                WHERE task_id = ? AND symbol_id = ?
                """,
                (task_id, symbol_id),
            ).fetchone()
            connection.execute(
                """
                UPDATE code_symbol
                SET summary_zh = ?, updated_at = CURRENT_TIMESTAMP
                WHERE task_id = ? AND symbol_id = ?
                """,
                (summary_zh, task_id, symbol_id),
            )
            if row is not None:
                self._upsert_symbol_fts(
                    connection,
                    task_id=task_id,
                    symbol_id=symbol_id,
                    name=str(row["name"]),
                    qualified_name=str(row["qualified_name"]),
                    signature=str(row["signature"] or ""),
                    summary_zh=summary_zh,
                )

    def list_files(self, *, task_id: str, language: str | None = None) -> list[CodeFileNode]:
        sql = """
            SELECT
                task_id, path, language, file_kind, summary_zh, entry_role,
                responsibility_zh, upstream_zh, downstream_zh, keywords_zh,
                summary_source, summary_version, summary_confidence
            FROM code_file
            WHERE task_id = ?
        """
        params: list[object] = [task_id]
        if language is not None:
            sql += " AND language = ?"
            params.append(language)
        sql += " ORDER BY path"
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [
            CodeFileNode(
                task_id=str(row["task_id"]),
                path=str(row["path"]),
                language=str(row["language"]),
                file_kind=str(row["file_kind"]),
                summary_zh=str(row["summary_zh"] or ""),
                entry_role=str(row["entry_role"]) if row["entry_role"] is not None else None,
                responsibility_zh=str(row["responsibility_zh"] or ""),
                upstream_zh=str(row["upstream_zh"] or ""),
                downstream_zh=str(row["downstream_zh"] or ""),
                keywords_zh=json.loads(str(row["keywords_zh"] or "[]")),
                summary_source=str(row["summary_source"] or "rule"),
                summary_version=int(row["summary_version"] or 0),
                summary_confidence=str(row["summary_confidence"] or "low"),
            )
            for row in rows
        ]

    def list_symbols(self, *, task_id: str, file_path: str | None = None, symbol_kind: str | None = None) -> list[CodeSymbolNode]:
        sql = """
            SELECT
                task_id, symbol_id, symbol_kind, name, qualified_name, file_path,
                start_line, end_line, parent_symbol_id, signature, summary_zh, language,
                input_output_zh, side_effects_zh, call_targets_zh, callers_zh,
                summary_source, summary_version, summary_confidence
            FROM code_symbol
            WHERE task_id = ?
        """
        params: list[object] = [task_id]
        if file_path is not None:
            sql += " AND file_path = ?"
            params.append(file_path)
        if symbol_kind is not None:
            sql += " AND symbol_kind = ?"
            params.append(symbol_kind)
        sql += " ORDER BY file_path, start_line, qualified_name"
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [
            CodeSymbolNode(
                task_id=str(row["task_id"]),
                symbol_id=str(row["symbol_id"]),
                symbol_kind=str(row["symbol_kind"]),
                name=str(row["name"]),
                qualified_name=str(row["qualified_name"]),
                file_path=str(row["file_path"]),
                start_line=int(row["start_line"]),
                end_line=int(row["end_line"]),
                parent_symbol_id=str(row["parent_symbol_id"]) if row["parent_symbol_id"] is not None else None,
                signature=str(row["signature"]) if row["signature"] is not None else None,
                summary_zh=str(row["summary_zh"] or ""),
                language=str(row["language"]),
                input_output_zh=str(row["input_output_zh"] or ""),
                side_effects_zh=str(row["side_effects_zh"] or ""),
                call_targets_zh=str(row["call_targets_zh"] or ""),
                callers_zh=str(row["callers_zh"] or ""),
                summary_source=str(row["summary_source"] or "rule"),
                summary_version=int(row["summary_version"] or 0),
                summary_confidence=str(row["summary_confidence"] or "low"),
            )
            for row in rows
        ]

    def list_out_edges(self, *, task_id: str, symbol_id: str, edge_kind: str | None = None) -> list[CodeEdge]:
        return self._list_edges(task_id=task_id, symbol_id=symbol_id, direction="out", edge_kind=edge_kind)

    def list_in_edges(self, *, task_id: str, symbol_id: str, edge_kind: str | None = None) -> list[CodeEdge]:
        return self._list_edges(task_id=task_id, symbol_id=symbol_id, direction="in", edge_kind=edge_kind)

    def search_files_fts(self, *, task_id: str, query: str, limit: int = 10) -> list[RetrievalCandidate]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    cf.task_id,
                    cf.path,
                    cf.summary_zh,
                    bm25(code_file_fts) AS score
                FROM code_file_fts
                JOIN code_file cf
                    ON cf.task_id = code_file_fts.task_id
                   AND cf.path = code_file_fts.path
                WHERE code_file_fts MATCH ? AND cf.task_id = ?
                ORDER BY score
                LIMIT ?
                """,
                (normalized_query, task_id, max(limit, 1)),
            ).fetchall()
        return [
            RetrievalCandidate(
                task_id=str(row["task_id"]),
                item_id=str(row["path"]),
                item_type="file",
                path=str(row["path"]),
                symbol_id=None,
                qualified_name=None,
                score=-float(row["score"]),
                source="exact",
                summary_zh=str(row["summary_zh"] or ""),
            )
            for row in rows
        ]

    def search_symbols_fts(self, *, task_id: str, query: str, limit: int = 10) -> list[RetrievalCandidate]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    cs.task_id,
                    cs.symbol_id,
                    cs.file_path,
                    cs.qualified_name,
                    cs.summary_zh,
                    bm25(code_symbol_fts) AS score
                FROM code_symbol_fts
                JOIN code_symbol cs
                    ON cs.task_id = code_symbol_fts.task_id
                   AND cs.symbol_id = code_symbol_fts.symbol_id
                WHERE code_symbol_fts MATCH ? AND cs.task_id = ?
                ORDER BY score
                LIMIT ?
                """,
                (normalized_query, task_id, max(limit, 1)),
            ).fetchall()
        return [
            RetrievalCandidate(
                task_id=str(row["task_id"]),
                item_id=str(row["symbol_id"]),
                item_type="symbol",
                path=str(row["file_path"]),
                symbol_id=str(row["symbol_id"]),
                qualified_name=str(row["qualified_name"]),
                score=-float(row["score"]),
                source="exact",
                summary_zh=str(row["summary_zh"] or ""),
            )
            for row in rows
        ]

    def register_embedding(
        self,
        *,
        task_id: str,
        item_type: str,
        item_ref_id: str,
        vector_store: str,
        collection_name: str,
        vector_point_id: str,
        embedding_model: str,
        content_hash: str,
        status: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO embedding_registry(
                    task_id, item_type, item_ref_id, vector_store, collection_name,
                    vector_point_id, embedding_model, content_hash, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, item_type, item_ref_id) DO UPDATE SET
                    vector_store = excluded.vector_store,
                    collection_name = excluded.collection_name,
                    vector_point_id = excluded.vector_point_id,
                    embedding_model = excluded.embedding_model,
                    content_hash = excluded.content_hash,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    task_id,
                    item_type,
                    item_ref_id,
                    vector_store,
                    collection_name,
                    vector_point_id,
                    embedding_model,
                    content_hash,
                    status,
                ),
            )

    def list_embedding_registry(self, *, task_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    task_id,
                    item_type,
                    item_ref_id,
                    vector_store,
                    collection_name,
                    vector_point_id,
                    embedding_model,
                    content_hash,
                    status
                FROM embedding_registry
                WHERE task_id = ?
                ORDER BY item_type, item_ref_id
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _list_edges(self, *, task_id: str, symbol_id: str, direction: str, edge_kind: str | None) -> list[CodeEdge]:
        column = "from_symbol_id" if direction == "out" else "to_symbol_id"
        sql = f"""
            SELECT task_id, from_symbol_id, to_symbol_id, edge_kind, source_path, line, confidence
            FROM code_edge
            WHERE task_id = ? AND {column} = ?
        """
        params: list[object] = [task_id, symbol_id]
        if edge_kind is not None:
            sql += " AND edge_kind = ?"
            params.append(edge_kind)
        sql += " ORDER BY source_path, line, id"
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [
            CodeEdge(
                task_id=str(row["task_id"]),
                from_symbol_id=str(row["from_symbol_id"]),
                to_symbol_id=str(row["to_symbol_id"]),
                edge_kind=str(row["edge_kind"]),
                source_path=str(row["source_path"]),
                line=int(row["line"]) if row["line"] is not None else None,
                confidence=float(row["confidence"]),
            )
            for row in rows
        ]

    def _upsert_file_fts(self, connection: sqlite3.Connection, *, task_id: str, path: str, summary_zh: str) -> None:
        connection.execute(
            "DELETE FROM code_file_fts WHERE task_id = ? AND path = ?",
            (task_id, path),
        )
        connection.execute(
            """
            INSERT INTO code_file_fts(task_id, path, summary_zh)
            VALUES (?, ?, ?)
            """,
            (task_id, path, summary_zh),
        )

    def _upsert_symbol_fts(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        symbol_id: str,
        name: str,
        qualified_name: str,
        signature: str,
        summary_zh: str,
    ) -> None:
        connection.execute(
            "DELETE FROM code_symbol_fts WHERE task_id = ? AND symbol_id = ?",
            (task_id, symbol_id),
        )
        connection.execute(
            """
            INSERT INTO code_symbol_fts(task_id, symbol_id, name, qualified_name, signature, summary_zh)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, symbol_id, name, qualified_name, signature, summary_zh),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection
