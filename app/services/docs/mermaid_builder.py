from __future__ import annotations


class MermaidBuilder:
    def build_system_diagram(self, detected_stack: dict[str, list[str]]) -> str:
        frameworks = set(detected_stack.get("frameworks", []))
        backend_label = "FastAPI API" if "fastapi" in frameworks else "Backend"
        frontend_label = "React UI" if "react" in frameworks else "Frontend"

        lines = ["graph TD"]
        if "react" in frameworks and "fastapi" in frameworks:
            lines.extend(
                [
                    "    user[User] --> ui[React UI]",
                    "    ui --> api[FastAPI API]",
                ]
            )
        elif "react" in frameworks:
            lines.extend(
                [
                    "    user[User] --> ui[React UI]",
                ]
            )
        elif "fastapi" in frameworks:
            lines.extend(
                [
                    "    user[User] --> api[FastAPI API]",
                ]
            )
        else:
            lines.append("    repo[Repository]")

        return "\n".join(lines)
