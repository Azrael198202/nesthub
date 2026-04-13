from __future__ import annotations

import logging
import time

LOGGER = logging.getLogger("nethub_runtime.ui.tvbox.main")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def start_ui() -> None:
    """
    TV Box local UI entry.

    This is currently a placeholder loop.
    Later you can replace it with:
    - FastAPI + local web UI
    - Flask
    - PySide6
    - Tkinter
    - WebView / kiosk frontend
    """
    LOGGER.info("TV Box UI starting...")
    LOGGER.info("TV Box UI ready.")

    try:
        while True:
            time.sleep(5)
            LOGGER.debug("TV Box UI heartbeat...")
    except KeyboardInterrupt:
        LOGGER.info("TV Box UI stopped by user.")


def main() -> None:
    setup_logging()
    start_ui()


if __name__ == "__main__":
    main()