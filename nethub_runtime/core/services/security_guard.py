from __future__ import annotations

import json
from pathlib import Path

from nethub_runtime.core.config.settings import SECURITY_POLICY_PATH, ensure_core_config_dir


class SecurityGuard:
    """Validates output format and step tool permissions."""

    def __init__(self, policy_path: Path | None = None) -> None:
        ensure_core_config_dir()
        self.policy_path = policy_path or SECURITY_POLICY_PATH
        self.policy = self._load_policy()

    def _load_policy(self) -> dict:
        if not self.policy_path.exists():
            return {"allowed_output_formats": ["dict"], "allowed_tool_names": ["none"]}
        return json.loads(self.policy_path.read_text(encoding="utf-8"))

    def validate_output_format(self, fmt: str) -> None:
        allowed = set(self.policy.get("allowed_output_formats", ["dict"]))
        if fmt not in allowed:
            raise ValueError(f"Output format '{fmt}' is not allowed.")

    def validate_plan(self, plan: list[dict]) -> None:
        allowed_tools = set(self.policy.get("allowed_tool_names", []))
        for step in plan:
            tool_name = (step.get("capability") or {}).get("tool", "none")
            if tool_name not in allowed_tools:
                raise PermissionError(f"Tool '{tool_name}' is not allowed by security policy.")
