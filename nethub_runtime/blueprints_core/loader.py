from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BlueprintLoader:
    def load_file(self, path: str | Path) -> dict[str, Any]:
        resolved = Path(path)
        raw = json.loads(resolved.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
