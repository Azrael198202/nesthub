from __future__ import annotations

from nethub_runtime.core_brain.brain.memory.repositories.session_repo import SessionRepo


class SessionMemoryService:
    def __init__(self, repo: SessionRepo) -> None:
        self.repo = repo

    def load(self, session_id: str) -> list[dict[str, str]]:
        return self.repo.read(session_id)

    def write_turn(self, session_id: str, user_message: str, assistant_message: str) -> None:
        self.repo.append(session_id, "user", user_message)
        self.repo.append(session_id, "assistant", assistant_message)
