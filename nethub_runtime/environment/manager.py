from __future__ import annotations

from nethub_runtime.capability.registry import CapabilityRegistry
from nethub_runtime.common.enums import InstallTarget
from nethub_runtime.common.models import InstallPlan, RuntimeProfile
from nethub_runtime.environment.installers.ollama_installer import OllamaInstaller
from nethub_runtime.environment.installers.pip_installer import PipInstaller
from nethub_runtime.environment.installers.tool_installer import ToolInstaller


class EnvironmentManager:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry
        self.installers = [PipInstaller(), ToolInstaller(), OllamaInstaller()]

    def apply_plan(self, plan: InstallPlan, profile: RuntimeProfile) -> list[str]:
        installed: list[str] = []
        for requirement in plan.missing:
            for installer in self.installers:
                if installer.supports(requirement):
                    name = installer.install(requirement, profile)
                    installed.append(name)
                    self._register(requirement.target.value, name)
                    break
            else:
                raise RuntimeError(f"No installer found for {requirement.target}:{requirement.name}")
        return installed

    def _register(self, target: str, name: str) -> None:
        if target == InstallTarget.PACKAGE.value:
            self.registry.register_package(name)
        elif target == InstallTarget.TOOL.value:
            self.registry.register_tool(name)
        elif target == InstallTarget.MODEL.value:
            self.registry.register_model(name)
