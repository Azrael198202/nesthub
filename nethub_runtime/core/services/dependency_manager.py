from __future__ import annotations

import importlib.util
import json
import shlex
import subprocess
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

    def _resolve_tool_installers(self, tool_name: str) -> list[dict[str, str]]:
        installers = (self.config.get("shell_tool_installers") or {}).get(tool_name, [])
        resolved: list[dict[str, str]] = []
        for installer in installers:
            if not isinstance(installer, dict):
                continue
            installer_type = str(installer.get("type") or "").strip()
            package_name = str(installer.get("package") or tool_name).strip()
            if not installer_type or not package_name:
                continue
            command = self._build_installer_command(installer_type, package_name)
            if command is None:
                continue
            resolved.append(
                {
                    "type": installer_type,
                    "package": package_name,
                    "command": command,
                }
            )
        return resolved

    def _build_installer_command(self, installer_type: str, package_name: str) -> str | None:
        command_templates = {
            "apt-get": f"apt-get install -y {package_name}",
            "apt": f"apt install -y {package_name}",
            "dnf": f"dnf install -y {package_name}",
            "yum": f"yum install -y {package_name}",
            "brew": f"brew install {package_name}",
        }
        return command_templates.get(installer_type)

    def build_install_plan(self, missing_items: list[str]) -> dict[str, Any]:
        package_candidates = [item for item in missing_items if item in self.config.get("python_packages", [])]
        tool_candidates = [item for item in missing_items if item in self.config.get("shell_tools", [])]
        tool_installers: dict[str, list[dict[str, str]]] = {}
        unsupported_tools: list[str] = []
        shell_commands: list[str] = []
        if package_candidates:
            shell_commands.append(f"python -m pip install {' '.join(package_candidates)}")
        if tool_candidates:
            for tool_name in tool_candidates:
                installers = self._resolve_tool_installers(tool_name)
                tool_installers[tool_name] = installers
                if not installers:
                    unsupported_tools.append(tool_name)
                    continue
                shell_commands.append(installers[0]["command"])
        return {
            "auto_install": bool(self.config.get("auto_install", False)),
            "packages": package_candidates,
            "tools": tool_candidates,
            "tool_installers": tool_installers,
            "unsupported_tools": unsupported_tools,
            "shell_commands": shell_commands,
        }

    def execute_install_plan(self, plan: dict[str, Any], *, allowed_installers: list[str] | None = None) -> dict[str, Any]:
        if not plan.get("auto_install", False):
            return {
                "status": "skipped",
                "reason": "auto_install_disabled",
                "executed_commands": [],
                "failed_commands": [],
                "blocked_commands": [],
                "unsupported_tools": list(plan.get("unsupported_tools", [])),
            }

        allowed_installer_set = {item.strip() for item in (allowed_installers or []) if isinstance(item, str) and item.strip()}
        executed_commands: list[str] = []
        failed_commands: list[dict[str, Any]] = []
        blocked_commands: list[dict[str, Any]] = []
        for command in plan.get("shell_commands", []):
            if not isinstance(command, str) or not command.strip():
                continue
            command_parts = shlex.split(command)
            if not command_parts:
                continue
            installer_name = command_parts[0]
            normalized_installer = "pip" if installer_name == "python" and len(command_parts) >= 3 and command_parts[1:3] == ["-m", "pip"] else installer_name
            if allowed_installer_set and normalized_installer not in allowed_installer_set:
                blocked_commands.append(
                    {
                        "command": command,
                        "reason": "installer_not_allowed",
                        "installer": normalized_installer,
                    }
                )
                continue
            executable_name = installer_name if normalized_installer != "pip" else "python"
            if shutil.which(executable_name) is None:
                failed_commands.append(
                    {
                        "command": command,
                        "reason": "installer_not_available",
                        "installer": normalized_installer,
                    }
                )
                continue
            try:
                subprocess.run(command_parts, check=True, capture_output=True, text=True)
                executed_commands.append(command)
            except Exception as exc:
                failed_commands.append({
                    "command": command,
                    "reason": str(exc),
                    "installer": normalized_installer,
                })

        unsupported_tools = list(plan.get("unsupported_tools", []))
        if failed_commands:
            status = "partial"
        elif blocked_commands or unsupported_tools:
            status = "deferred"
        else:
            status = "completed"
        return {
            "status": status,
            "executed_commands": executed_commands,
            "failed_commands": failed_commands,
            "blocked_commands": blocked_commands,
            "unsupported_tools": unsupported_tools,
        }
