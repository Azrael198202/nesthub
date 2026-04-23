from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ContractSchemaRegistry:
    """Loads schema files from contracts/schemas for runtime visibility."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parent / "schemas"

    def load_all(self) -> dict[str, dict[str, Any]]:
        schemas: dict[str, dict[str, Any]] = {}
        for schema_name in ("intent", "workflow", "blueprint", "tool", "trace"):
            schemas[schema_name] = self.load(schema_name)
        return schemas

    def load(self, schema_name: str) -> dict[str, Any]:
        path = self.base_dir / f"{schema_name}.schema.json"
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
