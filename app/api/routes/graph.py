from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.routes.tasks import get_settings, get_task_store
from app.core.config import Settings
from app.core.models import TaskGraphEdgePayload, TaskGraphNodePayload, TaskGraphPayload, TaskKnowledgeState, TaskState
from app.core.security import require_task_access
from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSymbolNode
from app.services.code_graph.storage import CodeGraphStore
from app.storage.artifacts import ArtifactPaths
from app.storage.task_store import RedisTaskStore

router = APIRouter()


@router.get("/tasks/{task_id}/graph", response_model=TaskGraphPayload)
async def get_task_graph(
    task_id: str,
    request: Request,
    view: str = Query(default="repository"),
    symbol_id: str | None = Query(default=None),
    path: str | None = Query(default=None),
    store: RedisTaskStore = Depends(get_task_store),
    settings: Settings = Depends(get_settings),
) -> TaskGraphPayload:
    await require_task_access(request, task_id, settings, store)
    status_payload = await store.get_status(task_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if status_payload.state is not TaskState.SUCCEEDED or status_payload.knowledge_state is not TaskKnowledgeState.READY:
        raise HTTPException(status_code=409, detail="Task graph is available only after the knowledge base is ready.")

    artifacts = ArtifactPaths(base_dir=settings.artifacts_dir, task_id=task_id)
    db_path = artifacts.knowledge_db_path
    if not db_path.is_file():
        raise HTTPException(status_code=404, detail="Task knowledge base not found.")

    graph_store = CodeGraphStore(db_path)
    if not graph_store.has_graph_index(task_id=task_id):
        raise HTTPException(status_code=404, detail="Task graph index not found.")

    normalized_view = (view or "repository").strip().lower()
    if normalized_view not in {"repository", "symbol", "module"}:
        raise HTTPException(status_code=400, detail="Unsupported graph view.")

    files = graph_store.list_files(task_id=task_id)
    symbols = graph_store.list_symbols(task_id=task_id)
    edges = _list_all_edges(graph_store=graph_store, task_id=task_id, symbols=symbols)

    if normalized_view == "repository":
        return _build_repository_graph(task_id=task_id, files=files, symbols=symbols, edges=edges)
    if normalized_view == "symbol":
        if not symbol_id:
            raise HTTPException(status_code=400, detail="symbol_id is required for symbol view.")
        return _build_symbol_graph(task_id=task_id, symbol_id=symbol_id, files=files, symbols=symbols, edges=edges)
    return _build_module_graph(task_id=task_id, path=path, files=files, symbols=symbols, edges=edges)


def _build_repository_graph(
    *,
    task_id: str,
    files: list[CodeFileNode],
    symbols: list[CodeSymbolNode],
    edges: list[CodeEdge],
) -> TaskGraphPayload:
    file_nodes = [_file_to_payload(file_node=file_node) for file_node in files]
    symbol_nodes = [_symbol_to_payload(symbol=symbol) for symbol in symbols]
    contains_edges = [_contains_edge(symbol.file_path, symbol.symbol_id) for symbol in symbols]
    code_edges = [_edge_to_payload(edge=edge) for edge in edges]
    return TaskGraphPayload(
        task_id=task_id,
        view="repository",
        nodes=[*file_nodes, *symbol_nodes],
        edges=[*contains_edges, *code_edges],
    )


def _build_symbol_graph(
    *,
    task_id: str,
    symbol_id: str,
    files: list[CodeFileNode],
    symbols: list[CodeSymbolNode],
    edges: list[CodeEdge],
) -> TaskGraphPayload:
    symbol_by_id = {symbol.symbol_id: symbol for symbol in symbols}
    focus_symbol = symbol_by_id.get(symbol_id)
    if focus_symbol is None:
        raise HTTPException(status_code=404, detail="Requested symbol was not found.")

    selected_edges = [
        edge for edge in edges if edge.from_symbol_id == symbol_id or edge.to_symbol_id == symbol_id
    ]
    selected_symbol_ids = {symbol_id}
    selected_file_paths = {focus_symbol.file_path}
    if focus_symbol.parent_symbol_id:
        selected_symbol_ids.add(focus_symbol.parent_symbol_id)

    for edge in selected_edges:
        selected_symbol_ids.add(edge.from_symbol_id)
        selected_symbol_ids.add(edge.to_symbol_id)

    for selected_id in list(selected_symbol_ids):
        symbol = symbol_by_id.get(selected_id)
        if symbol is not None:
            selected_file_paths.add(symbol.file_path)

    node_payloads = [
        _file_to_payload(file_node=file_node)
        for file_node in files
        if file_node.path in selected_file_paths
    ]
    node_payloads.extend(
        _symbol_to_payload(symbol=symbol_by_id[selected_id], focus_node_id=symbol_id)
        for selected_id in selected_symbol_ids
        if selected_id in symbol_by_id
    )
    edge_payloads = [
        _contains_edge(symbol_by_id[selected_id].file_path, selected_id)
        for selected_id in selected_symbol_ids
        if selected_id in symbol_by_id
    ]
    edge_payloads.extend(_edge_to_payload(edge=edge) for edge in selected_edges)

    return TaskGraphPayload(
        task_id=task_id,
        view="symbol",
        focus_node_id=symbol_id,
        nodes=node_payloads,
        edges=edge_payloads,
    )


def _build_module_graph(
    *,
    task_id: str,
    path: str | None,
    files: list[CodeFileNode],
    symbols: list[CodeSymbolNode],
    edges: list[CodeEdge],
) -> TaskGraphPayload:
    focus_path = (path or "").strip()
    if not focus_path and files:
        focus_path = files[0].path
    focus_file = next((file_node for file_node in files if file_node.path == focus_path), None)
    if focus_file is None:
        raise HTTPException(status_code=404, detail="Requested module was not found.")

    module_symbols = [symbol for symbol in symbols if symbol.file_path == focus_file.path]
    module_symbol_ids = {symbol.symbol_id for symbol in module_symbols}
    module_edges = [
        edge
        for edge in edges
        if edge.from_symbol_id in module_symbol_ids or edge.to_symbol_id in module_symbol_ids
    ]
    linked_symbol_ids = set(module_symbol_ids)
    linked_file_paths = {focus_file.path}
    symbol_by_id = {symbol.symbol_id: symbol for symbol in symbols}
    for edge in module_edges:
        linked_symbol_ids.add(edge.from_symbol_id)
        linked_symbol_ids.add(edge.to_symbol_id)
    for selected_id in list(linked_symbol_ids):
        symbol = symbol_by_id.get(selected_id)
        if symbol is not None:
            linked_file_paths.add(symbol.file_path)

    node_payloads = [
        _file_to_payload(file_node=file_node, focus_path=focus_file.path)
        for file_node in files
        if file_node.path in linked_file_paths
    ]
    node_payloads.extend(
        _symbol_to_payload(symbol=symbol_by_id[selected_id])
        for selected_id in linked_symbol_ids
        if selected_id in symbol_by_id
    )
    edge_payloads = [
        _contains_edge(symbol_by_id[selected_id].file_path, selected_id)
        for selected_id in linked_symbol_ids
        if selected_id in symbol_by_id
    ]
    edge_payloads.extend(_edge_to_payload(edge=edge) for edge in module_edges)

    return TaskGraphPayload(
        task_id=task_id,
        view="module",
        focus_node_id=f"file:{focus_file.path}",
        nodes=node_payloads,
        edges=edge_payloads,
    )


def _list_all_edges(*, graph_store: CodeGraphStore, task_id: str, symbols: list[CodeSymbolNode]) -> list[CodeEdge]:
    seen: set[tuple[str, str, str, str, int | None]] = set()
    collected: list[CodeEdge] = []
    for symbol in symbols:
        for edge in graph_store.list_out_edges(task_id=task_id, symbol_id=symbol.symbol_id):
            key = (edge.from_symbol_id, edge.to_symbol_id, edge.edge_kind, edge.source_path, edge.line)
            if key in seen:
                continue
            seen.add(key)
            collected.append(edge)
    return collected


def _file_to_payload(*, file_node: CodeFileNode, focus_path: str | None = None) -> TaskGraphNodePayload:
    return TaskGraphNodePayload(
        node_id=f"file:{file_node.path}",
        kind="file",
        label=file_node.path,
        path=file_node.path,
        summary=file_node.summary_zh,
        language=file_node.language,
        file_kind=file_node.file_kind,
        is_focus=focus_path == file_node.path,
    )


def _symbol_to_payload(*, symbol: CodeSymbolNode, focus_node_id: str | None = None) -> TaskGraphNodePayload:
    return TaskGraphNodePayload(
        node_id=symbol.symbol_id,
        kind="symbol",
        label=symbol.qualified_name,
        path=symbol.file_path,
        summary=symbol.summary_zh,
        language=symbol.language,
        symbol_kind=symbol.symbol_kind,
        qualified_name=symbol.qualified_name,
        parent_node_id=symbol.parent_symbol_id or f"file:{symbol.file_path}",
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        is_focus=focus_node_id == symbol.symbol_id,
    )


def _contains_edge(file_path: str, symbol_id: str) -> TaskGraphEdgePayload:
    return TaskGraphEdgePayload(
        from_node_id=f"file:{file_path}",
        to_node_id=symbol_id,
        kind="contains",
        path=file_path,
        confidence=1.0,
    )


def _edge_to_payload(*, edge: CodeEdge) -> TaskGraphEdgePayload:
    return TaskGraphEdgePayload(
        from_node_id=edge.from_symbol_id,
        to_node_id=edge.to_symbol_id,
        kind=edge.edge_kind,
        path=edge.source_path,
        line=edge.line,
        confidence=edge.confidence,
    )
