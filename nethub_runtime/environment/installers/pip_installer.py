from __future__ import annotations

import sys

from nethub_runtime.core.enums import InstallTarget
from nethub_runtime.core.models import InstallRequirement, RuntimeProfile
from nethub_runtime.environment.installers.base import BaseInstaller
from nethub_runtime.runtime.command_runner import CommandRunner


class PipInstaller(BaseInstaller):
    def __init__(self) -> None:
        self.runner = CommandRunner()

    def supports(self, requirement: InstallRequirement) -> bool:
        return requirement.target == InstallTarget.PACKAGE

    def install(self, requirement: InstallRequirement, profile: RuntimeProfile) -> str:
        command = [profile.python_executable or sys.executable, "-m", "pip", "install", requirement.name]
        result = self.runner.run(command)
        if result.return_code != 0:
            raise RuntimeError(f"Failed to install package {requirement.name}: {result.stderr}")
        return requirement.name
