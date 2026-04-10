from __future__ import annotations

import json
from pathlib import Path


class RepoMapLoader:
    def load(self, repo_map_path: Path | str) -> dict[str, object]:
        path = Path(repo_map_path)
        return json.loads(path.read_text(encoding="utf-8"))
