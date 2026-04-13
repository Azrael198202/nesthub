from __future__ import annotations

import logging
from typing import Any

from nethub_runtime.capability.registry import CapabilityRegistry
from nethub_runtime.environment.manager import EnvironmentManager
from nethub_runtime.platform.detector import detect_runtime_profile

LOGGER = logging.getLogger("nethub_runtime.app.bootstrap")


def bootstrap_runtime() -> dict[str, Any]:
    """
    Bootstrap the runtime context.

    Responsibilities:
    - detect current platform
    - initialize capability registry
    - initialize environment manager
    - prepare shared runtime context
    """
    LOGGER.info("Bootstrapping runtime...")

    profile = detect_runtime_profile()

    registry = CapabilityRegistry()
    registry_state = registry.refresh_local_snapshot()

    env_manager = EnvironmentManager(registry=registry)

    context: dict[str, Any] = {
        "runtime_profile": profile.model_dump() if hasattr(profile, "model_dump") else profile,
        "registry_state": registry_state.model_dump() if hasattr(registry_state, "model_dump") else registry_state,
        "environment_manager": env_manager,
        "start_tvbox_ui": True,
    }

    LOGGER.info("Bootstrap completed.")
    return context