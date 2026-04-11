from __future__ import annotations

from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSymbolNode


class CodeSummaryBuilder:
    def build_file_summary(self, *, file_node: CodeFileNode, symbols: list[CodeSymbolNode]) -> str:
        payload = self.build_file_payload(file_node=file_node, symbols=symbols)
        return str(payload["summary_zh"])

    def build_symbol_summary(
        self,
        *,
        symbol: CodeSymbolNode,
        outgoing_edges: list[CodeEdge],
        incoming_edges: list[CodeEdge] | None = None,
    ) -> str:
        payload = self.build_symbol_payload(
            symbol=symbol,
            outgoing_edges=outgoing_edges,
            incoming_edges=incoming_edges or [],
        )
        return str(payload["summary_zh"])

    def build_file_payload(self, *, file_node: CodeFileNode, symbols: list[CodeSymbolNode]) -> dict[str, object]:
        kind_counts: dict[str, int] = {}
        for symbol in symbols:
            kind_counts[symbol.symbol_kind] = kind_counts.get(symbol.symbol_kind, 0) + 1

        summary_parts = [f"该文件位于 {file_node.path}。"]
        if file_node.entry_role:
            summary_parts.append("它是当前仓库的重要入口文件。")
        if kind_counts:
            details = "、".join(f"{kind} {count} 个" for kind, count in sorted(kind_counts.items()))
            summary_parts.append(f"主要定义了 {details}。")
        if any(symbol.symbol_kind == "route" for symbol in symbols):
            summary_parts.append("该文件侧重处理路由或请求入口。")
        elif any(symbol.symbol_kind in {"class", "method"} for symbol in symbols):
            summary_parts.append("该文件以类型定义和方法组织为主。")
        else:
            summary_parts.append("该文件主要承载局部业务逻辑或工具能力。")

        responsibility = "负责组织该文件内的核心代码结构"
        if file_node.entry_role:
            responsibility = "负责承接仓库入口初始化并组织下游处理逻辑"
        elif any(symbol.symbol_kind == "route" for symbol in symbols):
            responsibility = "负责暴露请求入口并分发到具体处理逻辑"
        elif any(symbol.symbol_kind == "class" for symbol in symbols):
            responsibility = "负责封装相关对象能力并组织方法协作"

        keywords = [file_node.language, file_node.file_kind]
        if file_node.entry_role:
            keywords.append(file_node.entry_role)
        keywords.extend(sorted(kind_counts))

        return {
            "summary_zh": "".join(summary_parts),
            "responsibility_zh": responsibility,
            "upstream_zh": "由上游模块导入或被运行时直接加载" if file_node.entry_role else "",
            "downstream_zh": "向文件内定义的符号或下游调用链继续分发逻辑" if symbols else "",
            "keywords_zh": [item for item in keywords if item],
            "summary_confidence": "low",
        }

    def build_symbol_payload(
        self,
        *,
        symbol: CodeSymbolNode,
        outgoing_edges: list[CodeEdge],
        incoming_edges: list[CodeEdge] | None = None,
    ) -> dict[str, object]:
        incoming_edges = incoming_edges or []
        call_count = sum(1 for edge in outgoing_edges if edge.edge_kind == "calls")
        caller_count = sum(1 for edge in incoming_edges if edge.edge_kind == "calls")

        if symbol.symbol_kind == "route":
            summary = f"该路由节点负责描述 {symbol.name} 请求如何进入仓库中的处理逻辑。"
            io_text = "输入为 HTTP 请求，输出为对应路由处理结果"
        elif symbol.symbol_kind == "class":
            summary = f"该类 {symbol.name} 定义在 {symbol.file_path}，用于组织相关状态与方法。"
            io_text = "输入输出取决于类实例方法与成员状态"
        elif symbol.symbol_kind == "method":
            summary = f"该方法 {symbol.qualified_name} 定义在 {symbol.file_path}。"
            io_text = "输入输出可结合方法签名与返回值进一步确认"
        else:
            summary = f"该函数 {symbol.qualified_name} 定义在 {symbol.file_path}。"
            io_text = "输入输出可结合函数签名与返回值进一步确认"

        if call_count:
            summary += f" 当前静态分析识别到它会调用 {call_count} 个下游符号。"
        else:
            summary += " 当前静态分析中没有识别到明确的下游调用。"

        call_targets = f"当前识别到 {call_count} 个下游调用" if call_count else "未识别到明确的下游调用"
        callers = f"当前识别到 {caller_count} 个上游调用方" if caller_count else "未识别到明确的上游调用方"

        return {
            "summary_zh": summary,
            "input_output_zh": io_text if not symbol.signature else f"签名为 {symbol.signature}",
            "side_effects_zh": "需结合函数体进一步确认外部状态、副作用或 I/O 操作",
            "call_targets_zh": call_targets,
            "callers_zh": callers,
            "summary_confidence": "low",
        }
