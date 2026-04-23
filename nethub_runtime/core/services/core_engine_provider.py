from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from nethub_runtime.core.services.core_engine import AICore


def _variant_name() -> str:
    return os.getenv("NETHUB_CORE_ENGINE_VARIANT", "legacy").strip().lower()


@lru_cache(maxsize=1)
def _load_core_plus_engine_class() -> type[Any]:
    engine_path = Path(__file__).resolve().parents[1].parent / "core+" / "engine.py"
    spec = importlib.util.spec_from_file_location("nethub_runtime.core_plus_dynamic.engine", engine_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load core+ engine from {engine_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine_class = getattr(module, "CorePlusEngine", None)
    if engine_class is None:
        raise ImportError("core+ engine module does not export CorePlusEngine")
    return engine_class


def create_core_engine(model_config_path: str | Path | None = None) -> Any:
    variant = _variant_name()
    if variant in {"core_plus", "core+", "plus"}:
        engine_class = _load_core_plus_engine_class()
        return engine_class(model_config_path=model_config_path)
    return AICore(model_config_path=model_config_path)


def active_core_engine_variant() -> str:
    return "core_plus" if _variant_name() in {"core_plus", "core+", "plus"} else "legacy"