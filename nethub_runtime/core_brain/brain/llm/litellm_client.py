from __future__ import annotations

import json
import os
from typing import Any


class LiteLLMClient:
    def __init__(self) -> None:
        self._litellm_completion = None
        enabled = str(os.getenv("NETHUB_CORE_BRAIN_ENABLE_LITELLM", "")).strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return
        try:
            from litellm import completion  # type: ignore

            self._litellm_completion = completion
        except Exception:
            self._litellm_completion = None

    async def call(self, model_config: dict[str, Any], messages: list[dict[str, str]]) -> str:
        model_name = str(model_config.get("model") or "")
        fallback_name = str(model_config.get("fallback") or "")

        if self._litellm_completion is None or not model_name:
            return self._mock_response(messages)

        try:
            response = self._litellm_completion(model=model_name, messages=messages)
            return self._extract_text(response)
        except Exception:
            if fallback_name:
                try:
                    response = self._litellm_completion(model=fallback_name, messages=messages)
                    return self._extract_text(response)
                except Exception:
                    pass
            return self._mock_response(messages)

    def _extract_text(self, response: Any) -> str:
        choices = getattr(response, "choices", None)
        if choices:
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None)
            if isinstance(content, str) and content.strip():
                return content

        if isinstance(response, dict):
            try:
                content = response["choices"][0]["message"]["content"]
                if isinstance(content, str) and content.strip():
                    return content
            except Exception:
                pass
        return ""

    def _mock_response(self, messages: list[dict[str, str]]) -> str:
        user_msg = ""
        for item in reversed(messages):
            if item.get("role") == "user":
                user_msg = str(item.get("content") or "")
                break

        if "intent" in str(messages[0].get("content") if messages else "").lower():
            lowered = user_msg.lower()
            intent_name = "general_chat"
            if any(word in lowered for word in ["agent", "智能体"]):
                intent_name = "agent_creation"
            elif any(word in lowered for word in ["workflow", "流程", "计划"]):
                intent_name = "workflow_decomposition"
            return json.dumps({"intent_name": intent_name, "confidence": 0.72})

        return f"已收到请求：{user_msg}"
