from __future__ import annotations

from pathlib import Path
from typing import Any


class SemanticPolicyStore:
    """Minimal compatibility store for core-brain phase0."""

    def __init__(self, policy_path: str | Path) -> None:
        self.policy_path = Path(policy_path)

    def load_runtime_policy(self) -> dict[str, Any]:
        return {}
