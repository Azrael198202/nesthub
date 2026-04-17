from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from nethub_runtime.models.model_router import ModelRouter


def test_model_router_load_and_select() -> None:
    router = ModelRouter("nethub_runtime/config/model_config.yaml")
    models = router.list_available_models()
    assert len(models) > 0

    selected = router.select_model("intent_analysis")
    assert isinstance(selected, str)
    assert ":" in selected


def test_model_router_mock_invoke() -> None:
    router = ModelRouter("nethub_runtime/config/model_config.yaml")
    router.mock_llm_calls = True

    result = asyncio.run(
        router.invoke(
            task_type="intent_analysis",
            prompt="分析这句话",
            system_prompt="只输出JSON",
        )
    )
    assert isinstance(result, str)
    assert "mock" in result.lower()


def test_model_router_skips_unhealthy_ollama_candidate(monkeypatch) -> None:
    router = ModelRouter("nethub_runtime/config/model_config.yaml")
    router.mock_llm_calls = False
    router.model_cache = {
        "openai:gpt-4o": {
            "provider": "openai",
            "provider_type": "openai",
            "name": "gpt-4o",
            "base_url": None,
            "api_key": "test-key",
        },
        "ollama:qwen2.5:7b-instruct": {
            "provider": "ollama",
            "provider_type": "ollama",
            "name": "qwen2.5:7b-instruct",
            "base_url": "http://localhost:11434",
            "api_key": None,
        },
    }
    router.config["routing_policies"]["test_ollama_fallback"] = {
        "primary": "ollama:qwen2.5:7b-instruct",
        "fallback": ["openai:gpt-4o"],
        "timeout_sec": 5,
    }

    monkeypatch.setattr(router, "_ollama_is_healthy", AsyncMock(return_value=False))

    async def fake_acompletion(**kwargs):
        class Message:
            content = "ok"

        class Choice:
            message = Message()

        class Response:
            choices = [Choice()]

        return Response()

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    result = asyncio.run(router.invoke("test_ollama_fallback", "hello"))

    assert result == "ok"
