from __future__ import annotations

from pathlib import Path
from typing import Any

from nethub_runtime.core_brain.engine import CoreBrainEngine


def create_core_engine(model_config_path: str | Path | None = None) -> Any:
    # model_config_path is kept for compatibility with old callsites.
    _ = model_config_path
    return CoreBrainEngine()


def active_core_engine_variant() -> str:
    return "core_brain"
