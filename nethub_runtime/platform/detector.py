from __future__ import annotations

import platform
import shutil
import socket
import sys

from nethub_runtime.common.enums import OSType
from nethub_runtime.common.models import RuntimeProfile
from nethub_runtime.platform.os_profile import enrich_runtime_notes


def _detect_os() -> OSType:
    raw = platform.system().lower()
    if raw == "linux":
        return OSType.LINUX
    if raw == "windows":
        return OSType.WINDOWS
    if raw == "darwin":
        return OSType.MACOS
    return OSType.UNKNOWN


def detect_runtime_profile() -> RuntimeProfile:
    shell = None
    if _detect_os() == OSType.WINDOWS:
        shell = shutil.which("powershell") or shutil.which("pwsh") or shutil.which("cmd")
    else:
        shell = shutil.which("bash") or shutil.which("zsh") or shutil.which("sh")

    profile = RuntimeProfile(
        os_type=_detect_os(),
        os_version=platform.version(),
        architecture=platform.machine(),
        hostname=socket.gethostname(),
        supports_shell=shell is not None,
        default_shell=shell,
        python_executable=sys.executable if sys.executable else None,
        ollama_available=shutil.which("ollama") is not None,
        docker_available=shutil.which("docker") is not None,
    )
    return enrich_runtime_notes(profile)
