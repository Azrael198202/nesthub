from __future__ import annotations

from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = CORE_ROOT / "config"
MODEL_ROUTES_PATH = CONFIG_DIR / "model_routes.json"
DEPENDENCIES_PATH = CONFIG_DIR / "dependencies.json"
INTENT_POLICY_PATH = CONFIG_DIR / "intent_policy.json"
RUNTIME_CAPABILITIES_PATH = CONFIG_DIR / "runtime_capabilities.json"
MODEL_ROUTING_POLICY_PATH = CONFIG_DIR / "model_routing_policy.json"
LOCAL_MODEL_REGISTRY_PATH = CONFIG_DIR / "local_model_registry.json"
VECTOR_STORE_POLICY_PATH = CONFIG_DIR / "vector_store_policy.json"


def ensure_core_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR
