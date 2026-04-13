from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "nethub_runtime"


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
