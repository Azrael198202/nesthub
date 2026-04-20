from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "nethub_runtime"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
GENERATED_ROOT = PACKAGE_ROOT / "generated"


def generated_root() -> Path:
    env = os.getenv("NETHUB_GENERATED_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return GENERATED_ROOT


def app_home() -> Path:
    env = os.getenv("NETHUB_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".nethub"


def ensure_app_dirs() -> dict[str, Path]:
    root = app_home()
    paths = {
        "root": root,
        "cache": root / "cache",
        "registry": root / "registry",
        "logs": root / "logs",
        "blueprints": root / "blueprints",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def ensure_generated_dirs() -> dict[str, Path]:
    root = generated_root()
    datasets_root = root / "datasets"
    paths = {
        "root": root,
        "code": root / "code",
        "blueprints": root / "blueprints",
        "agents": root / "agents",
        "features": root / "features",
        "traces": root / "traces",
        "datasets": datasets_root,
        "datasets_sft": datasets_root / "sft",
        "datasets_preferences": datasets_root / "preferences",
        "datasets_manifests": datasets_root / "manifests",
        "datasets_runs": datasets_root / "runs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
