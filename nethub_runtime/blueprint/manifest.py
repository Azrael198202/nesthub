from __future__ import annotations

from pydantic import BaseModel, Field


class BlueprintManifest(BaseModel):
    name: str
    description: str = ""
    required_models: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_packages: list[str] = Field(default_factory=list)
    allowed_shell_commands: list[str] = Field(default_factory=list)
    install_policy: dict[str, bool] = Field(
        default_factory=lambda: {
            "auto": True,
            "fallback": True,
        }
    )
    execution: dict = Field(default_factory=dict)
