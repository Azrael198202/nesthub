from __future__ import annotations

import json
from typing import Any

from nethub_runtime.core_brain.brain.api.dto.chat_request import ChatRequest
from nethub_runtime.core_brain.brain.llm.litellm_client import LiteLLMClient
from nethub_runtime.core_brain.brain.llm.model_registry import ModelRegistry
from nethub_runtime.core_brain.brain.llm.prompt_registry import PromptRegistry
from nethub_runtime.core_brain.brain.llm.validators.json_validator import parse_json_text


class ChatService:
    def __init__(
        self,
        *,
        llm_client: LiteLLMClient,
        model_registry: ModelRegistry,
        prompt_registry: PromptRegistry,
    ) -> None:
        self.llm_client = llm_client
        self.model_registry = model_registry
        self.prompt_registry = prompt_registry

    async def analyze_intent(self, req: ChatRequest, context_bundle: dict[str, Any]) -> dict[str, Any]:
        system_prompt = self.prompt_registry.get("intent_system") or "Extract intent in JSON."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.message},
        ]
        response_text = await self.llm_client.call(self.model_registry.intent_model(), messages)
        parsed = parse_json_text(response_text)
        if parsed is None:
            return {"intent_name": "general_chat", "confidence": 0.6}
        raw_name = str(parsed.get("name") or parsed.get("intent_name") or "general_chat")
        confidence = float(parsed.get("confidence") or 0.6)
        entities = parsed.get("entities") if isinstance(parsed.get("entities"), dict) else {}
        constraints = parsed.get("constraints") if isinstance(parsed.get("constraints"), dict) else {}
        clarification_questions = parsed.get("clarification_questions")
        if not isinstance(clarification_questions, list):
            clarification_questions = []
        return {
            "name": raw_name,
            "intent_name": raw_name,
            "description": str(parsed.get("description") or ""),
            "confidence": confidence,
            "entities": entities,
            "constraints": constraints,
            "clarification_questions": [str(item) for item in clarification_questions if isinstance(item, str)],
        }

    async def generate_answer(
        self,
        *,
        req: ChatRequest,
        context_bundle: dict[str, Any],
        route: dict[str, Any],
    ) -> str:
        context_preview = json.dumps(
            {
                "session_context": context_bundle.get("session_context", [])[-6:],
                "long_term_context": context_bundle.get("long_term_context", []),
            },
            ensure_ascii=False,
        )
        messages = [
            {"role": "system", "content": "You are NestHub core-brain assistant. Be concise and practical."},
            {"role": "system", "content": f"Context: {context_preview}"},
            {"role": "user", "content": req.message},
        ]
        model = self.model_registry.get(str(route.get("model") or "")) or self.model_registry.chat_model()
        text = await self.llm_client.call(model, messages)
        return text.strip() or "已处理你的请求。"
