from __future__ import annotations

import logging
import os
import subprocess
import sys

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
    """
    cmd = [sys.executable, "-m", "nethub_runtime.ui.tvbox.main"]
    LOGGER.info("Starting TV Box UI: %s", " ".join(cmd))

    return subprocess.Popen(
        cmd,
        stdout=None,
        stderr=None,
        text=True,
        env=os.environ.copy(),
        close_fds=True,
    )


def start_api_server() -> subprocess.Popen[str] | None:
    """
    Placeholder for starting local public API server if needed.
    """
    return None


def main() -> None:
    """
    System entry point.

    Responsibilities:
    - initialize logging
    - bootstrap application runtime
    - optionally launch TV Box UI
    - optionally launch local API server
    """
    setup_logging()
    LOGGER.info("NetHub Runtime starting...")

    try:
        app_context = start_app()
        LOGGER.info("Application bootstrap completed.")
    except Exception as exc:
        LOGGER.exception("Application bootstrap failed: %s", exc)
        raise

    if app_context.get("start_tvbox_ui", True):
        try:
            ui_process = start_tvbox_ui()
            LOGGER.info("TV Box UI started successfully. pid=%s", ui_process.pid)
        except Exception as exc:
            LOGGER.exception("Failed to start TV Box UI: %s", exc)

    if app_context.get("start_local_api", False):
        try:
            api_process = start_api_server()
            if api_process is not None:
                LOGGER.info("Local API server started successfully. pid=%s", api_process.pid)
        except Exception as exc:
            LOGGER.exception("Failed to start local API server: %s", exc)

    LOGGER.info("NetHub Runtime started successfully.")


if __name__ == "__main__":
    main()