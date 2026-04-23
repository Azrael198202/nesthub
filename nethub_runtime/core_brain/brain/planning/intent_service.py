from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from nethub_runtime.core_brain.brain.api.dto.chat_request import ChatRequest
from nethub_runtime.core_brain.brain.chat.chat_service import ChatService


class IntentPlanningService:
    def __init__(self, chat_service: ChatService) -> None:
        self.chat_service = chat_service

    async def analyze(self, *, req: ChatRequest, context_bundle: dict[str, Any]) -> dict[str, Any]:
        parsed = await self.chat_service.analyze_intent(req, context_bundle)
        raw_name = str(parsed.get("name") or parsed.get("intent_name") or "general_chat")
        normalized_name = self._normalize_name(raw_name)
        intent_type = self._detect_intent_type(normalized_name)
        confidence = self._normalize_confidence(parsed.get("confidence"))
        expected_outcome = self._expected_outcome(intent_type, normalized_name)
        requires_clarification = intent_type == "agent_creation_intent"

        entities = parsed.get("entities")
        if not isinstance(entities, dict):
            entities = {}
        if intent_type == "agent_creation_intent" and not entities.get("agent_role"):
            entities = {**entities, "agent_role": "custom_agent"}

        constraints = parsed.get("constraints")
        if not isinstance(constraints, dict):
            constraints = {}

        clarification_questions = parsed.get("clarification_questions")
        if not isinstance(clarification_questions, list):
            clarification_questions = []
        if requires_clarification and not clarification_questions:
            clarification_questions = [
                "What agent role should be created?",
                "What tools must this agent use?",
            ]

        return {
            "intent_id": f"intent_{uuid4().hex[:12]}",
            "intent_type": intent_type,
            "name": normalized_name,
            "description": str(parsed.get("description") or f"Detected user goal: {normalized_name}."),
            "confidence": confidence,
            "entities": entities,
            "constraints": constraints,
            "expected_outcome": expected_outcome,
            "requires_clarification": requires_clarification,
            "clarification_questions": clarification_questions,
            "source_text": req.message,
            "context_refs": {
                "session_id": req.session_id,
                "task_session_id": req.task_id or f"task_{req.session_id}",
                "memory_refs": [],
            },
            "metadata": {
                "mode": req.mode,
                "context_policy": req.context_policy,
            },
        }

    def _normalize_name(self, value: str) -> str:
        name = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower())
        name = re.sub(r"_+", "_", name).strip("_")
        return name if name and name[0].isalpha() else "general_chat"

    def _detect_intent_type(self, normalized_name: str) -> str:
        if "create_agent" in normalized_name or "agent_creation" in normalized_name:
            return "agent_creation_intent"
        return "normal_intent"

    def _normalize_confidence(self, value: Any) -> float:
        try:
            score = float(value)
        except Exception:
            score = 0.6
        return min(max(score, 0.0), 1.0)

    def _expected_outcome(self, intent_type: str, normalized_name: str) -> list[str]:
        if intent_type == "agent_creation_intent":
            return ["blueprint_created", "creation_workflow_created", "agent_registered"]
        return [f"{normalized_name}_completed"]
