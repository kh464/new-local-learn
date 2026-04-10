from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path


_FILE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".vue"}
_IGNORED_DIR_NAMES = {
    ".git",
    ".idea",
    ".pytest_cache",
    "__pycache__",
    "artifacts",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "tests",
    "tmp",
    "tmpbase",
}
_IGNORED_FILE_SUFFIXES = (".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx", ".test.py")
_ROUTE_DECORATOR_RE = re.compile(r"@(?P<owner>\w+)\.(?P<method>get|post|put|delete|patch)\(\s*[\"'](?P<path>[^\"']+)")
_FETCH_RE = re.compile(r"fetch\(\s*[\"'](?P<path>/[^\"']+)")
_AXIOS_RE = re.compile(r"axios\.(?P<method>get|post|put|delete|patch)\(\s*[\"'](?P<path>/[^\"']+)")
_TS_IMPORT_RE = re.compile(r"import\s+.+?\s+from\s+[\"'](?P<target>[^\"']+)[\"']")
_INCLUDE_ROUTER_PREFIX_RE = re.compile(r"include_router\(.+?prefix\s*=\s*[\"'](?P<prefix>/[^\"']*)[\"']")
_REQUEST_JSON_RE = re.compile(r"requestJson(?:<[^>]+>)?\(\s*(?P<quote>`|\"|')(?P<path>[^`\"']+)(?P=quote)")
_VUE_EVENT_HANDLER_RE = re.compile(r"@(?P<event>[A-Za-z_][\w:-]*)\s*=\s*[\"'](?P<handler>[A-Za-z_][A-Za-z0-9_]*)[\"']")
_TS_FUNCTION_RE = re.compile(
    r"(?:const|function)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(|function\s+(?P<name2>[A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.MULTILINE,
)


class RepoMapBuilder:
    def build(self, *, task_id: str, repo_path: Path, output_path: Path) -> dict[str, object]:
        file_nodes = self._collect_file_nodes(repo_path)
        symbol_nodes = self._collect_symbol_nodes(repo_path, file_nodes)
        route_prefixes = self._collect_route_prefixes(repo_path, file_nodes)
        edges = self._collect_edges(repo_path, file_nodes, symbol_nodes, route_prefixes)
        payload = {
            "task_id": task_id,
            "file_nodes": file_nodes,
            "symbol_nodes": symbol_nodes,
            "edges": edges,
            "entrypoints": self._collect_entrypoints(file_nodes),
            "call_chains": self._collect_call_chains(edges, symbol_nodes, file_nodes),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def _collect_file_nodes(self, repo_path: Path) -> list[dict[str, object]]:
        file_nodes: list[dict[str, object]] = []
        for dirpath, dirnames, filenames in os.walk(repo_path):
            nested_repo_dirs = [name for name in sorted(dirnames) if (Path(dirpath) / name / ".git").exists()]
            ignored_names = _IGNORED_DIR_NAMES | set(nested_repo_dirs)
            dirnames[:] = [name for name in sorted(dirnames) if name not in ignored_names]

            for filename in sorted(filenames):
                path = Path(dirpath) / filename
                if path.suffix not in _FILE_SUFFIXES:
                    continue
                if any(path.name.endswith(suffix) for suffix in _IGNORED_FILE_SUFFIXES):
                    continue
                relative_path = self._rel_path(repo_path, path)
                if self._is_ignored_relative_path(relative_path):
                    continue
                file_nodes.append(
                    {
                        "id": self._file_node_id(relative_path),
                        "file_path": relative_path,
                        "language": self._language_for(path),
                        "layer": self._layer_for(relative_path),
                    }
                )
        return file_nodes

    def _collect_symbol_nodes(self, repo_path: Path, file_nodes: list[dict[str, object]]) -> list[dict[str, object]]:
        symbol_nodes: list[dict[str, object]] = []
        for file_node in file_nodes:
            relative_path = str(file_node["file_path"])
            path = repo_path / relative_path
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                source = path.read_text(encoding="utf-8", errors="ignore")

            if path.suffix == ".py":
                symbol_nodes.extend(self._python_symbols(relative_path, source))
            else:
                symbol_nodes.extend(self._script_symbols(relative_path, source))
        return symbol_nodes

    def _collect_edges(
        self,
        repo_path: Path,
        file_nodes: list[dict[str, object]],
        symbol_nodes: list[dict[str, object]],
        route_prefixes: list[str],
    ) -> list[dict[str, object]]:
        edges: list[dict[str, object]] = []
        symbol_index = self._build_symbol_index(symbol_nodes)
        known_files = {str(node["file_path"]) for node in file_nodes}
        backend_routes = [node for node in symbol_nodes if node.get("route_path")]
        route_candidates: list[tuple[str, dict[str, object]]] = []
        for node in backend_routes:
            for candidate_path in self._expand_route_paths(str(node["route_path"]), route_prefixes):
                route_candidates.append((candidate_path, node))

        for file_node in file_nodes:
            relative_path = str(file_node["file_path"])
            path = repo_path / relative_path
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                source = path.read_text(encoding="utf-8", errors="ignore")

            if path.suffix == ".py":
                edges.extend(self._python_import_edges(relative_path, source))
                edges.extend(self._python_call_edges(relative_path, source, symbol_index))
            else:
                frontend_calls = self._frontend_api_calls(relative_path, source)
                edges.extend(self._script_import_edges(relative_path, source, known_files))
                edges.extend(frontend_calls)
                for call in frontend_calls:
                    for candidate_path, route in route_candidates:
                        if not self._paths_match(str(call["route_path"]), candidate_path):
                            continue
                        edges.append(
                            {
                                "type": "maps_to_backend",
                                "source": call["source"],
                                "target": route["id"],
                                "path": call["route_path"],
                                "method": route.get("route_method"),
                                "frontend_file": relative_path,
                                "frontend_symbol": call.get("frontend_symbol"),
                                "frontend_trigger": call.get("frontend_trigger"),
                                "backend_file": route["file_path"],
                            }
                        )
                        break

        return edges

    def _collect_route_prefixes(self, repo_path: Path, file_nodes: list[dict[str, object]]) -> list[str]:
        prefixes: list[str] = []
        for file_node in file_nodes:
            relative_path = str(file_node["file_path"])
            if not relative_path.startswith("app/") or not relative_path.endswith(".py"):
                continue
            path = repo_path / relative_path
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                source = path.read_text(encoding="utf-8", errors="ignore")
            for match in _INCLUDE_ROUTER_PREFIX_RE.finditer(source):
                prefix = match.group("prefix").rstrip("/")
                if prefix and prefix not in prefixes:
                    prefixes.append(prefix)
        return prefixes

    def _collect_entrypoints(self, file_nodes: list[dict[str, object]]) -> dict[str, dict[str, object] | None]:
        backend_entry = next((node for node in file_nodes if node["file_path"] == "app/main.py"), None)
        if backend_entry is None:
            backend_entry = next((node for node in file_nodes if node["layer"] == "backend"), None)

        frontend_entry = next(
            (node for node in file_nodes if str(node["file_path"]) in {"web/src/main.ts", "web/src/main.js", "web/main.ts", "web/main.js"}),
            None,
        )
        if frontend_entry is None:
            frontend_entry = next((node for node in file_nodes if node["layer"] == "frontend"), None)

        return {
            "backend": self._entrypoint_payload(backend_entry),
            "frontend": self._entrypoint_payload(frontend_entry),
        }

    def _collect_call_chains(
        self, edges: list[dict[str, object]], symbol_nodes: list[dict[str, object]], file_nodes: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        symbol_by_id = {str(node["id"]): node for node in symbol_nodes}
        call_edges_by_source: dict[str, list[dict[str, object]]] = {}
        reverse_frontend_imports: dict[str, list[str]] = {}
        frontend_entry = next(
            (
                str(node["file_path"])
                for node in file_nodes
                if str(node["file_path"]) in {"web/src/main.ts", "web/src/main.js", "web/main.ts", "web/main.js"}
            ),
            None,
        )
        for edge in edges:
            if edge["type"] == "calls":
                source = str(edge["source"])
                call_edges_by_source.setdefault(source, []).append(edge)
            if edge["type"] == "imports" and edge.get("resolved_target_file"):
                source_file = str(edge["file_path"])
                target_file = str(edge["resolved_target_file"])
                if source_file.startswith("web/") and target_file.startswith("web/"):
                    reverse_frontend_imports.setdefault(target_file, []).append(source_file)
        call_chains: list[dict[str, object]] = []
        for edge in edges:
            if edge["type"] != "maps_to_backend":
                continue
            target = symbol_by_id.get(str(edge["target"]))
            if target is None:
                continue
            method = str(target.get("route_method") or "GET").upper()
            route_path = str(edge.get("path") or target.get("route_path") or "")
            frontend_segment = str(edge["frontend_file"])
            if edge.get("frontend_symbol"):
                frontend_segment = f"{frontend_segment}:{edge['frontend_symbol']}"
                if edge.get("frontend_trigger"):
                    frontend_segment = f"{frontend_segment} [{edge['frontend_trigger']}]"
            mount_chain = self._expand_frontend_mount_chain(
                str(edge["frontend_file"]),
                reverse_frontend_imports,
                frontend_entry,
            )
            segments = [*mount_chain, frontend_segment, f"{method} {route_path}", f"{target['file_path']}:{target['name']}"]
            for target_id in self._expand_call_targets(str(target["id"]), call_edges_by_source):
                next_symbol = symbol_by_id.get(target_id)
                if next_symbol is None:
                    continue
                segments.append(f"{next_symbol['file_path']}:{next_symbol['name']}")
            segments = list(dict.fromkeys(segments))
            call_chains.append(
                {
                    "summary": " -> ".join(segments),
                    "frontend_file": edge["frontend_file"],
                    "backend_file": target["file_path"],
                    "route_path": route_path,
                    "method": method,
                }
            )
        return call_chains

    def _python_symbols(self, relative_path: str, source: str) -> list[dict[str, object]]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        route_lookup = self._python_route_lookup(source)
        symbol_nodes: list[dict[str, object]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                route = route_lookup.get(node.name, {})
                symbol_nodes.append(
                    {
                        "id": self._symbol_node_id(relative_path, node.name),
                        "file_path": relative_path,
                        "name": node.name,
                        "kind": "function",
                        "line": node.lineno,
                        "route_path": route.get("path"),
                        "route_method": route.get("method"),
                        "route_owner": route.get("owner"),
                    }
                )
            if isinstance(node, ast.ClassDef):
                symbol_nodes.append(
                    {
                        "id": self._symbol_node_id(relative_path, node.name),
                        "file_path": relative_path,
                        "name": node.name,
                        "kind": "class",
                        "line": node.lineno,
                    }
                )
        return symbol_nodes

    def _python_route_lookup(self, source: str) -> dict[str, dict[str, str]]:
        lines = source.splitlines()
        route_lookup: dict[str, dict[str, str]] = {}
        for index, line in enumerate(lines):
            match = _ROUTE_DECORATOR_RE.search(line)
            if match is None:
                continue
            for next_line in lines[index + 1 :]:
                func_match = re.match(r"\s*async\s+def\s+(?P<name>\w+)\s*\(|\s*def\s+(?P<name2>\w+)\s*\(", next_line)
                if func_match is None:
                    continue
                func_name = func_match.group("name") or func_match.group("name2")
                route_lookup[func_name] = {
                    "path": match.group("path"),
                    "method": match.group("method").upper(),
                    "owner": match.group("owner"),
                }
                break
        return route_lookup

    def _script_symbols(self, relative_path: str, source: str) -> list[dict[str, object]]:
        symbol_nodes: list[dict[str, object]] = []
        for match in _TS_FUNCTION_RE.finditer(source):
            name = match.group("name") or match.group("name2")
            if not name:
                continue
            line = source[: match.start()].count("\n") + 1
            symbol_nodes.append(
                {
                    "id": self._symbol_node_id(relative_path, name),
                    "file_path": relative_path,
                    "name": name,
                    "kind": "function",
                    "line": line,
                }
            )
        return symbol_nodes

    def _python_import_edges(self, relative_path: str, source: str) -> list[dict[str, object]]:
        edges: list[dict[str, object]] = []
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            edges.append(
                {
                    "type": "imports",
                    "source": self._file_node_id(relative_path),
                    "target": stripped,
                    "file_path": relative_path,
                }
            )
        return edges

    def _python_call_edges(
        self,
        relative_path: str,
        source: str,
        symbol_index: dict[str, object],
    ) -> list[dict[str, object]]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        imported_names, imported_modules = self._python_import_lookup(tree)
        edges: list[dict[str, object]] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            source_symbol_id = self._symbol_node_id(relative_path, node.name)
            if source_symbol_id not in symbol_index["by_id"]:
                continue
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                target_symbol_id = self._resolve_call_target(
                    call.func,
                    current_file=relative_path,
                    imported_names=imported_names,
                    imported_modules=imported_modules,
                    symbol_index=symbol_index,
                )
                if target_symbol_id is None or target_symbol_id == source_symbol_id:
                    continue
                edges.append(
                    {
                        "type": "calls",
                        "source": source_symbol_id,
                        "target": target_symbol_id,
                        "file_path": relative_path,
                    }
                )

        deduped: list[dict[str, object]] = []
        seen: set[tuple[str, str, str]] = set()
        for edge in edges:
            key = (str(edge["source"]), str(edge["target"]), str(edge["file_path"]))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(edge)
        return deduped

    def _script_import_edges(
        self,
        relative_path: str,
        source: str,
        known_files: set[str],
    ) -> list[dict[str, object]]:
        edges: list[dict[str, object]] = []
        for match in _TS_IMPORT_RE.finditer(source):
            target = match.group("target")
            edges.append(
                {
                    "type": "imports",
                    "source": self._file_node_id(relative_path),
                    "target": target,
                    "file_path": relative_path,
                    "resolved_target_file": self._resolve_script_import_target(relative_path, target, known_files),
                }
            )
        return edges

    def _frontend_api_calls(self, relative_path: str, source: str) -> list[dict[str, object]]:
        edges: list[dict[str, object]] = []
        function_ranges = self._script_function_ranges(source)
        vue_handlers = self._vue_event_handlers(source) if relative_path.endswith(".vue") else {}
        for match in _FETCH_RE.finditer(source):
            frontend_symbol = self._find_enclosing_function_name(match.start(), function_ranges)
            frontend_trigger = vue_handlers.get(frontend_symbol) if frontend_symbol else None
            edges.append(
                {
                    "type": "frontend_api_call",
                    "source": self._symbol_node_id(relative_path, frontend_symbol)
                    if frontend_symbol and frontend_trigger
                    else self._file_node_id(relative_path),
                    "target": match.group("path"),
                    "route_path": match.group("path"),
                    "method": "GET",
                    "frontend_file": relative_path,
                    "frontend_symbol": frontend_symbol if frontend_trigger else None,
                    "frontend_trigger": frontend_trigger,
                }
            )
        for match in _REQUEST_JSON_RE.finditer(source):
            route_path = self._normalize_frontend_path(match.group("path"))
            frontend_symbol = self._find_enclosing_function_name(match.start(), function_ranges)
            frontend_trigger = vue_handlers.get(frontend_symbol) if frontend_symbol else None
            edges.append(
                {
                    "type": "frontend_api_call",
                    "source": self._symbol_node_id(relative_path, frontend_symbol)
                    if frontend_symbol and frontend_trigger
                    else self._file_node_id(relative_path),
                    "target": route_path,
                    "route_path": route_path,
                    "method": "GET",
                    "frontend_file": relative_path,
                    "frontend_symbol": frontend_symbol if frontend_trigger else None,
                    "frontend_trigger": frontend_trigger,
                }
            )
        for match in _AXIOS_RE.finditer(source):
            frontend_symbol = self._find_enclosing_function_name(match.start(), function_ranges)
            frontend_trigger = vue_handlers.get(frontend_symbol) if frontend_symbol else None
            edges.append(
                {
                    "type": "frontend_api_call",
                    "source": self._symbol_node_id(relative_path, frontend_symbol)
                    if frontend_symbol and frontend_trigger
                    else self._file_node_id(relative_path),
                    "target": match.group("path"),
                    "route_path": match.group("path"),
                    "method": match.group("method").upper(),
                    "frontend_file": relative_path,
                    "frontend_symbol": frontend_symbol if frontend_trigger else None,
                    "frontend_trigger": frontend_trigger,
                }
            )
        return edges

    def _entrypoint_payload(self, node: dict[str, object] | None) -> dict[str, object] | None:
        if node is None:
            return None
        return {
            "file_path": node["file_path"],
            "language": node["language"],
            "layer": node["layer"],
        }

    def _language_for(self, path: Path) -> str:
        suffix = path.suffix
        return {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".vue": "vue",
        }.get(suffix, "text")

    def _layer_for(self, relative_path: str) -> str:
        if relative_path.startswith("app/"):
            return "backend"
        if relative_path.startswith("web/"):
            return "frontend"
        return "shared"

    def _file_node_id(self, relative_path: str) -> str:
        return f"file:{relative_path}"

    def _symbol_node_id(self, relative_path: str, name: str) -> str:
        return f"symbol:{relative_path}:{name}"

    def _rel_path(self, repo_path: Path, path: Path) -> str:
        return path.relative_to(repo_path).as_posix()

    def _is_ignored_relative_path(self, relative_path: str) -> bool:
        return any(part in _IGNORED_DIR_NAMES for part in Path(relative_path).parts[:-1])

    def _expand_route_paths(self, route_path: str, route_prefixes: list[str]) -> list[str]:
        normalized_path = route_path if route_path.startswith("/") else f"/{route_path}"
        candidates = [normalized_path]
        for prefix in route_prefixes:
            combined = f"{prefix}{normalized_path}" if normalized_path != "/" else prefix or "/"
            if combined not in candidates:
                candidates.append(combined)
        return candidates

    def _normalize_frontend_path(self, route_path: str) -> str:
        normalized = route_path if route_path.startswith("/") else f"/{route_path}"
        return re.sub(r"\$\{([^}]+)\}", r"{\1}", normalized)

    def _paths_match(self, frontend_path: str, backend_path: str) -> bool:
        frontend_parts = [part for part in frontend_path.strip("/").split("/") if part]
        backend_parts = [part for part in backend_path.strip("/").split("/") if part]
        if len(frontend_parts) != len(backend_parts):
            return frontend_path == backend_path

        for frontend_part, backend_part in zip(frontend_parts, backend_parts, strict=False):
            if frontend_part == backend_part:
                continue
            if frontend_part.startswith("{") and frontend_part.endswith("}"):
                continue
            if backend_part.startswith("{") and backend_part.endswith("}"):
                continue
            return False
        return True

    def _build_symbol_index(self, symbol_nodes: list[dict[str, object]]) -> dict[str, object]:
        by_id = {str(node["id"]): node for node in symbol_nodes}
        by_file_and_name = {
            (str(node["file_path"]), str(node["name"])): str(node["id"])
            for node in symbol_nodes
        }
        return {
            "by_id": by_id,
            "by_file_and_name": by_file_and_name,
        }

    def _python_import_lookup(self, tree: ast.AST) -> tuple[dict[str, str], dict[str, str]]:
        imported_names: dict[str, str] = {}
        imported_modules: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                module_path = self._module_to_rel_path(node.module)
                if module_path is None:
                    continue
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    imported_names[local_name] = module_path
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module_path = self._module_to_rel_path(alias.name)
                    if module_path is None:
                        continue
                    local_name = alias.asname or alias.name.split(".")[-1]
                    imported_modules[local_name] = module_path
        return imported_names, imported_modules

    def _resolve_call_target(
        self,
        func: ast.AST,
        *,
        current_file: str,
        imported_names: dict[str, str],
        imported_modules: dict[str, str],
        symbol_index: dict[str, object],
    ) -> str | None:
        by_file_and_name = symbol_index["by_file_and_name"]

        if isinstance(func, ast.Name):
            if (current_file, func.id) in by_file_and_name:
                return by_file_and_name[(current_file, func.id)]
            imported_file = imported_names.get(func.id)
            if imported_file is not None:
                return by_file_and_name.get((imported_file, func.id))
            return None

        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            imported_file = imported_modules.get(func.value.id)
            if imported_file is not None:
                return by_file_and_name.get((imported_file, func.attr))

        return None

    def _module_to_rel_path(self, module_name: str) -> str | None:
        if not module_name.startswith("app."):
            return None
        return f"{module_name.replace('.', '/')}.py"

    def _expand_call_targets(
        self,
        start_symbol_id: str,
        call_edges_by_source: dict[str, list[dict[str, object]]],
        *,
        limit: int = 2,
    ) -> list[str]:
        chain: list[str] = []
        current_symbol_id = start_symbol_id
        seen = {start_symbol_id}
        for _ in range(limit):
            next_edges = call_edges_by_source.get(current_symbol_id) or []
            next_edge = next((edge for edge in next_edges if str(edge["target"]) not in seen), None)
            if next_edge is None:
                break
            next_target = str(next_edge["target"])
            chain.append(next_target)
            seen.add(next_target)
            current_symbol_id = next_target
        return chain

    def _expand_frontend_mount_chain(
        self,
        frontend_file: str,
        reverse_frontend_imports: dict[str, list[str]],
        frontend_entry: str | None,
        *,
        limit: int = 4,
    ) -> list[str]:
        parents = self._find_frontend_parent_chain(frontend_file, reverse_frontend_imports, frontend_entry, limit=limit)
        return parents

    def _script_function_ranges(self, source: str) -> list[dict[str, int | str]]:
        matches = list(_TS_FUNCTION_RE.finditer(source))
        ranges: list[dict[str, int | str]] = []
        for index, match in enumerate(matches):
            name = match.group("name") or match.group("name2")
            if not name:
                continue
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
            ranges.append({"name": name, "start": start, "end": end})
        return ranges

    def _find_enclosing_function_name(self, position: int, function_ranges: list[dict[str, int | str]]) -> str | None:
        for item in function_ranges:
            start = int(item["start"])
            end = int(item["end"])
            if start <= position < end:
                return str(item["name"])
        return None

    def _vue_event_handlers(self, source: str) -> dict[str, str]:
        handlers: dict[str, str] = {}
        for match in _VUE_EVENT_HANDLER_RE.finditer(source):
            handlers[match.group("handler")] = match.group("event")
        return handlers

    def _resolve_script_import_target(self, relative_path: str, target: str, known_files: set[str]) -> str | None:
        if not target.startswith("."):
            return None

        base = (Path(relative_path).parent / target).as_posix()
        candidates = [base]
        if not Path(base).suffix:
            candidates.extend(f"{base}{suffix}" for suffix in (".ts", ".tsx", ".js", ".jsx", ".vue"))
            candidates.extend(f"{base}/index{suffix}" for suffix in (".ts", ".tsx", ".js", ".jsx", ".vue"))

        for candidate in candidates:
            normalized = Path(candidate).as_posix()
            if normalized in known_files:
                return normalized
        return None

    def _find_frontend_parent_chain(
        self,
        current_file: str,
        reverse_frontend_imports: dict[str, list[str]],
        frontend_entry: str | None,
        *,
        limit: int,
        visited: set[str] | None = None,
    ) -> list[str]:
        if visited is None:
            visited = set()
        if current_file in visited or limit <= 0:
            return []
        visited.add(current_file)
        parents = sorted(reverse_frontend_imports.get(current_file) or [])
        if not parents:
            return []
        if frontend_entry in parents:
            return [str(frontend_entry)]
        for parent in parents:
            parent_chain = self._find_frontend_parent_chain(
                parent,
                reverse_frontend_imports,
                frontend_entry,
                limit=limit - 1,
                visited={*visited},
            )
            if parent_chain:
                return [*parent_chain, parent]
        return [parents[0]]
