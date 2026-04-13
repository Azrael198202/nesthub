# nethub_runtime/app/bootstrap.py

from __future__ import annotations

import logging
from typing import Any

from nethub_runtime.capability.registry import CapabilityRegistry
from nethub_runtime.environment.manager import EnvironmentManager
from nethub_runtime.platform.detector import detect_runtime_profile

LOGGER = logging.getLogger("nethub_runtime.app.bootstrap")


def bootstrap_runtime() -> dict[str, Any]:
    LOGGER.info("🚀 Bootstrapping runtime...")

    # 1. 平台检测
    profile = detect_runtime_profile()

    # 2. capability 注册
    registry = CapabilityRegistry()
    registry_state = registry.refresh_local_snapshot()

    # 3. environment manager
    env_manager = EnvironmentManager(registry=registry)

    context: dict[str, Any] = {
        "runtime_profile": profile,
        "registry": registry,
        "registry_state": registry_state,
        "environment_manager": env_manager,

        # 👉 控制 main.py 行为
        "start_tvbox_ui": True,
        "start_local_api": False,
    }

    LOGGER.info("✅ Bootstrap completed.")

    return context