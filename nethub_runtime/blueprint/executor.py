from __future__ import annotations

from nethub_runtime.blueprint.manifest import BlueprintManifest
from nethub_runtime.capability.registry import CapabilityRegistry
from nethub_runtime.capability.resolver import CapabilityResolver
from nethub_runtime.core.enums import ExecutionStatus
from nethub_runtime.core.models import BlueprintExecutionContext, ExecuteResult, RuntimeProfile
from nethub_runtime.environment.manager import EnvironmentManager


class BlueprintExecutor:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry
        self.resolver = CapabilityResolver(registry)
        self.env_manager = EnvironmentManager(registry)

    def execute(
        self,
        blueprint: BlueprintManifest,
        profile: RuntimeProfile,
        context: BlueprintExecutionContext,
    ) -> ExecuteResult:
        plan = self.resolver.resolve(blueprint, profile)

        installed: list[str] = []
        if not plan.is_ready:
            if not blueprint.install_policy.get("auto", False):
                return ExecuteResult(
                    status=ExecutionStatus.MISSING_DEPENDENCIES,
                    detail="Missing dependencies and auto install disabled.",
                )
            installed = self.env_manager.apply_plan(plan, profile)

        # Placeholder execution stage:
        # In the real system, this is where the Feature/Tool/Service call happens.
        return ExecuteResult(
            status=ExecutionStatus.COMPLETED,
            detail=f"Blueprint '{blueprint.name}' is ready for execution.",
            installed=installed,
            output={
                "blueprint": blueprint.name,
                "input": context.input_payload,
                "mode": context.execution_mode,
            },
        )
