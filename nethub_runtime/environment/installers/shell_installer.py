from __future__ import annotations

from nethub_runtime.core.models import RuntimeProfile


class ShellBootstrapHelper:
    def recommended_package_manager(self, profile: RuntimeProfile) -> str:
        if profile.os_type.value == "linux":
            return "apt / dnf / yum (depends on distro)"
        if profile.os_type.value == "macos":
            return "brew"
        if profile.os_type.value == "windows":
            return "winget / choco / scoop"
        return "unknown"
