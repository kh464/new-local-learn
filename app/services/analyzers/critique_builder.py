from __future__ import annotations


class CritiqueBuilder:
    def build(
        self,
        *,
        repo_summary: dict[str, object],
        backend_summary: dict[str, object],
        frontend_summary: dict[str, object],
        deploy_summary: dict[str, object],
    ) -> dict[str, list[str]]:
        coverage_notes = [
            f"Scanned {repo_summary.get('file_count', 0)} files from the repository snapshot.",
            f"Detected {len(backend_summary.get('routes', []))} backend routes and {len(frontend_summary.get('api_calls', []))} frontend API calls.",
        ]
        inferred_sections: list[str] = []
        if frontend_summary.get("framework") is None:
            inferred_sections.append("Frontend framework could not be proven from manifests and was left unknown.")
        if not deploy_summary.get("services"):
            inferred_sections.append("No deploy services were extracted from compose files or manifests.")

        missing_areas = [
            "HTML output is a rendered Markdown view, not a template-specific document.",
            "PDF output uses a lightweight built-in renderer and does not yet support rich layout or diagrams.",
        ]
        return {
            "coverage_notes": coverage_notes,
            "inferred_sections": inferred_sections,
            "missing_areas": missing_areas,
        }
