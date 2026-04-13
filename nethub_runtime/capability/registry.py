from __future__ import annotations

import importlib.metadata as metadata
import json
from pathlib import Path

from nethub_runtime.core.models import RegistryState
from nethub_runtime.config.settings import ensure_app_dirs


class CapabilityRegistry:
    def __init__(self) -> None:
        self.paths = ensure_app_dirs()
        self.registry_file = self.paths["registry"] / "capabilities.json"

    def load(self) -> RegistryState:
        if not self.registry_file.exists():
            return self.refresh_local_snapshot()
        data = json.loads(self.registry_file.read_text(encoding="utf-8"))
        return RegistryState(
            packages=set(data.get("packages", [])),
            tools=set(data.get("tools", [])),
            models=set(data.get("models", [])),
        )

    def save(self, state: RegistryState) -> None:
        data = {
            "packages": sorted(state.packages),
            "tools": sorted(state.tools),
            "models": sorted(state.models),
        }
        self.registry_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def refresh_local_snapshot(self) -> RegistryState:
        packages = {dist.metadata["Name"].lower() for dist in metadata.distributions() if dist.metadata.get("Name")}
        state = RegistryState(packages=packages, tools=set(), models=set())
        self.save(state)
        return state

    def register_package(self, name: str) -> None:
        state = self.load()
        state.packages.add(name.lower())
        self.save(state)

    def register_tool(self, name: str) -> None:
        state = self.load()
        state.tools.add(name.lower())
        self.save(state)

    def register_model(self, name: str) -> None:
        state = self.load()
        state.models.add(name.lower())
        self.save(state)
