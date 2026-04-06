from __future__ import annotations

import re


_ROUTE_PATTERN = re.compile(
    r"@(?P<target>app|router)\.(?P<method>get|post|put|delete|patch)\((?P<args>[^)]*)\)",
    re.IGNORECASE,
)
_STRING_PATTERN = re.compile(r"['\"](?P<value>[^'\"]+)['\"]")


class BackendAnalyzer:
    def analyze(self, file_contents: dict[str, str]) -> dict[str, list[dict[str, str]]]:
        routes: list[dict[str, str]] = []

        for source_file, content in sorted(file_contents.items()):
            for match in _ROUTE_PATTERN.finditer(content):
                path_match = _STRING_PATTERN.search(match.group("args"))
                if path_match is None:
                    continue
                routes.append(
                    {
                        "method": match.group("method").upper(),
                        "path": path_match.group("value"),
                        "source_file": source_file,
                    }
                )

        return {"routes": routes}
