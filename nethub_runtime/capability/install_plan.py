from __future__ import annotations

from nethub_runtime.core.models import InstallPlan, InstallRequirement
from nethub_runtime.core.enums import ExecutionStatus


def build_missing_plan(requirements: list[InstallRequirement]) -> InstallPlan:
    if not requirements:
        return InstallPlan(status=ExecutionStatus.READY, missing=[], reasons=["All dependencies are available."])
    return InstallPlan(
        status=ExecutionStatus.MISSING_DEPENDENCIES,
        missing=requirements,
        reasons=[f"{len(requirements)} dependency item(s) missing."],
    )
