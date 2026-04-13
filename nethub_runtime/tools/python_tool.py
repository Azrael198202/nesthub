from __future__ import annotations

import sys

from nethub_runtime.runtime.command_runner import CommandRunner
from nethub_runtime.tools.base import Tool


class PythonTool(Tool):
    name = "python"

    def __init__(self) -> None:
        self.runner = CommandRunner()

    def execute(self, script_path: str, *script_args: str):
        command = [sys.executable, script_path, *script_args]
        return self.runner.run(command)
