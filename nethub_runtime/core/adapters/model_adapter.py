from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import LOCAL_MODEL_REGISTRY_PATH, MODEL_ROUTING_POLICY_PATH, ensure_core_config_dir
from nethub_runtime.models.ollama_provider import OllamaProvider


class ModelRouter:
    """Multi-model routing adapter with optional local auto-pull support."""

    def __init__(self, policy_path: Path | None = None, local_registry_path: Path | None = None) -> None:
        ensure_core_config_dir()
        self.policy_path = policy_path or MODEL_ROUTING_POLICY_PATH
        self.local_registry_path = local_registry_path or LOCAL_MODEL_REGISTRY_PATH
        self.policy: dict[str, Any] = self._load_policy()
        self._local_registry = self._load_local_registry()
        self._ollama_provider = OllamaProvider()

    def _default_policy(self) -> dict[str, Any]:
        return {
            "task_mapping": {"routing": [{"provider": "ollama", "model": "qwen2.5"}]},
            "auto_pull_rule": {"enabled": True, "only_local_provider": "ollama", "verify_checksum": False, "verify_version": True},
        }

    def _load_policy(self) -> dict[str, Any]:
        if not self.policy_path.exists():
            policy = self._default_policy()
            self.policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
            return policy
        return json.loads(self.policy_path.read_text(encoding="utf-8"))

    def _load_local_registry(self) -> set[str]:
        if not self.local_registry_path.exists():
            self.local_registry_path.write_text(json.dumps({"models": []}, indent=2), encoding="utf-8")
            return set()
        payload = json.loads(self.local_registry_path.read_text(encoding="utf-8"))
        return {item.lower() for item in payload.get("models", [])}

    def _save_local_registry(self) -> None:
        self.local_registry_path.write_text(json.dumps({"models": sorted(self._local_registry)}, ensure_ascii=False, indent=2), encoding="utf-8")

    def route(self, task_kind: str) -> dict[str, str]:
        candidates = self.policy.get("task_mapping", {}).get(task_kind) or self.policy.get("task_mapping", {}).get("routing", [])
        if not candidates:
            return {"provider": "local", "model": "rule-engine", "api": "internal"}
        selected = candidates[0]
        return {
            "provider": selected.get("provider", "local"),
            "model": selected.get("model", "rule-engine"),
            "api": self._resolve_api(selected.get("provider", "local")),
        }

    def _resolve_api(self, provider: str) -> str:
        provider = provider.lower()
        if provider == "ollama":
            return "ollama_local_api"
        if provider == "tool":
            return "local_tool_runtime"
        if provider == "openai":
            return "openai_chat_api"
        if provider == "claude":
            return "anthropic_messages_api"
        if provider == "gemini":
            return "google_genai_api"
        return "internal"

    def ensure_available(self, provider: str, model: str) -> dict[str, Any]:
        rule = self.policy.get("auto_pull_rule", {})
        model_key = model.lower()
        if provider in {"tool", "service", "internal"}:
            return {"available": True, "source": "local_runtime", "auto_pulled": False}
        if provider != rule.get("only_local_provider", "ollama"):
            return {"available": True, "source": "external_provider", "auto_pulled": False}
        if model_key in self._local_registry:
            return {"available": True, "source": "local_registry", "auto_pulled": False}

        auto_pull_enabled = bool(rule.get("enabled", False))
        if not auto_pull_enabled:
            return {"available": False, "source": "local_registry", "auto_pulled": False}

        try:
            if not self._ollama_provider.is_available(model):
                self._ollama_provider.ensure(model)
            self._local_registry.add(model_key)
            self._save_local_registry()
            return {"available": True, "source": "ollama_pull", "auto_pulled": True}
        except Exception as exc:
            return {"available": False, "source": "ollama_pull", "auto_pulled": False, "error": str(exc)}
