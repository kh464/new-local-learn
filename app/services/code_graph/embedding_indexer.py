from __future__ import annotations

import hashlib

from app.services.code_graph.models import CodeFileNode, CodeSymbolNode, SemanticDocument
from app.services.code_graph.storage import CodeGraphStore
from app.services.vector_store.client import BaseVectorStore, VectorPoint


class EmbeddingIndexer:
    def __init__(
        self,
        *,
        embedding_client,
        vector_store: BaseVectorStore,
        graph_store: CodeGraphStore,
        collection_name: str = "repo_semantic_items",
        embedding_model: str,
    ) -> None:
        self._embedding_client = embedding_client
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._collection_name = collection_name
        self._embedding_model = embedding_model

    async def ensure_ready(self) -> None:
        ok = await self._vector_store.healthcheck()
        if not ok:
            raise RuntimeError("Vector store healthcheck failed.")

    async def index_documents(self, *, documents: list[SemanticDocument]) -> int:
        if not documents:
            return 0
        texts = [document.summary_zh for document in documents]
        embeddings = await self._embedding_client.embed_texts(texts, model=self._embedding_model)
        if len(embeddings) != len(documents):
            raise RuntimeError("Embedding result count does not match the number of documents.")
        if not embeddings or not embeddings[0]:
            raise RuntimeError("Embedding service returned empty vectors.")

        await self._vector_store.ensure_collection(name=self._collection_name, dimension=len(embeddings[0]))
        points: list[VectorPoint] = []
        for document, vector in zip(documents, embeddings, strict=False):
            point_id = self._point_id(document)
            payload = {
                "task_id": document.task_id,
                "item_id": document.item_id,
                "item_type": document.item_type,
                "path": document.path,
                "qualified_name": document.qualified_name,
                "language": document.language,
                "summary_zh": document.summary_zh,
                "tags": list(document.tags),
                "importance": document.importance,
            }
            points.append(VectorPoint(id=point_id, vector=list(vector), payload=payload))
        await self._vector_store.upsert(collection=self._collection_name, points=points)

        for document, point in zip(documents, points, strict=False):
            self._graph_store.register_embedding(
                task_id=document.task_id,
                item_type=document.item_type,
                item_ref_id=document.item_id,
                vector_store="qdrant",
                collection_name=self._collection_name,
                vector_point_id=point.id,
                embedding_model=self._embedding_model,
                content_hash=self._content_hash(document.summary_zh),
                status="ready",
            )
        return len(points)

    async def index_task_records(self, *, task_id: str) -> int:
        documents: list[SemanticDocument] = []
        for file_node in self._graph_store.list_files(task_id=task_id):
            if file_node.summary_zh.strip():
                documents.append(self.build_file_document(file_node=file_node))
        for symbol_node in self._graph_store.list_symbols(task_id=task_id):
            if symbol_node.summary_zh.strip():
                documents.append(self.build_symbol_document(symbol_node=symbol_node))
        return await self.index_documents(documents=documents)

    async def delete_task_documents(self, *, task_id: str) -> None:
        await self._vector_store.delete_by_filter(
            collection=self._collection_name,
            filters={"task_id": task_id},
        )

    def build_file_document(self, *, file_node: CodeFileNode) -> SemanticDocument:
        return SemanticDocument(
            task_id=file_node.task_id,
            item_id=file_node.path,
            item_type="file",
            path=file_node.path,
            qualified_name=None,
            summary_zh=self._compose_file_semantic_text(file_node),
            language=file_node.language,
            tags=[file_node.file_kind, *(["entry"] if file_node.entry_role else [])],
            importance=0.8 if file_node.entry_role else 0.5,
        )

    def build_symbol_document(self, *, symbol_node: CodeSymbolNode) -> SemanticDocument:
        return SemanticDocument(
            task_id=symbol_node.task_id,
            item_id=symbol_node.symbol_id,
            item_type="symbol",
            path=symbol_node.file_path,
            qualified_name=symbol_node.qualified_name,
            summary_zh=self._compose_symbol_semantic_text(symbol_node),
            language=symbol_node.language,
            tags=[symbol_node.symbol_kind],
            importance=0.7 if symbol_node.symbol_kind in {"route", "class", "method"} else 0.6,
        )

    def build_call_chain_document(self, *, task_id: str, chain_id: str, summary_zh: str, path: str | None = None) -> SemanticDocument:
        return SemanticDocument(
            task_id=task_id,
            item_id=chain_id,
            item_type="call_chain",
            path=path,
            qualified_name=chain_id,
            summary_zh=summary_zh,
            language="python",
            tags=["call_chain"],
            importance=0.9,
        )

    def _point_id(self, document: SemanticDocument) -> str:
        return hashlib.sha256(
            f"{document.task_id}:{document.item_type}:{document.item_id}".encode("utf-8")
        ).hexdigest()

    def _content_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _compose_file_semantic_text(self, file_node: CodeFileNode) -> str:
        parts = [
            file_node.summary_zh,
            file_node.responsibility_zh,
            file_node.upstream_zh,
            file_node.downstream_zh,
            f"关键词：{'、'.join(file_node.keywords_zh)}" if file_node.keywords_zh else "",
        ]
        return "\n".join(part for part in parts if part)

    def _compose_symbol_semantic_text(self, symbol_node: CodeSymbolNode) -> str:
        parts = [
            symbol_node.summary_zh,
            symbol_node.input_output_zh,
            symbol_node.side_effects_zh,
            symbol_node.call_targets_zh,
            symbol_node.callers_zh,
        ]
        return "\n".join(part for part in parts if part)


class EmbeddingIndexBuildService:
    def __init__(
        self,
        *,
        embedding_client,
        vector_store: BaseVectorStore,
        collection_name: str,
        embedding_model: str,
    ) -> None:
        self._embedding_client = embedding_client
        self._vector_store = vector_store
        self._collection_name = collection_name
        self._embedding_model = embedding_model

    async def build(self, *, task_id: str, db_path) -> int:
        graph_store = CodeGraphStore(db_path)
        indexer = EmbeddingIndexer(
            embedding_client=self._embedding_client,
            vector_store=self._vector_store,
            graph_store=graph_store,
            collection_name=self._collection_name,
            embedding_model=self._embedding_model,
        )
        return await indexer.index_task_records(task_id=task_id)
