from __future__ import annotations

from nethub_runtime.common.models import RuntimeProfile


def enrich_runtime_notes(profile: RuntimeProfile) -> RuntimeProfile:
    if profile.os_type.value == "linux":
        profile.notes.append("Recommended target for TV Box runtime.")
    elif profile.os_type.value == "windows":
        profile.notes.append("Use winget/choco/powershell for tool bootstrap.")
    elif profile.os_type.value == "macos":
        profile.notes.append("Current development environment detected.")
    return profile
