from __future__ import annotations

from nethub_runtime.core.enums import InstallTarget
from nethub_runtime.core.models import InstallRequirement, RuntimeProfile
from nethub_runtime.environment.installers.base import BaseInstaller
from nethub_runtime.runtime.command_runner import CommandRunner


class OllamaInstaller(BaseInstaller):
    def __init__(self) -> None:
        self.runner = CommandRunner()

    def supports(self, requirement: InstallRequirement) -> bool:
        return requirement.target == InstallTarget.MODEL

    def install(self, requirement: InstallRequirement, profile: RuntimeProfile) -> str:
        if not profile.ollama_available:
            raise RuntimeError("Ollama is not available on this node.")
        result = self.runner.run(["ollama", "pull", requirement.name], timeout=1800)
        if result.return_code != 0:
            raise RuntimeError(f"Failed to pull model {requirement.name}: {result.stderr}")
        return requirement.name
