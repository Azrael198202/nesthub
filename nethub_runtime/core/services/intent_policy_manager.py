from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from nethub_runtime.core.adapters.model_adapter import ModelRouter
from nethub_runtime.core.config.settings import INTENT_POLICY_PATH


class IntentPolicyManager:
    """Derive and optionally persist runtime intent policy using routed model strategy."""

    def __init__(self, policy_path: Path | None = None, model_router: ModelRouter | None = None) -> None:
        self.policy_path = policy_path or INTENT_POLICY_PATH
        self.model_router = model_router or ModelRouter()
        self.base_policy = self._load_base_policy()

    def _load_base_policy(self) -> dict[str, Any]:
        if not self.policy_path.exists():
            return {}
        return json.loads(self.policy_path.read_text(encoding="utf-8"))

    def synthesize(self, text: str, persist: bool = False) -> dict[str, Any]:
        routing = self.model_router.route("routing")
        availability = self.model_router.ensure_available(routing["provider"], routing["model"])

        dynamic_terms = self._extract_dynamic_terms(text)
        policy = dict(self.base_policy)
        policy.setdefault("dynamic_markers", [])
        for term in dynamic_terms:
            if term not in policy["dynamic_markers"]:
                policy["dynamic_markers"].append(term)
        policy["_analysis_meta"] = {
            "provider": routing["provider"],
            "model": routing["model"],
            "api": routing["api"],
            "model_available": availability.get("available", False),
            "auto_pulled": availability.get("auto_pulled", False),
        }
        if persist:
            self.policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
            self.base_policy = policy
        return policy

    def _extract_dynamic_terms(self, text: str) -> list[str]:
        tokens = [t for t in re.split(r"[\s，,。；;！？!?]+", text) if t]
        return [token for token in tokens if len(token) >= 2 and not re.fullmatch(r"\d+(?:\.\d+)?", token)]
