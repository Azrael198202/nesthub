from __future__ import annotations

from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = CORE_ROOT / "config"
MODEL_ROUTES_PATH = CONFIG_DIR / "model_routes.json"
DEPENDENCIES_PATH = CONFIG_DIR / "dependencies.json"


def ensure_core_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR
