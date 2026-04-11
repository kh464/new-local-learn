from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from app.services.code_graph.adapters.base import BaseLanguageAdapter, ExtractionResult
from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSymbolNode, UnresolvedCall


_ROUTE_METHODS = {"get", "post", "put", "delete", "patch"}


@dataclass(frozen=True)
class _RouteDef:
    owner: str
    method: str
    path: str


class PythonCodeGraphAdapter(BaseLanguageAdapter):
    language = "python"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".py"

    def extract_file(self, *, task_id: str, repo_root: Path, file_path: Path) -> ExtractionResult:
        relative_path = file_path.relative_to(repo_root).as_posix()
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return ExtractionResult(files=[self._build_file_node(task_id=task_id, relative_path=relative_path)])

        file_node = self._build_file_node(task_id=task_id, relative_path=relative_path)
        module_name = self._module_name(relative_path)
        file_id = self._file_id(relative_path)

        symbols: list[CodeSymbolNode] = []
        edges: list[CodeEdge] = []
        unresolved_calls: list[UnresolvedCall] = []
        local_functions: dict[str, str] = {}
        class_methods: dict[tuple[str, str], str] = {}

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_symbol = self._class_symbol(task_id=task_id, relative_path=relative_path, module_name=module_name, node=node)
                symbols.append(class_symbol)
                edges.append(
                    CodeEdge(
                        task_id=task_id,
                        from_symbol_id=file_id,
                        to_symbol_id=class_symbol.symbol_id,
                        edge_kind="contains",
                        source_path=relative_path,
                        line=node.lineno,
                    )
                )
                for body_node in node.body:
                    if not isinstance(body_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    method_symbol = self._method_symbol(
                        task_id=task_id,
                        relative_path=relative_path,
                        module_name=module_name,
                        class_node=node,
                        method_node=body_node,
                        parent_symbol_id=class_symbol.symbol_id,
                    )
                    symbols.append(method_symbol)
                    class_methods[(node.name, body_node.name)] = method_symbol.symbol_id
                    edges.append(
                        CodeEdge(
                            task_id=task_id,
                            from_symbol_id=class_symbol.symbol_id,
                            to_symbol_id=method_symbol.symbol_id,
                            edge_kind="contains",
                            source_path=relative_path,
                            line=body_node.lineno,
                        )
                    )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_symbol = self._function_symbol(
                    task_id=task_id,
                    relative_path=relative_path,
                    module_name=module_name,
                    node=node,
                )
                symbols.append(function_symbol)
                local_functions[node.name] = function_symbol.symbol_id
                edges.append(
                    CodeEdge(
                        task_id=task_id,
                        from_symbol_id=file_id,
                        to_symbol_id=function_symbol.symbol_id,
                        edge_kind="contains",
                        source_path=relative_path,
                        line=node.lineno,
                    )
                )
                for route in self._route_defs(node):
                    route_symbol = self._route_symbol(
                        task_id=task_id,
                        relative_path=relative_path,
                        module_name=module_name,
                        route=route,
                        line=node.lineno,
                    )
                    symbols.append(route_symbol)
                    edges.append(
                        CodeEdge(
                            task_id=task_id,
                            from_symbol_id=file_id,
                            to_symbol_id=route_symbol.symbol_id,
                            edge_kind="contains",
                            source_path=relative_path,
                            line=node.lineno,
                        )
                    )
                    edges.append(
                        CodeEdge(
                            task_id=task_id,
                            from_symbol_id=route_symbol.symbol_id,
                            to_symbol_id=function_symbol.symbol_id,
                            edge_kind="routes_to",
                            source_path=relative_path,
                            line=node.lineno,
                        )
                    )

        imported_name_to_file = self._imported_name_to_file(tree)
        import_edges = self._import_edges(task_id=task_id, relative_path=relative_path, file_id=file_id, tree=tree)
        edges.extend(import_edges)

        for symbol in symbols:
            if symbol.symbol_kind not in {"function", "method"}:
                continue
            fn_node = self._find_function_node(tree, symbol)
            if fn_node is None:
                continue
            for call in ast.walk(fn_node):
                if not isinstance(call, ast.Call):
                    continue
                target_symbol_id = self._resolve_call_target(
                    call.func,
                    local_functions=local_functions,
                    class_methods=class_methods,
                    current_parent=symbol.parent_symbol_id,
                )
                if target_symbol_id is not None and target_symbol_id != symbol.symbol_id:
                    edges.append(
                        CodeEdge(
                            task_id=task_id,
                            from_symbol_id=symbol.symbol_id,
                            to_symbol_id=target_symbol_id,
                            edge_kind="calls",
                            source_path=relative_path,
                            line=getattr(call, "lineno", None),
                        )
                    )
                    continue

                unresolved = self._build_unresolved_call(
                    task_id=task_id,
                    caller_symbol_id=symbol.symbol_id,
                    source_path=relative_path,
                    call=call,
                    imported_name_to_file=imported_name_to_file,
                )
                if unresolved is not None:
                    unresolved_calls.append(unresolved)

        return ExtractionResult(
            files=[file_node],
            symbols=self._dedupe_symbols(symbols),
            edges=self._dedupe_edges(edges),
            unresolved_calls=self._dedupe_unresolved_calls(unresolved_calls),
        )

    def _build_file_node(self, *, task_id: str, relative_path: str) -> CodeFileNode:
        entry_role = "backend_entry" if relative_path == "app/main.py" else None
        return CodeFileNode(
            task_id=task_id,
            path=relative_path,
            language=self.language,
            file_kind="source",
            entry_role=entry_role,
        )

    def _function_symbol(self, *, task_id: str, relative_path: str, module_name: str, node: ast.AST) -> CodeSymbolNode:
        name = getattr(node, "name")
        return CodeSymbolNode(
            task_id=task_id,
            symbol_id=self._symbol_id(relative_path=relative_path, qualified_name=f"{module_name}.{name}", symbol_kind="function"),
            symbol_kind="function",
            name=name,
            qualified_name=f"{module_name}.{name}",
            file_path=relative_path,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            signature=self._signature(node),
            language=self.language,
        )

    def _class_symbol(self, *, task_id: str, relative_path: str, module_name: str, node: ast.ClassDef) -> CodeSymbolNode:
        return CodeSymbolNode(
            task_id=task_id,
            symbol_id=self._symbol_id(relative_path=relative_path, qualified_name=f"{module_name}.{node.name}", symbol_kind="class"),
            symbol_kind="class",
            name=node.name,
            qualified_name=f"{module_name}.{node.name}",
            file_path=relative_path,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            language=self.language,
        )

    def _method_symbol(
        self,
        *,
        task_id: str,
        relative_path: str,
        module_name: str,
        class_node: ast.ClassDef,
        method_node: ast.AST,
        parent_symbol_id: str,
    ) -> CodeSymbolNode:
        method_name = getattr(method_node, "name")
        qualified_name = f"{module_name}.{class_node.name}.{method_name}"
        return CodeSymbolNode(
            task_id=task_id,
            symbol_id=self._symbol_id(relative_path=relative_path, qualified_name=qualified_name, symbol_kind="method"),
            symbol_kind="method",
            name=method_name,
            qualified_name=qualified_name,
            file_path=relative_path,
            start_line=method_node.lineno,
            end_line=getattr(method_node, "end_lineno", method_node.lineno),
            parent_symbol_id=parent_symbol_id,
            signature=self._signature(method_node),
            language=self.language,
        )

    def _route_symbol(
        self,
        *,
        task_id: str,
        relative_path: str,
        module_name: str,
        route: _RouteDef,
        line: int,
    ) -> CodeSymbolNode:
        route_name = f"{route.method} {route.path}"
        qualified_name = f"{module_name}.__route__.{route.owner}.{route.method.lower()}:{route.path}"
        return CodeSymbolNode(
            task_id=task_id,
            symbol_id=self._symbol_id(relative_path=relative_path, qualified_name=qualified_name, symbol_kind="route"),
            symbol_kind="route",
            name=route_name,
            qualified_name=qualified_name,
            file_path=relative_path,
            start_line=line,
            end_line=line,
            language=self.language,
        )

    def _route_defs(self, node: ast.AST) -> list[_RouteDef]:
        routes: list[_RouteDef] = []
        for decorator in getattr(node, "decorator_list", []):
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            owner = decorator.func.value.id if isinstance(decorator.func.value, ast.Name) else None
            method = decorator.func.attr.lower()
            if owner is None or method not in _ROUTE_METHODS or not decorator.args:
                continue
            first_arg = decorator.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                routes.append(_RouteDef(owner=owner, method=method.upper(), path=first_arg.value))
        return routes

    def _imported_name_to_file(self, tree: ast.AST) -> dict[str, str]:
        imported_names: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
                module_path = f"{node.module.replace('.', '/')}.py"
                for alias in node.names:
                    imported_names[alias.asname or alias.name] = module_path
        return imported_names

    def _import_edges(self, *, task_id: str, relative_path: str, file_id: str, tree: ast.AST) -> list[CodeEdge]:
        edges: list[CodeEdge] = []
        seen: set[tuple[str, str]] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
                target_file_id = self._file_id(f"{node.module.replace('.', '/')}.py")
                key = (file_id, target_file_id)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    CodeEdge(
                        task_id=task_id,
                        from_symbol_id=file_id,
                        to_symbol_id=target_file_id,
                        edge_kind="imports",
                        source_path=relative_path,
                        line=node.lineno,
                    )
                )
        return edges

    def _resolve_call_target(
        self,
        func: ast.AST,
        *,
        local_functions: dict[str, str],
        class_methods: dict[tuple[str, str], str],
        current_parent: str | None,
    ) -> str | None:
        if isinstance(func, ast.Name):
            return local_functions.get(func.id)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "self" and current_parent:
            class_name = current_parent.split(":")[-1].split(".")[-1]
            return class_methods.get((class_name, func.attr))
        return None

    def _build_unresolved_call(
        self,
        *,
        task_id: str,
        caller_symbol_id: str,
        source_path: str,
        call: ast.Call,
        imported_name_to_file: dict[str, str],
    ) -> UnresolvedCall | None:
        callee_name: str | None = None
        raw_expr: str | None = None
        if isinstance(call.func, ast.Name):
            callee_name = call.func.id
            raw_expr = call.func.id
        elif isinstance(call.func, ast.Attribute):
            callee_name = call.func.attr
            raw_expr = self._attribute_text(call.func)
        if callee_name is None:
            return None
        if callee_name in {"APIRouter", "FastAPI"}:
            return None
        if callee_name in imported_name_to_file or isinstance(call.func, ast.Attribute):
            return UnresolvedCall(
                task_id=task_id,
                caller_symbol_id=caller_symbol_id,
                callee_name=callee_name,
                source_path=source_path,
                line=getattr(call, "lineno", None),
                raw_expr=raw_expr,
            )
        return None

    def _find_function_node(self, tree: ast.AST, symbol: CodeSymbolNode) -> ast.AST | None:
        candidates = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.lineno != symbol.start_line:
                continue
            candidates.append(node)
        return candidates[0] if candidates else None

    def _attribute_text(self, node: ast.Attribute) -> str:
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        return node.attr

    def _signature(self, node: ast.AST) -> str:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return ""
        arg_names = [arg.arg for arg in node.args.args]
        return f"{node.name}({', '.join(arg_names)})"

    def _module_name(self, relative_path: str) -> str:
        if relative_path.endswith("/__init__.py"):
            return relative_path[:-12].replace("/", ".")
        return relative_path[:-3].replace("/", ".")

    def _file_id(self, relative_path: str) -> str:
        return f"file:{self.language}:{relative_path}"

    def _symbol_id(self, *, relative_path: str, qualified_name: str, symbol_kind: str) -> str:
        return f"{symbol_kind}:{self.language}:{relative_path}:{qualified_name}"

    def _dedupe_symbols(self, symbols: list[CodeSymbolNode]) -> list[CodeSymbolNode]:
        seen: set[str] = set()
        result: list[CodeSymbolNode] = []
        for symbol in symbols:
            if symbol.symbol_id in seen:
                continue
            seen.add(symbol.symbol_id)
            result.append(symbol)
        return result

    def _dedupe_edges(self, edges: list[CodeEdge]) -> list[CodeEdge]:
        seen: set[tuple[str, str, str, str, int | None]] = set()
        result: list[CodeEdge] = []
        for edge in edges:
            key = (edge.edge_kind, edge.from_symbol_id, edge.to_symbol_id, edge.source_path, edge.line)
            if key in seen:
                continue
            seen.add(key)
            result.append(edge)
        return result

    def _dedupe_unresolved_calls(self, calls: list[UnresolvedCall]) -> list[UnresolvedCall]:
        seen: set[tuple[str, str, str, int | None]] = set()
        result: list[UnresolvedCall] = []
        for call in calls:
            key = (call.caller_symbol_id, call.callee_name, call.source_path, call.line)
            if key in seen:
                continue
            seen.add(key)
            result.append(call)
        return result

