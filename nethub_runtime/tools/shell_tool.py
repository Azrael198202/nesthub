from __future__ import annotations

from nethub_runtime.runtime.command_runner import CommandRunner
from nethub_runtime.runtime.policies import ShellPolicy
from nethub_runtime.tools.base import Tool


class ShellTool(Tool):
    name = "shell"

    def __init__(self, policy: ShellPolicy) -> None:
        self.policy = policy
        self.runner = CommandRunner()

    def execute(self, command: list[str], timeout: int = 120):
        if not self.policy.is_allowed(command):
            raise PermissionError(f"Command not allowed: {command}")
        return self.runner.run(command, timeout=timeout)
