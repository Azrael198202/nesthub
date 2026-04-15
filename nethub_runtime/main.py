
from __future__ import annotations
import importlib.util

def start_line_demo():
    """
    启动 line_demo.py 的 poll_and_reply 协程（以守护线程方式）。
    """
    import threading
    import asyncio
    import sys
    import os
    # 动态导入 line_demo.py
    demo_path = os.path.join(os.path.dirname(__file__), "integrations/im/line_demo.py")
    spec = importlib.util.spec_from_file_location("line_demo", demo_path)
    line_demo = importlib.util.module_from_spec(spec)
    sys.modules["line_demo"] = line_demo
    spec.loader.exec_module(line_demo)
    # 启动 poll_and_reply 协程
    def _run():
        asyncio.run(line_demo.poll_and_reply())
    t = threading.Thread(target=_run, name="LineDemoThread", daemon=True)
    t.start()
    return t

import logging
import os
import subprocess
import sys
import threading
import time
from typing import TextIO

from nethub_runtime.app.main import start_app
from nethub_runtime.config.settings import ensure_app_dirs

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
    # Run the child Python interpreter in unbuffered mode so prints/logs from
    # the child process are emitted immediately and visible in the parent
    # process' output (important when running under IDE debuggers).
    cmd = [sys.executable, "-u", "-m", "nethub_runtime.ui.tvbox.main"]
    LOGGER.info("Starting TV Box UI: %s", " ".join(cmd))
    env = os.environ.copy()
    # Ensure unbuffered at environment level as well (redundant but helpful).
    env.setdefault("PYTHONUNBUFFERED", "1")

    # Capture stdout/stderr so we can stream child output into the parent logger.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        close_fds=True,
    )

    # Prepare log file under app logs directory
    try:
        paths = ensure_app_dirs()
        logs_path = paths.get("logs")
        if logs_path is None:
            logs_file = None
        else:
            logs_file = logs_path / "tvbox.log"
    except Exception:
        logs_file = None

    def _stream_output_and_persist(stream: TextIO, logger: logging.Logger) -> None:
        f = None

        def _rotate_log_if_needed(path):
            try:
                max_bytes = int(os.getenv("NETHUB_TVBOX_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
            except Exception:
                max_bytes = 5 * 1024 * 1024
            try:
                backup_count = int(os.getenv("NETHUB_TVBOX_LOG_BACKUP_COUNT", "5"))
            except Exception:
                backup_count = 5

            try:
                if not path.exists():
                    return
                if path.stat().st_size <= max_bytes:
                    return
                # rotate: remove oldest
                for i in range(backup_count - 1, 0, -1):
                    s = path.with_suffix(path.suffix + f".{i}")
                    d = path.with_suffix(path.suffix + f".{i+1}")
                    if s.exists():
                        if d.exists():
                            d.unlink()
                        s.rename(d)
                # move current to .1
                first = path.with_suffix(path.suffix + ".1")
                if first.exists():
                    first.unlink()
                path.rename(first)
            except Exception:
                logger.exception("Failed during log rotation")

        try:
            if logs_file is not None:
                # open in append mode
                f = open(logs_file, "a", encoding="utf-8")
            for line in iter(stream.readline, ""):
                if not line:
                    break
                text = line.rstrip()
                logger.info("[tvbox] %s", text)
                if f is not None:
                    try:
                        f.write(line)
                        f.flush()
                        # rotate if needed after writing (close and reopen around rotation)
                        try:
                            max_bytes = int(os.getenv("NETHUB_TVBOX_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
                        except Exception:
                            max_bytes = 5 * 1024 * 1024
                        try:
                            if logs_file.exists() and logs_file.stat().st_size > max_bytes:
                                try:
                                    f.close()
                                except Exception:
                                    pass
                                _rotate_log_if_needed(logs_file)
                                # reopen
                                f = open(logs_file, "a", encoding="utf-8")
                        except Exception:
                            logger.exception("Failed to rotate tvbox log after write")
                    except Exception:
                        logger.exception("Failed to write to tvbox log file")
        except Exception as exc:  # pragma: no cover - robust logging
            logger.exception("Error reading tvbox output: %s", exc)
        finally:
            if f is not None:
                try:
                    f.close()
                except Exception:
                    pass

    # Start a daemon thread to forward child output to the parent logger and persist it.
    if proc.stdout is not None:
        t = threading.Thread(target=_stream_output_and_persist, args=(proc.stdout, LOGGER), daemon=True)
        t.start()

    return proc


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

    # 启动 line_demo 线程
    try:
        start_line_demo()
        LOGGER.info("line_demo.py started in background thread.")
    except Exception as exc:
        LOGGER.exception("Failed to start line_demo.py: %s", exc)

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

    # Keep the parent process resident so child UI/API processes remain available
    # for debugging and runtime interactions. We poll child processes and wait
    # until interrupted (Ctrl+C) or they exit.
    ui_proc = None
    api_proc = None
    try:
        if app_context.get("start_tvbox_ui", True):
            ui_proc = ui_process  # type: ignore[name-defined]
        if app_context.get("start_local_api", False):
            api_proc = api_process  # type: ignore[name-defined]

        LOGGER.info("Entering main wait loop (press Ctrl+C to exit)")
        while True:
            # Check UI/process status
            if ui_proc is not None:
                try:
                    rc = ui_proc.poll()
                    if rc is not None:
                        LOGGER.warning("TV Box UI process exited with code=%s", rc)
                        ui_proc = None
                except Exception:
                    ui_proc = None

            if api_proc is not None:
                try:
                    rc = api_proc.poll()
                    if rc is not None:
                        LOGGER.warning("Local API process exited with code=%s", rc)
                        api_proc = None
                except Exception:
                    api_proc = None

            time.sleep(1)
    except KeyboardInterrupt:
        LOGGER.info("Shutdown requested (KeyboardInterrupt). Terminating child processes...")
        try:
            if ui_proc is not None and ui_proc.poll() is None:
                ui_proc.terminate()
                ui_proc.wait(timeout=5)
        except Exception:
            LOGGER.exception("Error terminating TV Box UI process")
        try:
            if api_proc is not None and api_proc.poll() is None:
                api_proc.terminate()
                api_proc.wait(timeout=5)
        except Exception:
            LOGGER.exception("Error terminating local API process")
    except Exception:
        LOGGER.exception("Unexpected error in main wait loop")
    finally:
        LOGGER.info("NetHub Runtime exiting.")

if __name__ == "__main__":
    main()