from __future__ import annotations

import logging
from typing import Any

from nethub_runtime.app.bootstrap import bootstrap_runtime

LOGGER = logging.getLogger("nethub_runtime.app.main")


def start_app() -> dict[str, Any]:
    """
    Application initialization entry.

    Responsibilities:
    - bootstrap runtime environment
    - load registries and configuration
    - prepare execution pipeline
    - return application context
    """
    LOGGER.info("Initializing application runtime...")

    context = bootstrap_runtime()

    LOGGER.info("Application runtime initialized.")
    return context


if __name__ == "__main__":
    # Usually this file is called by nethub_runtime/main.py
    # but it can also be executed directly for debugging.
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    ctx = start_app()
    print("Application context loaded:")
    print(ctx)