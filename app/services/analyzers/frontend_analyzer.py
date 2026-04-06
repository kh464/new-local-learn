from __future__ import annotations

import re


_ROUTE_PATTERN = re.compile(r"<Route[^>]*path=['\"](?P<path>[^'\"]+)['\"]", re.IGNORECASE)
_FETCH_PATTERN = re.compile(r"fetch\(\s*['\"](?P<url>[^'\"]+)['\"]", re.IGNORECASE)


class FrontendAnalyzer:
    def analyze(self, file_contents: dict[str, str]) -> dict[str, list[dict[str, str]]]:
        routing: list[dict[str, str]] = []
        api_calls: list[dict[str, str]] = []

        for source_file, content in sorted(file_contents.items()):
            if "react-router-dom" in content.lower():
                for match in _ROUTE_PATTERN.finditer(content):
                    routing.append({"path": match.group("path"), "source_file": source_file})

            for match in _FETCH_PATTERN.finditer(content):
                api_calls.append({"url": match.group("url"), "source_file": source_file})

        return {"routing": routing, "api_calls": api_calls}
