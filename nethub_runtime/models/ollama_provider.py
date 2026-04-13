from __future__ import annotations

from nethub_runtime.models.provider import ModelProvider
from nethub_runtime.runtime.command_runner import CommandRunner


class OllamaProvider(ModelProvider):
    def __init__(self) -> None:
        self.runner = CommandRunner()

    def is_available(self, model_name: str) -> bool:
        result = self.runner.run(["ollama", "list"])
        return model_name.lower() in result.stdout.lower()

    def ensure(self, model_name: str) -> None:
        result = self.runner.run(["ollama", "pull", model_name], timeout=1800)
        if result.return_code != 0:
            raise RuntimeError(result.stderr)
