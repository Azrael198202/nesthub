from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .enums import ExecutionStatus, InstallTarget, OSType


class RuntimeProfile(BaseModel):
    os_type: OSType
    os_version: str | None = None
    architecture: str
    hostname: str
    supports_shell: bool = False
    default_shell: str | None = None
    python_executable: str | None = None
    ollama_available: bool = False
    docker_available: bool = False
    notes: list[str] = Field(default_factory=list)


class RegistryState(BaseModel):
    packages: set[str] = Field(default_factory=set)
    tools: set[str] = Field(default_factory=set)
    models: set[str] = Field(default_factory=set)


class InstallRequirement(BaseModel):
    target: InstallTarget
    name: str
    version: str | None = None
    source: str | None = None
    optional: bool = False
    install_hint: str | None = None


class InstallPlan(BaseModel):
    status: ExecutionStatus = ExecutionStatus.READY
    missing: list[InstallRequirement] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        return not self.missing


class CommandResult(BaseModel):
    return_code: int
    stdout: str = ""
    stderr: str = ""
    command: list[str] = Field(default_factory=list)


class BootstrapManifest(BaseModel):
    default_packages: list[str] = Field(default_factory=list)
    default_tools: list[str] = Field(default_factory=list)
    default_models: list[str] = Field(default_factory=list)
    allowed_shell_commands: list[str] = Field(default_factory=list)


class ExecuteResult(BaseModel):
    status: ExecutionStatus
    detail: str
    installed: list[str] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)


class BlueprintExecutionContext(BaseModel):
    blueprint_name: str
    input_payload: dict[str, Any] = Field(default_factory=dict)
    execution_mode: Literal["dry_run", "live"] = "dry_run"
