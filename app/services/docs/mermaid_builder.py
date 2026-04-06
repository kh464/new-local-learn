from __future__ import annotations


class MermaidBuilder:
    def build_system_diagram(self, detected_stack: dict[str, list[str]]) -> str:
        frameworks = set(detected_stack.get("frameworks", []))
        backend_label = "FastAPI" if "fastapi" in frameworks else "Backend"
        frontend_label = "React" if "react" in frameworks else "Frontend"

        lines = [
            "graph TD",
            f"    ui[{frontend_label}] --> api[{backend_label}]",
            "    api --> worker[Worker]",
            "    worker --> redis[(Redis)]",
            "    worker --> artifacts[(Artifacts)]",
        ]
        return "\n".join(lines)
