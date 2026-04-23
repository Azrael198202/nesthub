from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.brain.kb.blueprint_kb.service import BlueprintKBService
from nethub_runtime.core_brain.brain.kb.intent_kb.service import IntentKBService
from nethub_runtime.core_brain.brain.kb.workflow_kb.service import WorkflowKBService


class RetrievalService:
    def __init__(
        self,
        *,
        intent_kb: IntentKBService,
        workflow_kb: WorkflowKBService,
        blueprint_kb: BlueprintKBService,
    ) -> None:
        self.intent_kb = intent_kb
        self.workflow_kb = workflow_kb
        self.blueprint_kb = blueprint_kb

    def retrieve(self, *, intent_name: str, workflow_name: str) -> dict[str, list[str]]:
        return {
            "intent_refs": self.intent_kb.retrieve(intent_name),
            "workflow_refs": self.workflow_kb.retrieve(workflow_name),
            "blueprint_refs": self.blueprint_kb.retrieve(intent_name),
        }
