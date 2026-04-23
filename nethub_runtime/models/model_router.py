"""
LiteLLM-based Model Router - Unified LLM interface management.
Reference: docs/02_router/litellm_routing_design.md
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
from typing import Any, Optional
from pathlib import Path
from threading import Lock

import httpx
import yaml

from nethub_runtime.config.secrets import _maybe_load_dotenv
from nethub_runtime.models.local_model_manager import LocalModelManager

LOGGER = logging.getLogger("nethub_runtime.models")


# ---------------------------------------------------------------------------
# Model Cooldown Tracker
# Inspired by OpenClaw's auth-profile rotation + exponential backoff:
#   1 min → 5 min → 25 min → 1 hr
# Records per-model failure counts and blocks re-use until cooldown expires.
# ---------------------------------------------------------------------------

_COOLDOWN_BACKOFF_SECONDS = [60, 300, 1500, 3600]


class ModelCooldownTracker:
    """Thread-safe per-model exponential backoff cooldown tracker.

    When a model fails, ``record_failure`` increments its error count and
    sets a cooldown until = now + backoff[min(error_count-1, max)].
    ``is_in_cooldown`` returns True while that window has not expired.
    ``reset`` clears the record after a successful call.
    """

    def __init__(self, backoff_seconds: list[int] | None = None) -> None:
        self._backoff = backoff_seconds or _COOLDOWN_BACKOFF_SECONDS
        # model_id -> {"cooldown_until": float, "error_count": int}
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def is_in_cooldown(self, model_id: str) -> bool:
        with self._lock:
            entry = self._state.get(model_id)
            if not entry:
                return False
            return time.monotonic() < entry.get("cooldown_until", 0.0)

    def record_failure(self, model_id: str) -> float:
        """Record a failure for *model_id* and return cooldown seconds applied."""
        with self._lock:
            entry = self._state.setdefault(model_id, {"cooldown_until": 0.0, "error_count": 0})
            count = entry["error_count"]
            backoff = self._backoff[min(count, len(self._backoff) - 1)]
            entry["cooldown_until"] = time.monotonic() + backoff
            entry["error_count"] = count + 1
            LOGGER.warning(
                "Model %s failed (error_count=%d); cooldown %.0fs",
                model_id, entry["error_count"], backoff,
            )
            return float(backoff)

    def reset(self, model_id: str) -> None:
        """Clear cooldown after a successful call."""
        with self._lock:
            self._state.pop(model_id, None)

    def status(self) -> dict[str, Any]:
        """Return a snapshot of all tracked models for observability."""
        now = time.monotonic()
        with self._lock:
            return {
                mid: {
                    "error_count": s["error_count"],
                    "remaining_seconds": max(0.0, round(s["cooldown_until"] - now, 1)),
                }
                for mid, s in self._state.items()
            }


def _running_under_pytest() -> bool:
    # Only use env var and argv — sys.modules check is too broad and
    # triggers false positives in VS Code debugpy sessions after test runs.
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTEST_VERSION"):
        return True
    argv = " ".join(sys.argv).lower()
    if "pytest" in argv or "-m pytest" in argv or "/pytest" in argv:
        return True
    return False


class ModelRouter:
    """
    LiteLLM 模型路由器 - 核心模型管理层
    
    职责:
    - 统一管理多个模型提供商接口
    - 根据任务类型自动选择最优模型
    - 支持模型回退链和性能路由
    - 配置热更新支持
    """

    def __init__(self, config_path: str | Path):
        """
        初始化模型路由器
        
        Args:
            config_path: 模型配置文件路径 (model_config.yaml)
        """
        self.config_path = Path(config_path)
        self.config: dict[str, Any] = {}
        self.model_cache: dict[str, dict[str, Any]] = {}
        self.fallback_chain: dict[str, list[str]] = {}
        self.mock_llm_calls = False
        self._ollama_models: set[str] | None = None
        self._ollama_health_cache: tuple[float, bool] | None = None
        self.local_model_manager = LocalModelManager()
        self.cooldown_tracker = ModelCooldownTracker()

        _maybe_load_dotenv()
        
        self._load_config()
        self._initialize_models()
    
    def _load_config(self) -> None:
        """加载模型配置文件"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
                self.mock_llm_calls = bool(self.config.get("development", {}).get("mock_llm_calls", False))
                if _running_under_pytest() and os.getenv("NETHUB_ENABLE_LIVE_MODELS_IN_TESTS", "").lower() not in {"1", "true", "yes", "on"}:
                    self.mock_llm_calls = True
                LOGGER.info(f"✓ Model config loaded from {self.config_path}")
            else:
                LOGGER.warning(f"⚠ Config file not found: {self.config_path}, using empty config")
                self.config = {
                    "model_providers": {},
                    "routing_policies": {},
                    "model_params": {}
                }
        except Exception as e:
            LOGGER.error(f"Failed to load config: {e}")
            self.config = {}
    
    def _initialize_models(self) -> None:
        """初始化所有模型"""
        providers = self.config.get("model_providers", {})
        for provider_key, provider_config in providers.items():
            provider_type = str(provider_config.get("type", provider_key)).lower()
            if provider_type in ("ollama", "openai", "anthropic", "claude", "gemini", "google", "groq"):
                self._init_provider(provider_key, provider_type, provider_config)
            else:
                LOGGER.debug("Unknown provider type: %s (%s)", provider_type, provider_key)
    
    def _init_provider(self, provider_key: str, provider_type: str, config: dict[str, Any]) -> None:
        """初始化单个 provider 下所有模型。"""
        base_url = config.get("base_url")
        api_key = self._resolve_api_key(config)
        models = config.get("models", [])
        if not isinstance(models, list):
            LOGGER.warning("Provider models should be list: %s", provider_key)
            return

        normalized_type = provider_type
        if normalized_type == "claude":
            normalized_type = "anthropic"
        if normalized_type == "google":
            normalized_type = "gemini"
        if normalized_type == "groq" and isinstance(base_url, str):
            if base_url.rstrip("/") == "https://api.groq.com":
                base_url = "https://api.groq.com/openai/v1"

        if not self._provider_is_usable(normalized_type, api_key):
            LOGGER.info("Skipping provider %s (%s): missing runtime credentials or local availability", provider_key, normalized_type)
            return

        try:
            LOGGER.info("Initializing provider: %s (%s)", provider_key, normalized_type)
            for model in models:
                model_cfg = self._normalize_model_config(model)
                if not model_cfg:
                    continue
                if not model_cfg.get("enabled", True):
                    continue

                model_name = str(model_cfg.get("name"))
                if normalized_type == "ollama" and not self._ollama_model_exists(model_name):
                    LOGGER.info("Skipping Ollama model not installed locally: %s", model_name)
                    continue
                model_id = f"{provider_key}:{model_name}"
                self.model_cache[model_id] = {
                    "provider": provider_key,
                    "provider_type": normalized_type,
                    "name": model_name,
                    "base_url": base_url,
                    "api_key": api_key,
                    **model_cfg,
                }
                LOGGER.debug("  Registered model: %s", model_id)
        except Exception as e:
            LOGGER.error("Failed to initialize provider %s: %s", provider_key, e)

    def _normalize_model_config(self, model: Any) -> dict[str, Any] | None:
        """兼容 string/dict 两种模型定义。"""
        if isinstance(model, str):
            return {"name": model, "enabled": True}
        if isinstance(model, dict) and model.get("name"):
            return model
        return None

    def _resolve_api_key(self, provider_config: dict[str, Any]) -> str | None:
        """解析 provider api_key（支持 ${ENV_VAR} 占位符）。"""
        raw_api_key = provider_config.get("api_key")
        if not raw_api_key:
            return None
        if not isinstance(raw_api_key, str):
            return str(raw_api_key)

        value = raw_api_key.strip()
        if value.startswith("${") and value.endswith("}"):
            env_name = value[2:-1].strip()
            return os.getenv(env_name)
        return value

    def _provider_is_usable(self, provider_type: str, api_key: str | None) -> bool:
        if provider_type == "ollama":
            return bool(self._get_ollama_models())
        return bool(api_key)

    def _get_ollama_models(self) -> set[str]:
        if self._ollama_models is not None:
            return self._ollama_models
        try:
            completed = subprocess.run(
                ["ollama", "list"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception as exc:
            LOGGER.info("Ollama is unavailable: %s", exc)
            self._ollama_models = set()
            return self._ollama_models

        models: set[str] = set()
        for line in completed.stdout.splitlines()[1:]:
            parts = line.split()
            if parts:
                models.add(parts[0].strip())
        self._ollama_models = models
        return models

    def _ollama_model_exists(self, model_name: str) -> bool:
        return model_name in self._get_ollama_models()

    def recommend_downloadable_local_models(self, task_type: str, query: str = "", limit: int = 5) -> list[dict[str, Any]]:
        return self.local_model_manager.recommend_huggingface_models(task_type=task_type, query=query, limit=limit)

    def install_downloadable_local_model(
        self,
        *,
        task_type: str,
        repo_id: str | None = None,
        query: str = "",
        alias: str | None = None,
        filename_pattern: str | None = None,
        set_as_fallback_for: str | None = None,
    ) -> dict[str, Any]:
        installed = self.local_model_manager.install_huggingface_model(
            task_type=task_type,
            repo_id=repo_id,
            query=query,
            alias=alias,
            filename_pattern=filename_pattern,
        )
        model_name = str(installed.get("model_name") or "").strip()
        if not model_name:
            raise RuntimeError("Installed local model did not return a usable model_name")
        self._ollama_models = None
        self._register_dynamic_ollama_model(model_name)
        if set_as_fallback_for:
            self._append_fallback_model(set_as_fallback_for, f"ollama:{model_name}")
        return installed

    def _register_dynamic_ollama_model(self, model_name: str) -> None:
        model_id = f"ollama:{model_name}"
        self.model_cache[model_id] = {
            "provider": "ollama",
            "provider_type": "ollama",
            "name": model_name,
            "base_url": self._resolve_ollama_base_url(),
            "api_key": None,
            "enabled": True,
            "source": "huggingface_local_import",
        }

    def _append_fallback_model(self, task_type: str, model_id: str) -> None:
        policies = self.config.setdefault("routing_policies", {})
        routing = policies.setdefault(task_type, {})
        fallback = routing.setdefault("fallback", [])
        if model_id not in fallback:
            fallback.append(model_id)

    def _resolve_ollama_base_url(self) -> str:
        return os.getenv("OLLAMA_HOST") or "http://localhost:11434"

    async def _ollama_is_healthy(self, timeout_sec: float = 2.0) -> bool:
        now = time.monotonic()
        if self._ollama_health_cache and now - self._ollama_health_cache[0] < 5.0:
            return self._ollama_health_cache[1]

        healthy = False
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                response = await client.get(f"{self._resolve_ollama_base_url().rstrip('/')}/api/tags")
                healthy = response.status_code == 200
        except Exception:
            healthy = False

        self._ollama_health_cache = (now, healthy)
        return healthy

    async def _candidate_is_ready(self, model_id: str, timeout_sec: float) -> bool:
        cfg = self.get_model_config(model_id)
        provider_type = str(cfg.get("provider_type", "")).lower()
        if provider_type != "ollama":
            return True

        provider_policy = self._get_provider_policy(model_id)
        if provider_policy.get("skip_unhealthy", True) is False:
            return True

        health_timeout = float(provider_policy.get("healthcheck_timeout_sec", min(timeout_sec, 2.0)))
        if await self._ollama_is_healthy(timeout_sec=max(0.1, health_timeout)):
            return True

        LOGGER.warning("Skipping unavailable Ollama candidate %s", self._to_litellm_model(model_id))
        return False
    
    def select_model(self, task_type: str) -> str:
        """
        根据任务类型选择最合适的模型
        
        Args:
            task_type: 任务类型 (intent_analysis / task_planning / code_generation 等)
        
        Returns:
            选中的模型名称 (provider/model_name)
        """
        candidates = self.get_candidate_models(task_type)
        if candidates:
            selected = candidates[0]
            LOGGER.info("✓ Selected model for %s: %s", task_type, selected)
            return selected

        LOGGER.warning(f"No model available for task: {task_type}, using any available")
        return self._get_any_available_model()

    def get_candidate_models(self, task_type: str) -> list[str]:
        policies = self.config.get("routing_policies", {})
        routing = policies.get(task_type)

        if not routing:
            routing = policies.get("default") or policies.get("general_chat", {})

        profile_override = self._profile_override_routing(task_type)
        if profile_override:
            merged_routing = dict(routing or {})
            merged_routing.update(profile_override)
            routing = merged_routing

        if not routing:
            any_model = self._get_any_available_model()
            return [] if any_model == "unknown" else [any_model]

        ordered_models = [routing.get("primary", ""), *routing.get("fallback", [])]
        candidates: list[str] = []
        for model_id in ordered_models:
            if model_id and self._is_model_available(model_id) and model_id not in candidates:
                candidates.append(model_id)
        if not candidates:
            auto_provisioned = self._auto_provision_local_model(task_type)
            if auto_provisioned and auto_provisioned not in candidates:
                candidates.append(auto_provisioned)
        return candidates

    def _auto_provision_local_model(self, task_type: str) -> str | None:
        cfg = self.config.get("local_model_management", {})
        if not isinstance(cfg, dict) or not cfg.get("enabled", False) or not cfg.get("auto_download_from_huggingface", False):
            return None
        if task_type.startswith("test_") or _running_under_pytest():
            return None

        preferred_queries = cfg.get("preferred_queries", {}) if isinstance(cfg.get("preferred_queries", {}), dict) else {}
        query = str(preferred_queries.get(task_type) or preferred_queries.get("default") or task_type).strip()
        try:
            installed = self.install_downloadable_local_model(
                task_type=task_type,
                query=query,
                set_as_fallback_for=task_type,
            )
        except Exception as exc:
            LOGGER.warning("Auto-provision local model failed for %s: %s", task_type, exc)
            return None
        model_name = str(installed.get("model_name") or "").strip()
        return f"ollama:{model_name}" if model_name else None
    
    def _is_model_available(self, model_id: str) -> bool:
        """检查模型是否可用"""
        return model_id in self.model_cache
    
    def _get_any_available_model(self) -> str:
        """获取任何可用的模型"""
        if not self.model_cache:
            LOGGER.warning("No models available!")
            return "unknown"
        return list(self.model_cache.keys())[0]

    def _local_profile_config(self) -> dict[str, Any]:
        payload = self.config.get("local_composite_profiles", {})
        return payload if isinstance(payload, dict) else {}

    def active_local_profile_info(self) -> dict[str, Any]:
        profile_config = self._local_profile_config()
        env_name = str(profile_config.get("active_profile_env") or "NETHUB_ACTIVE_LORA_PROFILE").strip() or "NETHUB_ACTIVE_LORA_PROFILE"
        default_profile = str(profile_config.get("default_profile") or "base_local").strip() or "base_local"
        requested_profile = str(os.getenv(env_name, default_profile) or default_profile).strip() or default_profile
        profiles = profile_config.get("profiles", {})
        profiles = profiles if isinstance(profiles, dict) else {}
        resolved_name = requested_profile if requested_profile in profiles else default_profile
        resolved = profiles.get(resolved_name, {}) if isinstance(profiles.get(resolved_name, {}), dict) else {}
        return {
            "name": resolved_name,
            "requested": requested_profile,
            "source_env": env_name,
            "enabled": bool(resolved.get("enabled", True)),
            "description": str(resolved.get("description") or ""),
            "task_routing_overrides": dict(resolved.get("task_routing_overrides") or {}),
            "adapter_hint": dict(resolved.get("adapter_hint") or {}),
        }

    def _profile_override_routing(self, task_type: str) -> dict[str, Any] | None:
        profile = self.active_local_profile_info()
        overrides = profile.get("task_routing_overrides") or {}
        if not isinstance(overrides, dict):
            return None
        override = overrides.get(task_type) or overrides.get("default")
        return dict(override) if isinstance(override, dict) else None
    
    def get_model_config(self, model_id: str) -> dict[str, Any]:
        """获取模型配置"""
        return self.model_cache.get(model_id, {})
    
    def get_model_params(self, task_type: str) -> dict[str, Any]:
        """获取任务特定的模型参数"""
        task_params = self.config.get("model_params", {}).get("task_specific", {}).get(task_type)
        if task_params:
            return task_params
        
        # 返回默认参数
        model_params = self.config.get("model_params", {})
        default_keys = ("temperature", "top_p", "max_tokens", "presence_penalty", "frequency_penalty")
        return {k: v for k, v in model_params.items() if k in default_keys}

    def _get_provider_policy(self, model_id: str) -> dict[str, Any]:
        cfg = self.get_model_config(model_id)
        provider = str(cfg.get("provider", "")).strip()
        if not provider:
            return {}
        provider_policies = self.config.get("provider_policies", {})
        policy = provider_policies.get(provider)
        return policy if isinstance(policy, dict) else {}

    def _effective_timeout_sec(self, model_id: str, task_timeout_sec: float) -> float:
        provider_policy = self._get_provider_policy(model_id)
        provider_cap = provider_policy.get("request_timeout_cap_sec")
        if provider_cap is None:
            return task_timeout_sec
        try:
            return max(0.1, min(float(task_timeout_sec), float(provider_cap)))
        except (TypeError, ValueError):
            return task_timeout_sec

    def _to_litellm_model(self, model_id: str) -> str:
        """将 provider:model_name 规范转换为 litellm model 名。"""
        cfg = self.get_model_config(model_id)
        provider_type = str(cfg.get("provider_type", "")).lower()
        model_name = str(cfg.get("name", ""))
        if not provider_type or not model_name:
            return model_id

        if provider_type == "anthropic":
            return f"anthropic/{model_name}"
        if provider_type == "gemini":
            return f"gemini/{model_name}"
        if provider_type == "openai":
            return f"openai/{model_name}"
        if provider_type == "ollama":
            return f"ollama/{model_name}"
        if provider_type == "groq":
            return f"groq/{model_name}"
        return f"{provider_type}/{model_name}"

    # ======================================================================
    # Validation layer
    # ======================================================================

    def validate_schema(
        self,
        text: str,
        schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Validate *text* (assumed JSON) against *schema* using jsonschema.

        Returns::

            {
                "valid": bool,
                "errors": [str, ...],   # empty on success
                "parsed": dict | None,  # parsed object on success
            }
        """
        if schema is None:
            return {"valid": True, "errors": [], "parsed": None}
        try:
            import json as _json
            parsed = _json.loads(text)
        except Exception as exc:
            return {"valid": False, "errors": [f"JSON parse error: {exc}"], "parsed": None}
        try:
            import jsonschema  # type: ignore
            jsonschema.validate(instance=parsed, schema=schema)
            return {"valid": True, "errors": [], "parsed": parsed}
        except ImportError:
            # jsonschema not installed — best-effort key presence check
            missing = [k for k in schema.get("required", []) if k not in parsed]
            if missing:
                return {"valid": False, "errors": [f"Missing required keys: {missing}"], "parsed": parsed}
            return {"valid": True, "errors": [], "parsed": parsed}
        except Exception as exc:
            messages = [str(e.message) for e in exc.context] if hasattr(exc, "context") else [str(exc)]
            return {"valid": False, "errors": messages, "parsed": parsed}

    def score_result(
        self,
        text: str,
        *,
        task_type: str,
        prompt: str,
        min_length: int = 4,
    ) -> dict[str, Any]:
        """Compute a heuristic quality score (0.0–1.0) for *text*.

        Scoring dimensions (each 0–1, equal weight):
        - length_ok     : len(text) >= min_length
        - non_trivial   : not a pure repetition of the prompt
        - no_error_blurb: does not start with an error keyword
        - has_content   : passes the basic _validate_invoke_result gate
        - task_relevant : shares at least one non-stop token with the prompt

        Returns::

            {
                "score": float,       # 0.0 – 1.0
                "dimensions": dict,   # per-dimension bool flags
                "passed": bool,       # score >= threshold (0.5)
            }
        """
        stripped = text.strip()
        error_markers = ("error:", "exception:", "traceback", "connection refused", "timed out")

        length_ok = len(stripped) >= min_length
        non_trivial = stripped.lower() != prompt.lower()[:len(stripped)]
        no_error_blurb = not any(stripped.lower().startswith(m) for m in error_markers)
        has_content = bool(stripped) and len(stripped) >= min_length

        # simple token overlap (ignore very short tokens)
        prompt_tokens = {t.lower() for t in prompt.split() if len(t) > 3}
        result_tokens = {t.lower() for t in stripped.split() if len(t) > 3}
        task_relevant = bool(prompt_tokens & result_tokens) if prompt_tokens else True

        dims = {
            "length_ok": length_ok,
            "non_trivial": non_trivial,
            "no_error_blurb": no_error_blurb,
            "has_content": has_content,
            "task_relevant": task_relevant,
        }
        score = round(sum(dims.values()) / len(dims), 3)
        return {"score": score, "dimensions": dims, "passed": score >= 0.5}

    def validate_tool_calls(
        self,
        response_raw: Any,
    ) -> dict[str, Any]:
        """Inspect a raw LiteLLM response for tool/function calls and validate them.

        Checks:
        - tool_calls present in choices[0].message
        - each call has a non-empty name
        - each call has parseable JSON arguments

        Returns::

            {
                "has_tool_calls": bool,
                "tool_calls": [{"name": str, "args": dict, "valid": bool, "error": str}],
                "all_valid": bool,
            }
        """
        import json as _json

        tool_calls_out: list[dict[str, Any]] = []
        try:
            msg = response_raw.choices[0].message
            raw_calls = getattr(msg, "tool_calls", None) or []
        except Exception:
            return {"has_tool_calls": False, "tool_calls": [], "all_valid": True}

        if not raw_calls:
            return {"has_tool_calls": False, "tool_calls": [], "all_valid": True}

        all_valid = True
        for call in raw_calls:
            name = ""
            args: dict[str, Any] = {}
            error = ""
            try:
                fn = getattr(call, "function", call)
                name = str(getattr(fn, "name", "") or "")
                raw_args = getattr(fn, "arguments", "{}") or "{}"
                args = _json.loads(raw_args)
                valid = bool(name)
                if not valid:
                    error = "empty function name"
            except Exception as exc:
                valid = False
                error = str(exc)
            if not valid:
                all_valid = False
            tool_calls_out.append({"name": name, "args": args, "valid": valid, "error": error})

        return {"has_tool_calls": True, "tool_calls": tool_calls_out, "all_valid": all_valid}

    def _is_local_model(self, model_id: str) -> bool:
        """Return True if *model_id* runs on a local Ollama instance."""
        cfg = self.get_model_config(model_id)
        return str(cfg.get("provider_type", "")).lower() == "ollama"

    def _cloud_escalation_allowed(self, task_type: str) -> bool:
        """Return True when cloud escalation is permitted for *task_type*.

        Checks (in order):
        1. Per-task override in routing_policies.<task_type>.allow_cloud_escalation
        2. Global flag routing_policies.escalation.allow_cloud (default True)
        3. At least one cloud API key must be present in env.
        """
        policies = self.config.get("routing_policies", {})
        task_policy = policies.get(task_type) or {}
        task_flag = task_policy.get("allow_cloud_escalation")
        if task_flag is not None:
            if not task_flag:
                return False
        else:
            global_flag = (policies.get("escalation") or {}).get("allow_cloud", True)
            if not global_flag:
                return False

        cloud_keys = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY")
        return any(os.getenv(k) for k in cloud_keys)

    def _split_local_cloud(self, candidates: list[str]) -> tuple[list[str], list[str]]:
        """Partition *candidates* into (local, cloud) lists preserving order."""
        local = [m for m in candidates if self._is_local_model(m)]
        cloud = [m for m in candidates if not self._is_local_model(m)]
        return local, cloud

    def _validate_invoke_result(self, text: str) -> bool:
        """Basic quality gate — returns False if the result looks empty or like an error blurb."""
        stripped = text.strip()
        if not stripped or len(stripped) < 4:
            return False
        error_markers = ("error:", "exception:", "traceback", "connection refused", "timed out")
        lowered = stripped.lower()
        if any(lowered.startswith(m) for m in error_markers):
            return False
        return True

    def _write_invoke_knowledge(
        self,
        *,
        task_type: str,
        model_id: str,
        prompt_preview: str,
        result_preview: str,
        tier: str,
        score: float = 1.0,
        schema_valid: bool = True,
        schema_errors: list[str] | None = None,
        tool_calls_valid: bool = True,
        tool_calls: list[dict[str, Any]] | None = None,
        runtime_context: dict[str, Any] | None = None,
    ) -> None:
        """Persist a full invocation record (score + schema + tool calls) to the runtime learning store."""
        try:
            from nethub_runtime.config.runtime_paths import SEMANTIC_POLICY_PATH
            from nethub_runtime.memory.runtime_learning_store import RuntimeLearningStore

            store = RuntimeLearningStore(SEMANTIC_POLICY_PATH)
            detail_parts = [
                f"prompt={prompt_preview[:80]}",
                f"result={result_preview[:80]}",
                f"score={score:.3f}",
                f"schema_valid={schema_valid}",
                f"tool_calls_valid={tool_calls_valid}",
            ]
            if schema_errors:
                detail_parts.append(f"schema_errors={schema_errors[:3]}")
            if tool_calls:
                detail_parts.append(f"tool_calls={[c['name'] for c in tool_calls]}")
            if runtime_context:
                detail_parts.append(f"runtime_context={runtime_context}")
            store.record_attempt(
                task_type=task_type,
                gap="model_invocation",
                strategy=f"{tier}_model:{model_id}",
                outcome="success",
                detail="; ".join(detail_parts),
                model_id=model_id,
            )
        except Exception as exc:
            LOGGER.debug("Write to knowledge store skipped: %s", exc)

    def _prepare_runtime_invoke_context(self, task_type: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        sanitized = dict(params)
        explicit_profile = sanitized.pop("local_profile", None)
        explicit_adapter_hint = sanitized.pop("adapter_hint", None)
        profile = explicit_profile if isinstance(explicit_profile, dict) else self.active_local_profile_info()
        adapter_hint = dict(explicit_adapter_hint) if isinstance(explicit_adapter_hint, dict) else dict(profile.get("adapter_hint") or {})
        runtime_context = {
            "task_type": task_type,
            "local_profile": profile,
            "adapter_hint": adapter_hint,
        }
        return sanitized, runtime_context

    async def _invoke_single(
        self,
        model: str,
        messages: list[dict],
        merged_params: dict,
        timeout_sec: float,
        runtime_context: dict[str, Any] | None = None,
    ) -> tuple[str, Any]:
        """Attempt one model invocation (with per-provider retry policy).
        Returns (text, raw_response). Raises on failure.
        """
        from litellm import acompletion

        model_config = self.get_model_config(model)
        provider_policy = self._get_provider_policy(model)
        max_retries = int(provider_policy.get("max_retries", 1))
        retry_backoff_sec = float(provider_policy.get("retry_backoff_sec", 1.0))
        min_interval_ms = int(provider_policy.get("min_request_interval_ms", 0))
        litellm_model = self._to_litellm_model(model)
        request_timeout_sec = self._effective_timeout_sec(model, timeout_sec)

        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                if min_interval_ms > 0:
                    await asyncio.sleep(min_interval_ms / 1000.0)
                if runtime_context and str(model_config.get("provider_type") or "").lower() == "ollama":
                    LOGGER.info(
                        "Applying local runtime context for %s: profile=%s adapter_hint=%s",
                        litellm_model,
                        (runtime_context.get("local_profile") or {}).get("name", "base_local"),
                        runtime_context.get("adapter_hint") or {},
                    )
                response = await acompletion(
                    model=litellm_model,
                    messages=messages,
                    timeout=request_timeout_sec,
                    api_base=model_config.get("base_url"),
                    api_key=model_config.get("api_key"),
                    **merged_params,
                )
                return response.choices[0].message.content or "", response
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    wait_sec = retry_backoff_sec * (2 ** attempt)
                    LOGGER.warning(
                        "Model invoke retrying (%s) attempt=%s wait=%.2fs error=%s",
                        litellm_model, attempt + 1, wait_sec, exc,
                    )
                    await asyncio.sleep(wait_sec)
        raise last_exc or RuntimeError(f"Invoke failed for {model}")

    async def _invoke_candidates(
        self,
        candidates: list[str],
        messages: list[dict],
        merged_params: dict,
        timeout_sec: float,
        tier: str,
        task_type: str,
        prompt_preview: str,
        output_schema: dict[str, Any] | None = None,
        runtime_context: dict[str, Any] | None = None,
    ) -> str | None:
        """Try *candidates* in order.

        For each candidate:
          1. Call the model
          2. Schema-validate the output (if output_schema provided)
          3. Score the result
          4. Validate tool calls in the raw response
          5. Write everything to the knowledge store
        Returns the first result that passes the score gate, or None.
        """
        for model in candidates:
            if self.cooldown_tracker.is_in_cooldown(model):
                rem = self.cooldown_tracker.status().get(model, {}).get("remaining_seconds", "?")
                LOGGER.info("Skipping %s — cooldown %.0fs remaining", model, rem)
                continue
            if not await self._candidate_is_ready(model, timeout_sec):
                continue
            try:
                if runtime_context:
                    LOGGER.info(
                        "[%s tier] invoking %s for %s with local_profile=%s",
                        tier,
                        model,
                        task_type,
                        (runtime_context.get("local_profile") or {}).get("name", "base_local"),
                    )
                else:
                    LOGGER.info("[%s tier] invoking %s for %s", tier, model, task_type)
                text, raw_response = await self._invoke_single(model, messages, merged_params, timeout_sec, runtime_context=runtime_context)

                # ── Schema validation ────────────────────────────────────────
                schema_result = self.validate_schema(text, output_schema)
                if output_schema and not schema_result["valid"]:
                    LOGGER.warning(
                        "[%s tier] %s schema invalid: %s", tier, model, schema_result["errors"]
                    )

                # ── Result scoring ───────────────────────────────────────────
                user_prompt = next(
                    (m["content"] for m in reversed(messages) if m.get("role") == "user"
                     and isinstance(m.get("content"), str)),
                    prompt_preview,
                )
                score_result = self.score_result(text, task_type=task_type, prompt=user_prompt)

                # ── Tool-call validation ────────────────────────────────────
                tool_result = self.validate_tool_calls(raw_response)
                if tool_result["has_tool_calls"] and not tool_result["all_valid"]:
                    LOGGER.warning(
                        "[%s tier] %s has invalid tool calls: %s",
                        tier, model,
                        [c for c in tool_result["tool_calls"] if not c["valid"]],
                    )

                passed = score_result["passed"] or (output_schema is None and self._validate_invoke_result(text))
                if passed:
                    self.cooldown_tracker.reset(model)
                    self._write_invoke_knowledge(
                        task_type=task_type,
                        model_id=model,
                        prompt_preview=prompt_preview,
                        result_preview=text[:120],
                        tier=tier,
                        score=score_result["score"],
                        schema_valid=schema_result["valid"],
                        schema_errors=schema_result["errors"],
                        tool_calls_valid=tool_result["all_valid"],
                        tool_calls=tool_result["tool_calls"],
                        runtime_context=runtime_context,
                    )
                    LOGGER.info(
                        "[%s tier] %s accepted — score=%.3f schema_valid=%s tool_calls_valid=%s",
                        tier, model, score_result["score"],
                        schema_result["valid"], tool_result["all_valid"],
                    )
                    return text

                LOGGER.warning(
                    "[%s tier] %s rejected — score=%.3f dims=%s",
                    tier, model, score_result["score"], score_result["dimensions"],
                )
                self.cooldown_tracker.reset(model)
            except Exception as exc:
                self.cooldown_tracker.record_failure(model)
                LOGGER.warning("[%s tier] %s failed: %s", tier, self._to_litellm_model(model), exc)
        return None

    async def invoke(
        self,
        task_type: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        output_schema: dict[str, Any] | None = None,
        **kwargs
    ) -> str:
        """Tiered model invocation.

        Args:
            output_schema: Optional JSON Schema dict. When provided the response
                text is parsed as JSON and validated; schema errors are logged
                and written to the knowledge store.

        Flow:
          1. Rule layer  — mock / fast-path guard
          2. Local tier  — Ollama models (Qwen / DeepSeek)
          3. Escalation  — check allow_cloud_escalation gate
          4. Cloud tier  — Groq / Gemini / OpenAI / Anthropic
          5. Schema validation + scoring + tool-call check + knowledge-base write
        """
        task_params = self.get_model_params(task_type)
        timeout_sec = float(
            self.config.get("routing_policies", {}).get(task_type, {}).get("timeout_sec")
            or self.config.get("routing_policies", {}).get("default", {}).get("timeout_sec")
            or 30
        )
        merged_params, runtime_context = self._prepare_runtime_invoke_context(task_type, {**task_params, **kwargs})

        # ── 1. Rule layer: mock fast-path ──────────────────────────────────
        if self.mock_llm_calls:
            model = self.select_model(task_type)
            LOGGER.info("mock_llm_calls enabled, returning mock response for %s", model)
            return f"Model response (mock): {prompt[:80]}..."

        try:
            from litellm import acompletion as _  # noqa: F401 — ensure litellm available
        except ImportError:
            LOGGER.warning("litellm is not installed, using mock response")
            return f"Model response (mock): {prompt[:50]}..."

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        candidates = self.get_candidate_models(task_type)
        if not candidates:
            raise RuntimeError(f"No available models configured for task_type={task_type}")

        local_models, cloud_models = self._split_local_cloud(candidates)
        prompt_preview = prompt[:120]

        # ── 2. Local tier ──────────────────────────────────────────────────
        if local_models:
            result = await self._invoke_candidates(
                local_models, messages, merged_params, timeout_sec,
                tier="local", task_type=task_type, prompt_preview=prompt_preview,
                output_schema=output_schema, runtime_context=runtime_context,
            )
            if result is not None:
                return result
            LOGGER.info("Local tier exhausted for %s — checking escalation", task_type)

        # ── 3. Escalation gate ─────────────────────────────────────────────
        if not cloud_models:
            raise RuntimeError(f"All local models failed for task_type={task_type} and no cloud models configured")

        if not self._cloud_escalation_allowed(task_type):
            raise RuntimeError(
                f"Local models failed for task_type={task_type} and cloud escalation is disabled"
            )
        LOGGER.info("Escalating to cloud tier for %s (%d candidates)", task_type, len(cloud_models))

        # ── 4. Cloud tier ──────────────────────────────────────────────────
        result = await self._invoke_candidates(
            cloud_models, messages, merged_params, timeout_sec,
            tier="cloud", task_type=task_type, prompt_preview=prompt_preview,
            output_schema=output_schema, runtime_context=runtime_context,
        )
        if result is not None:
            return result

        raise RuntimeError(f"All model tiers exhausted for task_type={task_type}")

    async def invoke_multimodal(
        self,
        task_type: str,
        user_content: list[dict[str, Any]],
        system_prompt: Optional[str] = None,
        output_schema: dict[str, Any] | None = None,
        **kwargs,
    ) -> str:
        """Tiered multimodal invocation (same local → cloud escalation flow as invoke())."""
        task_params = self.get_model_params(task_type)
        timeout_sec = float(
            self.config.get("routing_policies", {}).get(task_type, {}).get("timeout_sec")
            or self.config.get("routing_policies", {}).get("default", {}).get("timeout_sec")
            or 30
        )
        merged_params, runtime_context = self._prepare_runtime_invoke_context(task_type, {**task_params, **kwargs})

        if self.mock_llm_calls:
            model = self.select_model(task_type)
            LOGGER.info("mock_llm_calls enabled, returning multimodal mock response for %s", model)
            text_parts = [str(item.get("text") or "") for item in user_content if item.get("type") == "text"]
            preview = " ".join(p for p in text_parts if p).strip()
            return f"Model response (mock): {preview[:80]}..."

        try:
            from litellm import acompletion as _  # noqa: F401
        except ImportError:
            LOGGER.warning("litellm is not installed, using multimodal mock response")
            text_parts = [str(item.get("text") or "") for item in user_content if item.get("type") == "text"]
            return f"Model response (mock): {' '.join(text_parts)[:50]}..."

        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_content})

        candidates = self.get_candidate_models(task_type)
        if not candidates:
            raise RuntimeError(f"No available models configured for task_type={task_type}")

        local_models, cloud_models = self._split_local_cloud(candidates)
        text_preview = " ".join(
            str(item.get("text") or "") for item in user_content if item.get("type") == "text"
        )[:120]

        # ── Local tier ─────────────────────────────────────────────────────
        if local_models:
            result = await self._invoke_candidates(
                local_models, messages, merged_params, timeout_sec,
                tier="local", task_type=task_type, prompt_preview=text_preview,
                output_schema=output_schema, runtime_context=runtime_context,
            )
            if result is not None:
                return result

        # ── Escalation gate ────────────────────────────────────────────────
        if not cloud_models:
            raise RuntimeError(f"All local models failed for task_type={task_type} and no cloud models configured")
        if not self._cloud_escalation_allowed(task_type):
            raise RuntimeError(f"Local models failed and cloud escalation is disabled for {task_type}")
        LOGGER.info("Escalating multimodal to cloud tier for %s", task_type)

        # ── Cloud tier ─────────────────────────────────────────────────────
        result = await self._invoke_candidates(
            cloud_models, messages, merged_params, timeout_sec,
            tier="cloud", task_type=task_type, prompt_preview=text_preview,
            output_schema=output_schema, runtime_context=runtime_context,
        )
        if result is not None:
            return result

        raise RuntimeError(f"All model tiers exhausted for task_type={task_type}")

    
    def list_available_models(self) -> list[str]:
        """列出所有可用模型"""
        return list(self.model_cache.keys())
    
    def reload_config(self, config_path: Optional[str | Path] = None) -> None:
        """重新加载配置（支持热更新）"""
        if config_path:
            self.config_path = Path(config_path)
        
        self.config.clear()
        self.model_cache.clear()
        self.fallback_chain.clear()
        
        self._load_config()
        self._initialize_models()
        
        LOGGER.info("✓ Model routing config reloaded")
