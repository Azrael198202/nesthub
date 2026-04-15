from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import DEPENDENCIES_PATH, ensure_core_config_dir


class DependencyManager:
    """Checks required runtime dependencies from JSON config."""

    def __init__(self, config_path: Path | None = None) -> None:
        ensure_core_config_dir()
        self.config_path = config_path or DEPENDENCIES_PATH
        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {"python_packages": [], "shell_tools": [], "auto_install": False}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def check(self) -> dict[str, list[str] | bool]:
        missing_packages: list[str] = []
        missing_tools: list[str] = []
        for pkg in self.config.get("python_packages", []):
            if importlib.util.find_spec(pkg) is None:
                missing_packages.append(pkg)
        for tool in self.config.get("shell_tools", []):
            if shutil.which(tool) is None:
                missing_tools.append(tool)
        return {
            "auto_install": bool(self.config.get("auto_install", False)),
            "missing_packages": missing_packages,
            "missing_tools": missing_tools,
        }
