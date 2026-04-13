from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from nethub_runtime.app.main import start_app

LOGGER = logging.getLogger("nethub_runtime.main")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def start_tvbox_ui() -> subprocess.Popen[str]:
    """
    Start the TV Box local UI as a child process.

    Returns:
        subprocess.Popen: The spawned UI process handle.
    """
    cmd = [sys.executable, "-m", "nethub_runtime.ui.tvbox.main"]
    LOGGER.info("Starting TV Box UI: %s", " ".join(cmd))
    return subprocess.Popen(
        cmd,
        stdout=None,
        stderr=None,
        text=True,
    )


def main() -> None:
    """
    System entry point.

    Responsibilities:
    - initialize logging
    - bootstrap application runtime
    - optionally launch TV Box UI
    """
    setup_logging()
    LOGGER.info("NetHub Runtime starting...")

    app_context = start_app()

    if app_context.get("start_tvbox_ui", True):
        try:
            ui_process = start_tvbox_ui()
            LOGGER.info("TV Box UI started. pid=%s", ui_process.pid)
        except Exception as exc:
            LOGGER.exception("Failed to start TV Box UI: %s", exc)

    LOGGER.info("NetHub Runtime started successfully.")


if __name__ == "__main__":
    main()