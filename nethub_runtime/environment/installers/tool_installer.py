from __future__ import annotations

from nethub_runtime.common.enums import InstallTarget
from nethub_runtime.common.models import InstallRequirement, RuntimeProfile
from nethub_runtime.environment.installers.base import BaseInstaller


class ToolInstaller(BaseInstaller):
    def supports(self, requirement: InstallRequirement) -> bool:
        return requirement.target == InstallTarget.TOOL

    def install(self, requirement: InstallRequirement, profile: RuntimeProfile) -> str:
        # Placeholder:
        # Linux  -> apt/yum/dnf or local binary
        # macOS  -> brew or local binary
        # Windows-> winget/choco/scoop
        return requirement.name
