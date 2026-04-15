from __future__ import annotations

from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = CORE_ROOT / "config"
REGISTRIES_DIR = CORE_ROOT / "registries"
MODEL_ROUTES_PATH = CONFIG_DIR / "model_routes.json"
DEPENDENCIES_PATH = CONFIG_DIR / "dependencies.json"
INTENT_POLICY_PATH = CONFIG_DIR / "intent_policy.json"
RUNTIME_CAPABILITIES_PATH = CONFIG_DIR / "runtime_capabilities.json"
MODEL_ROUTING_POLICY_PATH = CONFIG_DIR / "model_routing_policy.json"
LOCAL_MODEL_REGISTRY_PATH = CONFIG_DIR / "local_model_registry.json"
VECTOR_STORE_POLICY_PATH = CONFIG_DIR / "vector_store_policy.json"
PLUGIN_CONFIG_PATH = CONFIG_DIR / "plugin_config.json"
SECURITY_POLICY_PATH = CONFIG_DIR / "security_policy.json"
SEMANTIC_POLICY_PATH = CONFIG_DIR / "semantic_policy.json"
MODEL_REGISTRY_PATH = REGISTRIES_DIR / "models.json"
BLUEPRINT_REGISTRY_PATH = REGISTRIES_DIR / "blueprints.json"
AGENT_REGISTRY_PATH = REGISTRIES_DIR / "agents.json"


def ensure_core_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRIES_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def load_local_env(env_path: Path | None = None) -> None:
    """
    Lightweight .env loader.
    - Does not override existing environment variables.
    - Ignores comments and blank lines.
    """
    import os

    target = env_path or (CORE_ROOT.parent.parent / ".env")
    if not target.exists():
        return
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
