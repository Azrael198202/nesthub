from __future__ import annotations

import subprocess

from nethub_runtime.core.models import CommandResult


class CommandRunner:
    def run(self, command: list[str], timeout: int = 120) -> CommandResult:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            return_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            command=command,
        )
