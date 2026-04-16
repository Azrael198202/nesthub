from __future__ import annotations

from nethub_runtime.core.services.capability_router import CapabilityRouter


def test_runtime_capabilities_expose_autonomous_implementation() -> None:
    router = CapabilityRouter()

    autonomous = router._capabilities.get("autonomous_implementation")

    assert isinstance(autonomous, dict)
    assert autonomous["enabled"] is True
    assert "capability_gap_resolution" in autonomous["supports"]
    assert "code_patch_generation" in autonomous["supports"]
    assert autonomous["safety_rules"]["require_tests_for_new_logic"] is True
    assert autonomous["safety_rules"]["allow_runtime_generated_code"] is True


def test_runtime_capabilities_keep_codegen_models_declared() -> None:
    router = CapabilityRouter()

    models = router._capabilities.get("models", [])
    codegen_models = {item["name"] for item in models if "code_generation" in item.get("supports", [])}
    autonomous = router._capabilities.get("autonomous_implementation", {})

    assert codegen_models
    assert set(autonomous.get("code_generation_models", [])) <= codegen_models