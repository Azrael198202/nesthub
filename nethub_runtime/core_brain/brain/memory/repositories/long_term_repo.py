from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LongTermRepo:
    _facts: list[str] = field(default_factory=list)

    def add(self, text: str) -> None:
        if text:
            self._facts.append(text)
            self._facts = self._facts[-200:]

    def search(self, query: str, top_k: int = 3) -> list[str]:
        q = query.lower().strip()
        if not q:
            return self._facts[-top_k:]
        hits = [item for item in self._facts if q in item.lower()]
        return hits[:top_k]
