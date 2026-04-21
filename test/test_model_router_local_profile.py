from __future__ import annotations

from pathlib import Path

from nethub_runtime.models.model_router import ModelRouter


def test_model_router_exposes_active_local_profile(monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_ACTIVE_LORA_PROFILE", "lora_sft")

    router = ModelRouter(Path("/home/lw-ai/Documents/nesthub/nethub_runtime/config/model_config.yaml"))
    profile = router.active_local_profile_info()

    assert profile["name"] == "lora_sft"
    assert profile["adapter_hint"]["training_profile"] == "lora_sft"


def test_model_router_profile_override_preserves_local_first_candidate_order(monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_ACTIVE_LORA_PROFILE", "lora_sft")

    router = ModelRouter(Path("/home/lw-ai/Documents/nesthub/nethub_runtime/config/model_config.yaml"))
    router.model_cache = {
        "ollama:qwen2.5:7b-instruct": {"provider": "ollama", "provider_type": "ollama", "name": "qwen2.5:7b-instruct"},
        "ollama:qwen2.5:3b-instruct": {"provider": "ollama", "provider_type": "ollama", "name": "qwen2.5:3b-instruct"},
        "groq:llama-3.1-8b-instant": {"provider": "groq", "provider_type": "groq", "name": "llama-3.1-8b-instant"},
    }

    candidates = router.get_candidate_models("semantic_parsing")

    assert candidates[0] == "ollama:qwen2.5:7b-instruct"
    assert candidates[1] == "ollama:qwen2.5:3b-instruct"


def test_model_router_prepare_runtime_context_strips_internal_adapter_fields(monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_ACTIVE_LORA_PROFILE", "lora_sft")

    router = ModelRouter(Path("/home/lw-ai/Documents/nesthub/nethub_runtime/config/model_config.yaml"))
    sanitized, runtime_context = router._prepare_runtime_invoke_context(
        "semantic_parsing",
        {
            "temperature": 0.1,
            "local_profile": {"name": "lora_sft", "adapter_hint": {"training_profile": "lora_sft"}},
            "adapter_hint": {"training_profile": "lora_sft", "mode": "lora"},
        },
    )

    assert sanitized == {"temperature": 0.1}
    assert runtime_context["local_profile"]["name"] == "lora_sft"
    assert runtime_context["adapter_hint"]["mode"] == "lora"