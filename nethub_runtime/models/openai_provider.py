from __future__ import annotations

from nethub_runtime.models.provider import ModelProvider
import os
import requests

class OpenAIProvider(ModelProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_url = "https://api.openai.com/v1/chat/completions"

    def is_available(self, model_name: str) -> bool:
        return self.api_key is not None

    def ensure(self, model_name: str) -> None:
        if not self.api_key:
            raise RuntimeError("OpenAI API key not set")
        # Always available if API key is set

    def chat(self, messages: list[dict], model: str = "gpt-4o", **kwargs):
        if not self.api_key:
            raise RuntimeError("OpenAI API key not set")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": messages,
            **kwargs
        }
        resp = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
