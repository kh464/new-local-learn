from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.services.knowledge.repo_map_loader import RepoMapLoader
from app.services.knowledge.retriever import KnowledgeRetriever


class _TaskStoreProtocol(Protocol):
    async def get_chat_messages(self, task_id: str): ...


class RepositoryQaToolSession:
    _MAX_REPO_MAP_SYMBOLS = 10
    _MAX_REPO_MAP_EDGES = 10
    _MAX_REPO_MAP_CALL_CHAINS = 5
    _MAX_OPEN_FILE_LINES = 80
    _MAX_SNIPPET_CHARS = 4000
    _TOOL_DEFINITIONS = [
        {
            "name": "search_code",
            "description": "Search indexed code snippets from the task knowledge database.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
        {
            "name": "load_repo_map",
            "description": "Load the read-only repository map for the current task.",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "trace_call_chain",
            "description": "Trace frontend/backend request chains from the repository map by query or entrypoint.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "entry": {"type": "string"},
                },
            },
        },
        {
            "name": "open_file",
            "description": "Open a file snippet by repository path or symbol name.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "symbol": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
            },
        },
        {
            "name": "read_history",
            "description": "Read recent task chat history summaries for the current task.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
            },
        },
    ]

    def __init__(
        self,
        *,
        task_id: str,
        repo_root: Path | str,
        repo_map_path: Path | str,
        knowledge_db_path: Path | str,
        task_store: _TaskStoreProtocol | None,
        repo_map_loader: RepoMapLoader | None = None,
        retriever: KnowledgeRetriever | None = None,
    ) -> None:
        self._task_id = task_id
        self._repo_root = Path(repo_root)
        self._repo_map_path = Path(repo_map_path)
        self._knowledge_db_path = Path(knowledge_db_path)
        self._task_store = task_store
        self._repo_map_loader = repo_map_loader or RepoMapLoader()
        self._retriever = retriever or KnowledgeRetriever()

    async def list_tools(self) -> list[dict[str, object]]:
        return [dict(tool) for tool in self._TOOL_DEFINITIONS]

    async def call_tool(self, name: str, arguments: dict[str, object] | None = None) -> dict[str, object]:
        normalized_arguments = arguments or {}
        handlers = {
            "search_code": self._search_code,
            "load_repo_map": self._load_repo_map_tool,
            "trace_call_chain": self._trace_call_chain,
            "open_file": self._open_file,
            "read_history": self._read_history,
        }
        handler = handlers.get(name)
        if handler is None:
            return self._failure(f"Unknown tool: {name}", {"arguments": normalized_arguments})

        try:
            return await handler(normalized_arguments)
        except Exception as exc:
            return self._failure(f"{name} failed: {exc}", {"arguments": normalized_arguments})

    async def _search_code(self, arguments: dict[str, object]) -> dict[str, object]:
        query = str(arguments.get("query") or "").strip()
        limit = self._coerce_limit(arguments.get("limit"), default=5)
        if not query:
            return self._failure("search_code requires a query.", {"hits": []})
        if not self._knowledge_db_path.exists():
            return self._failure("Knowledge DB is not available for search_code.", {"hits": []})

        hits = self._retriever.retrieve(
            task_id=self._task_id,
            db_path=self._knowledge_db_path,
            question=query,
            limit=limit,
        )
        payload_hits = [
            {
                "path": item.path,
                "symbol": item.symbol_name,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "summary": item.summary,
                "snippet": item.content,
            }
            for item in hits
        ]
        return self._success(
            f"Found {len(payload_hits)} matching code snippet(s).",
            {"query": query, "hits": payload_hits},
        )

    async def _load_repo_map_tool(self, arguments: dict[str, object]) -> dict[str, object]:
        del arguments
        repo_map = self._load_repo_map_payload()
        return self._success(
            "Loaded repository map.",
            {
                "task_id": repo_map.get("task_id", self._task_id),
                "entrypoints": repo_map.get("entrypoints") or {},
                "symbol_nodes": list(repo_map.get("symbol_nodes") or [])[: self._MAX_REPO_MAP_SYMBOLS],
                "edges": list(repo_map.get("edges") or [])[: self._MAX_REPO_MAP_EDGES],
                "call_chains": list(repo_map.get("call_chains") or [])[: self._MAX_REPO_MAP_CALL_CHAINS],
            },
        )

    async def _trace_call_chain(self, arguments: dict[str, object]) -> dict[str, object]:
        query = str(arguments.get("query") or "").strip()
        entry = str(arguments.get("entry") or "").strip()
        if not query and not entry:
            return self._failure("trace_call_chain requires query or entry.", {"chains": []})

        repo_map = self._load_repo_map_payload()
        call_chains = list(repo_map.get("call_chains") or [])
        entrypoints = repo_map.get("entrypoints") or {}
        query_lower = query.lower()
        entry_lower = entry.lower()

        matched = []
        for chain in call_chains:
            text = " ".join(str(value) for value in chain.values() if value is not None).lower()
            if query and query_lower in text:
                matched.append(chain)
                continue
            if entry and self._chain_matches_entry(chain, entry_lower, entrypoints):
                matched.append(chain)

        if not matched:
            return self._failure("No call chains matched the provided query or entry.", {"chains": []})

        return self._success(
            f"Found {len(matched)} call chain(s).",
            {"query": query or None, "entry": entry or None, "chains": matched},
        )

    async def _open_file(self, arguments: dict[str, object]) -> dict[str, object]:
        path_value = str(arguments.get("path") or "").strip()
        symbol = str(arguments.get("symbol") or "").strip()
        if not path_value and not symbol:
            return self._failure("open_file requires path or symbol.", {})

        resolved = self._resolve_open_target(
            path_value=path_value,
            symbol=symbol,
            start_line=self._coerce_positive_int(arguments.get("start_line")),
            end_line=self._coerce_positive_int(arguments.get("end_line")),
        )
        if resolved is None:
            return self._failure("Unable to resolve file target from the provided path or symbol.", {})

        path, start_line, end_line, resolved_symbol = resolved
        absolute_path = self._resolve_repo_path(path)
        if absolute_path is None or not absolute_path.is_file():
            return self._failure(f"File is not available: {path}", {"path": path})

        lines = absolute_path.read_text(encoding="utf-8").splitlines()
        bounded_start = max(start_line or 1, 1)
        if bounded_start > len(lines):
            return self._failure(
                "Resolved file location is stale or outside the file range.",
                {"path": path, "symbol": resolved_symbol},
            )
        max_end_line = bounded_start + self._MAX_OPEN_FILE_LINES - 1
        bounded_end = min(max(end_line or max_end_line, bounded_start), max_end_line, max(len(lines), 1))
        snippet = "\n".join(lines[bounded_start - 1 : bounded_end])
        if len(snippet) > self._MAX_SNIPPET_CHARS:
            snippet = snippet[: self._MAX_SNIPPET_CHARS - 3] + "..."
        return self._success(
            f"Opened {path}.",
            {
                "path": path,
                "symbol": resolved_symbol,
                "start_line": bounded_start,
                "end_line": bounded_end,
                "snippet": snippet,
            },
        )

    async def _read_history(self, arguments: dict[str, object]) -> dict[str, object]:
        limit = self._coerce_limit(arguments.get("limit"), default=5)
        if self._task_store is None:
            return self._failure("History is unavailable because task history storage is not configured.", {"messages": []})

        messages = await self._task_store.get_chat_messages(self._task_id)
        recent = messages[-limit:]
        payload_messages = [
            {
                "message_id": message.message_id,
                "role": message.role,
                "content": message.content,
            }
            for message in recent
        ]
        roles = ", ".join(message["role"] for message in payload_messages) or "no roles"
        return self._success(
            f"Loaded {len(payload_messages)} history message(s): {roles}.",
            {"messages": payload_messages},
        )

    def _load_repo_map_payload(self) -> dict[str, object]:
        if not self._repo_map_path.exists():
            raise FileNotFoundError("Repo map is not available.")
        payload = self._repo_map_loader.load(self._repo_map_path)
        return payload if isinstance(payload, dict) else {}

    def _resolve_open_target(
        self,
        *,
        path_value: str,
        symbol: str,
        start_line: int | None,
        end_line: int | None,
    ) -> tuple[str, int | None, int | None, str | None] | None:
        if path_value:
            return path_value, start_line, end_line, None

        repo_map = self._load_repo_map_payload()
        for node in repo_map.get("symbol_nodes") or []:
            if str(node.get("name") or "").strip().lower() != symbol.lower():
                continue
            path = str(node.get("file_path") or "").strip()
            line = self._coerce_positive_int(node.get("line"))
            hit = self._retriever.find_symbol(
                task_id=self._task_id,
                db_path=self._knowledge_db_path,
                symbol=symbol,
            )
            if hit is not None:
                return hit.path, hit.start_line, hit.end_line, symbol
            if path:
                return path, line, line + 20 if line is not None else None, symbol

        hit = self._retriever.find_symbol(
            task_id=self._task_id,
            db_path=self._knowledge_db_path,
            symbol=symbol,
        )
        if hit is None:
            return None
        return hit.path, hit.start_line, hit.end_line, symbol

    def _resolve_repo_path(self, relative_path: str) -> Path | None:
        candidate = (self._repo_root / relative_path).resolve()
        repo_root = self._repo_root.resolve()
        try:
            candidate.relative_to(repo_root)
        except ValueError:
            return None
        return candidate

    def _chain_matches_entry(
        self,
        chain: dict[str, object],
        entry: str,
        entrypoints: dict[str, object],
    ) -> bool:
        entry_payload = entrypoints.get(entry)
        entry_file = ""
        if isinstance(entry_payload, dict):
            entry_file = str(entry_payload.get("file_path") or "").lower()
        text = " ".join(str(value) for value in chain.values() if value is not None).lower()
        return entry in text or (entry_file and entry_file in text)

    def _coerce_limit(self, value: object, *, default: int) -> int:
        coerced = self._coerce_positive_int(value)
        if coerced is None:
            return default
        return min(max(coerced, 1), 20)

    def _coerce_positive_int(self, value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _success(self, summary: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "summary": summary, "payload": payload}

    def _failure(self, summary: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": False, "summary": summary, "payload": payload}
