from __future__ import annotations

from pathlib import Path


class RuntimeLearningStore:
    """No-op runtime learning store kept for compatibility imports."""

    def __init__(self, policy_path: str | Path) -> None:
        self.policy_path = Path(policy_path)

    def record_attempt(self, **kwargs) -> None:
        _ = kwargs
