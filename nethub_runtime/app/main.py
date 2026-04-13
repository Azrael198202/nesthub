from __future__ import annotations

import logging
from typing import Any

from nethub_runtime.app.bootstrap import bootstrap_runtime

LOGGER = logging.getLogger("nethub_runtime.app.main")


def start_app() -> dict[str, Any]:
    """
    Application initialization entry.

    Responsibilities:
    - bootstrap runtime
    - initialize core components
    - return shared application context
    """
    LOGGER.info("🔧 Initializing application...")

    context = bootstrap_runtime()

    # 这里可以扩展初始化 execution / agent 等
    context["status"] = "ready"

    LOGGER.info("✅ Application initialized.")

    return context


# 👉 允许单独调试
if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    ctx = start_app()

    print("\n=== App Context ===")
    for k, v in ctx.items():
        print(f"{k}: {v}")