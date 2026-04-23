from __future__ import annotations


class BlueprintKBService:
    def retrieve(self, blueprint_hint: str) -> list[str]:
        if not blueprint_hint:
            return []
        return [f"blueprint:{blueprint_hint}:candidate"]
