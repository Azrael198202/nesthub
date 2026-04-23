from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from nethub_runtime.core_brain.contracts.registry import ContractSchemaRegistry


@dataclass(slots=True)
class CoreBrainConfig:
    app: dict[str, Any]
    model_registry: dict[str, Any]
    prompt_registry: dict[str, Any]
    routing_policy: dict[str, Any]
    contract_schemas: dict[str, dict[str, Any]]


class ConfigLoader:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parent / "configs"

    def load(self) -> CoreBrainConfig:
        return CoreBrainConfig(
            app=self._read_yaml("app/app.yaml"),
            model_registry=self._read_yaml("models/registry.yaml"),
            prompt_registry=self._read_yaml("prompts/registry.yaml"),
            routing_policy=self._read_yaml("routing/escalation_policy.yaml"),
            contract_schemas=ContractSchemaRegistry().load_all(),
        )

    def _read_yaml(self, relative_path: str) -> dict[str, Any]:
        path = self.base_dir / relative_path
        if not path.exists():
            return {}
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
