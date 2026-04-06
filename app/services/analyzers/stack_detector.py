from __future__ import annotations

from pathlib import Path


_FRAMEWORK_MARKERS = {
    "fastapi": "fastapi",
    "react": "react",
    "vue": "vue",
    "svelte": "svelte",
}

_LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}


class StackDetector:
    def detect(self, file_list: list[str], file_contents: dict[str, str]) -> dict[str, list[str]]:
        frameworks: list[str] = []
        languages: list[str] = []

        for framework, marker in _FRAMEWORK_MARKERS.items():
            for path, content in file_contents.items():
                if Path(path).name.lower() not in {"pyproject.toml", "package.json"}:
                    continue
                if marker in content.lower():
                    frameworks.append(framework)
                    break

        for path in file_list:
            lowered_path = path.lower()
            for extension, language in _LANGUAGE_EXTENSIONS.items():
                if lowered_path.endswith(extension) and language not in languages:
                    languages.append(language)
                    break

            file_name = Path(path).name.lower()
            if file_name == "pyproject.toml" and "python" not in languages:
                languages.append("python")
            if file_name == "package.json" and "javascript" not in languages and "typescript" not in languages:
                languages.append("javascript")

        return {"frameworks": frameworks, "languages": languages}
