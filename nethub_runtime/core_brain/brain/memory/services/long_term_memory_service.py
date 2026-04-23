from __future__ import annotations

from nethub_runtime.core_brain.brain.memory.repositories.long_term_repo import LongTermRepo


class LongTermMemoryService:
    def __init__(self, repo: LongTermRepo) -> None:
        self.repo = repo

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        return self.repo.search(query, top_k=top_k)

    def write_fact(self, text: str) -> None:
        self.repo.add(text)
