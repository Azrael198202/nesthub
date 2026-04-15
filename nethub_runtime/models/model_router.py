"""
LiteLLM-based Model Router - Unified LLM interface management.
Reference: docs/02_router/litellm_routing_design.md
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional
from pathlib import Path

import yaml

LOGGER = logging.getLogger("nethub_runtime.models")


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
        
        self._load_config()
        self._initialize_models()
    
    def _load_config(self) -> None:
        """加载模型配置文件"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
                self.mock_llm_calls = bool(self.config.get("development", {}).get("mock_llm_calls", False))
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

        try:
            LOGGER.info("Initializing provider: %s (%s)", provider_key, normalized_type)
            for model in models:
                model_cfg = self._normalize_model_config(model)
                if not model_cfg:
                    continue
                if not model_cfg.get("enabled", True):
                    continue

                model_name = str(model_cfg.get("name"))
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
    
    def select_model(self, task_type: str) -> str:
        """
        根据任务类型选择最合适的模型
        
        Args:
            task_type: 任务类型 (intent_analysis / task_planning / code_generation 等)
        
        Returns:
            选中的模型名称 (provider/model_name)
        """
        policies = self.config.get("routing_policies", {})
        routing = policies.get(task_type)
        
        if not routing:
            # 使用默认路由
            default_routing = policies.get("default") or policies.get("general_chat", {})
            routing = default_routing
        
        if not routing:
            return self._get_any_available_model()
        
        primary = routing.get("primary", "")
        
        # 检查primary是否可用
        if self._is_model_available(primary):
            LOGGER.info(f"✓ Selected primary model for {task_type}: {primary}")
            return primary
        
        # 尝试fallback
        for fallback_model in routing.get("fallback", []):
            if self._is_model_available(fallback_model):
                LOGGER.info(f"⚠ Fallback to {fallback_model} for {task_type}")
                return fallback_model
        
        LOGGER.warning(f"No model available for task: {task_type}, using any available")
        return self._get_any_available_model()
    
    def _is_model_available(self, model_id: str) -> bool:
        """检查模型是否可用"""
        return model_id in self.model_cache
    
    def _get_any_available_model(self) -> str:
        """获取任何可用的模型"""
        if not self.model_cache:
            LOGGER.warning("No models available!")
            return "unknown"
        return list(self.model_cache.keys())[0]
    
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
    
    async def invoke(
        self,
        task_type: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        调用模型
        
        Args:
            task_type: 任务类型
            prompt: 用户提示
            system_prompt: 系统提示
            **kwargs: 其他参数（temperature, top_p等）
        
        Returns:
            模型响应
        """
        model = self.select_model(task_type)
        model_config = self.get_model_config(model)
        task_params = self.get_model_params(task_type)
        timeout_sec = (
            self.config.get("routing_policies", {}).get(task_type, {}).get("timeout_sec")
            or self.config.get("routing_policies", {}).get("default", {}).get("timeout_sec")
            or 30
        )
        provider_policy = self._get_provider_policy(model)
        max_retries = int(provider_policy.get("max_retries", 1))
        retry_backoff_sec = float(provider_policy.get("retry_backoff_sec", 1.0))
        min_interval_ms = int(provider_policy.get("min_request_interval_ms", 0))
        
        # 合并参数
        merged_params = {**task_params}
        merged_params.update(kwargs)
        
        LOGGER.debug(f"Invoking {model} for {task_type}")
        LOGGER.debug(f"Params: {merged_params}")

        if self.mock_llm_calls:
            LOGGER.info("mock_llm_calls enabled, returning mock response for %s", model)
            return f"Model response (mock): {prompt[:80]}..."
        
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        litellm_model = self._to_litellm_model(model)
        try:
            from litellm import acompletion
        except ImportError:
            LOGGER.warning("litellm is not installed, using mock response")
            return f"Model response (mock): {prompt[:50]}..."

        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                if min_interval_ms > 0:
                    await asyncio.sleep(min_interval_ms / 1000.0)

                response = await acompletion(
                    model=litellm_model,
                    messages=messages,
                    timeout=timeout_sec,
                    api_base=model_config.get("base_url"),
                    api_key=model_config.get("api_key"),
                    **merged_params,
                )
                return response.choices[0].message.content or ""
            except Exception as exc:
                last_exc = exc
                if attempt >= max_retries:
                    break
                wait_sec = retry_backoff_sec * (2**attempt)
                LOGGER.warning(
                    "Model invoke retrying (%s) attempt=%s wait=%.2fs error=%s",
                    litellm_model,
                    attempt + 1,
                    wait_sec,
                    exc,
                )
                await asyncio.sleep(wait_sec)

        LOGGER.error("Model invoke failed (%s): %s", litellm_model, last_exc)
        raise last_exc or RuntimeError("Model invoke failed")
    
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
