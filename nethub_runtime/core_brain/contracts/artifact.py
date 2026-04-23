from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


SemVer = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]


class ArtifactManifestContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    source_intent: str = Field(min_length=1)
    source_task: str = Field(min_length=1)
    version: SemVer
    status: str = Field(min_length=1)
    runnable: bool
    registered_at: str = Field(min_length=1)
