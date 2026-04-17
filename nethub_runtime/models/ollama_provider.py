from __future__ import annotations

from nethub_runtime.models.provider import ModelProvider
from nethub_runtime.runtime.command_runner import CommandRunner


class OllamaProvider(ModelProvider):
    def __init__(self) -> None:
        self.runner = CommandRunner()

    def list_models(self) -> list[str]:
        result = self.runner.run(["ollama", "list"])
        models: list[str] = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if parts:
                models.append(parts[0].strip())
        return models

    def is_available(self, model_name: str) -> bool:
        return model_name.lower() in {item.lower() for item in self.list_models()}

    def ensure(self, model_name: str) -> None:
        result = self.runner.run(["ollama", "pull", model_name], timeout=1800)
        if result.return_code != 0:
            raise RuntimeError(result.stderr)
