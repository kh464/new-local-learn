from __future__ import annotations

import re


_ROUTE_PATTERN = re.compile(r"<Route[^>]*path=['\"](?P<path>[^'\"]+)['\"]", re.IGNORECASE)
_FETCH_PATTERN = re.compile(r"fetch\(\s*['\"](?P<url>[^'\"]+)['\"]", re.IGNORECASE)
_IMPORT_PATTERN = re.compile(r"import\s+(?P<imports>.+?)\s+from\s+['\"](?P<source>[^'\"]+)['\"]", re.IGNORECASE)
_AXIOS_PATTERN = re.compile(r"axios\.(?P<method>get|post|put|patch|delete)\(\s*['\"](?P<url>[^'\"]+)['\"]", re.IGNORECASE)
_STATE_HINTS = {
    "zustand": "zustand",
    "redux": "redux",
    "@reduxjs/toolkit": "redux",
    "pinia": "pinia",
    "vuex": "vuex",
}
_FRAMEWORK_HINTS = {
    "react": "react",
    "vue": "vue",
    "svelte": "svelte",
}
_BUNDLER_HINTS = {
    "vite": "vite",
    "webpack": "webpack",
    "parcel": "parcel",
}


class FrontendAnalyzer:
    def analyze(self, file_contents: dict[str, str]) -> dict[str, object]:
        routing: list[dict[str, str]] = []
        api_calls: list[dict[str, str | None]] = []
        components: list[dict[str, object]] = []
        package_contents = file_contents.get("package.json", "")
        framework = self._detect_hint(package_contents, _FRAMEWORK_HINTS)
        bundler = self._detect_hint(package_contents, _BUNDLER_HINTS)
        state_manager = self._detect_hint(package_contents, _STATE_HINTS)

        for source_file, content in sorted(file_contents.items()):
            if "react-router-dom" in content.lower():
                for match in _ROUTE_PATTERN.finditer(content):
                    routing.append({"path": match.group("path"), "source_file": source_file})

            for match in _FETCH_PATTERN.finditer(content):
                api_calls.append(
                    {
                        "url": match.group("url"),
                        "source_file": source_file,
                        "client": "fetch",
                        "method": "GET",
                    }
                )

            for match in _AXIOS_PATTERN.finditer(content):
                api_calls.append(
                    {
                        "url": match.group("url"),
                        "source_file": source_file,
                        "client": "axios",
                        "method": match.group("method").upper(),
                    }
                )

            if source_file.endswith((".tsx", ".jsx", ".vue")):
                imports = self._extract_component_imports(content)
                component_name = source_file.rsplit("/", 1)[-1].split(".", 1)[0]
                components.append(
                    {
                        "name": component_name,
                        "source_file": source_file,
                        "imports": imports,
                    }
                )

        return {
            "framework": framework,
            "bundler": bundler,
            "state_manager": state_manager,
            "routing": routing,
            "api_calls": api_calls,
            "state_units": [],
            "components": components,
        }

    def _detect_hint(self, content: str, mapping: dict[str, str]) -> str | None:
        lowered = content.lower()
        for needle, value in mapping.items():
            if needle in lowered:
                return value
        return None

    def _extract_component_imports(self, content: str) -> list[str]:
        imports: list[str] = []
        for match in _IMPORT_PATTERN.finditer(content):
            source = match.group("source")
            if not source.startswith("."):
                continue
            imported = match.group("imports")
            imported = imported.replace("{", "").replace("}", "")
            for item in imported.split(","):
                name = item.strip().split(" as ")[0].strip()
                if not name or name == "type":
                    continue
                imports.append(name)
        return sorted(set(imports))
