from __future__ import annotations

from nethub_runtime.blueprint.manifest import BlueprintManifest
from nethub_runtime.capability.install_plan import build_missing_plan
from nethub_runtime.capability.registry import CapabilityRegistry
from nethub_runtime.core.enums import InstallTarget
from nethub_runtime.core.models import InstallRequirement, RuntimeProfile


class CapabilityResolver:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def resolve(self, blueprint: BlueprintManifest, profile: RuntimeProfile):
        state = self.registry.load()
        missing: list[InstallRequirement] = []

        if blueprint.allowed_shell_commands and not profile.supports_shell:
            missing.append(
                InstallRequirement(
                    target=InstallTarget.TOOL,
                    name="shell",
                    install_hint="Target node does not support shell execution.",
                )
            )

        for pkg in blueprint.required_packages:
            if pkg.lower() not in state.packages:
                missing.append(InstallRequirement(target=InstallTarget.PACKAGE, name=pkg))

        for tool in blueprint.required_tools:
            if tool.lower() not in state.tools:
                missing.append(InstallRequirement(target=InstallTarget.TOOL, name=tool))

        for model in blueprint.required_models:
            if model.lower() not in state.models:
                missing.append(InstallRequirement(target=InstallTarget.MODEL, name=model))

        return build_missing_plan(missing)
