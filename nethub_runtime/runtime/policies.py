from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ShellPolicy:
    allowed_commands: set[str] = field(default_factory=set)

    def is_allowed(self, command: list[str]) -> bool:
        if not command:
            return False
        return command[0] in self.allowed_commands
