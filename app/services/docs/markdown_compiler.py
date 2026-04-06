from __future__ import annotations


class MarkdownCompiler:
    def compile(
        self,
        *,
        task_id: str,
        repo_summary: dict[str, object],
        detected_stack: dict[str, list[str]],
        backend_summary: dict[str, list[dict[str, object]]],
        frontend_summary: dict[str, object],
        logic_summary: dict[str, list[dict[str, object]]],
        tutorial_summary: dict[str, object],
        mermaid_sections: dict[str, str],
    ) -> str:
        frameworks = ", ".join(detected_stack.get("frameworks", [])) or "unknown"
        languages = ", ".join(detected_stack.get("languages", [])) or "unknown"
        repo_name = str(repo_summary.get("name", task_id))
        key_files = repo_summary.get("key_files", [])
        routes = backend_summary.get("routes", [])
        routing = frontend_summary.get("routing", [])
        api_calls = frontend_summary.get("api_calls", [])
        flows = logic_summary.get("flows", [])

        if isinstance(routing, str):
            routing_text = routing
        else:
            route_paths = [route.get("path", "") for route in routing if isinstance(route, dict)]
            routing_text = ", ".join(path for path in route_paths if path) or "not detected"

        lines = [
            f"# Analysis Report: {repo_name}",
            "",
            f"- Task ID: `{task_id}`",
            f"- Frameworks: {frameworks}",
            f"- Languages: {languages}",
            "",
            "## Key Files",
        ]

        if key_files:
            lines.extend(f"- `{path}`" for path in key_files)
        else:
            lines.append("- None detected")

        lines.extend(
            [
                "",
                "## System Diagram",
                "```mermaid",
                mermaid_sections.get("system", "graph TD"),
                "```",
                "",
                "## Backend Analysis",
            ]
        )

        if routes:
            lines.extend(f"- `{route.get('method', 'GET')} {route.get('path', '')}`" for route in routes)
        else:
            lines.append("- No backend routes detected")

        lines.extend(
            [
                "",
                "## Frontend Analysis",
                f"- Routing: {routing_text}",
                f"- API calls detected: {len(api_calls)}",
                "",
                "## Logic Summary",
                f"- Cross-layer flows mapped: {len(flows)}",
                "",
                "## Beginner Guide",
                str(tutorial_summary.get("mental_model", "")),
                "",
                "### Run Steps",
            ]
        )
        lines.extend(f"- {step}" for step in tutorial_summary.get("run_steps", []))
        lines.extend(["", "### Pitfalls"])
        lines.extend(f"- {pitfall}" for pitfall in tutorial_summary.get("pitfalls", []))
        lines.extend(["", "### Self-Check"])
        lines.extend(f"- {question}" for question in tutorial_summary.get("self_check_questions", []))
        lines.append("")

        return "\n".join(lines)
