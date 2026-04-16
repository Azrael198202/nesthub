from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "nethub_runtime"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
GENERATED_ROOT = PACKAGE_ROOT / "generated"


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
    paths = {
        "root": GENERATED_ROOT,
        "code": GENERATED_ROOT / "code",
        "blueprints": GENERATED_ROOT / "blueprints",
        "agents": GENERATED_ROOT / "agents",
        "features": GENERATED_ROOT / "features",
        "traces": GENERATED_ROOT / "traces",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
