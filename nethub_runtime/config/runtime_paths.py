from __future__ import annotations

import shutil
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_CONFIG_DIR = RUNTIME_ROOT / "config" / "runtime"
RUNTIME_REGISTRIES_DIR = RUNTIME_ROOT / "generated" / "registries"

LEGACY_CORE_CONFIG_DIR = RUNTIME_ROOT / "core" / "config"
LEGACY_CORE_REGISTRIES_DIR = RUNTIME_ROOT / "core" / "registries"

LOCAL_MODEL_REGISTRY_PATH = RUNTIME_CONFIG_DIR / "local_model_registry.json"
MODEL_ROUTES_PATH = RUNTIME_CONFIG_DIR / "model_routes.json"
DEPENDENCIES_PATH = RUNTIME_CONFIG_DIR / "dependencies.json"
INTENT_POLICY_PATH = RUNTIME_CONFIG_DIR / "intent_policy.json"
RUNTIME_CAPABILITIES_PATH = RUNTIME_CONFIG_DIR / "runtime_capabilities.json"
MODEL_ROUTING_POLICY_PATH = RUNTIME_CONFIG_DIR / "model_routing_policy.json"
VECTOR_STORE_POLICY_PATH = RUNTIME_CONFIG_DIR / "vector_store_policy.json"
PLUGIN_CONFIG_PATH = RUNTIME_CONFIG_DIR / "plugin_config.json"
SECURITY_POLICY_PATH = RUNTIME_CONFIG_DIR / "security_policy.json"
SEMANTIC_POLICY_PATH = RUNTIME_CONFIG_DIR / "semantic_policy.json"
SEMANTIC_POLICY_MEMORY_DB_PATH = RUNTIME_CONFIG_DIR / "semantic_policy_memory.sqlite3"

MODEL_REGISTRY_PATH = RUNTIME_REGISTRIES_DIR / "models.json"
BLUEPRINT_REGISTRY_PATH = RUNTIME_REGISTRIES_DIR / "blueprints.json"
AGENT_REGISTRY_PATH = RUNTIME_REGISTRIES_DIR / "agents.json"

_MIGRATION_FILES = (
    "local_model_registry.json",
    "model_routes.json",
    "dependencies.json",
    "intent_policy.json",
    "runtime_capabilities.json",
    "model_routing_policy.json",
    "vector_store_policy.json",
    "plugin_config.json",
    "security_policy.json",
    "semantic_policy.json",
    "semantic_policy_memory.sqlite3",
)


def ensure_runtime_config_dir() -> Path:
    RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_REGISTRIES_DIR.mkdir(parents=True, exist_ok=True)

    if LEGACY_CORE_CONFIG_DIR.exists():
        for filename in _MIGRATION_FILES:
            legacy_path = LEGACY_CORE_CONFIG_DIR / filename
            target_path = RUNTIME_CONFIG_DIR / filename
            if legacy_path.exists() and not target_path.exists():
                if legacy_path.is_file():
                    shutil.copy2(legacy_path, target_path)

    if LEGACY_CORE_REGISTRIES_DIR.exists():
        for filename in ("models.json", "blueprints.json", "agents.json"):
            legacy_path = LEGACY_CORE_REGISTRIES_DIR / filename
            target_path = RUNTIME_REGISTRIES_DIR / filename
            if legacy_path.exists() and not target_path.exists():
                shutil.copy2(legacy_path, target_path)

    return RUNTIME_CONFIG_DIR
