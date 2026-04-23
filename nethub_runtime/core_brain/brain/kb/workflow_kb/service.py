from __future__ import annotations


class WorkflowKBService:
    def retrieve(self, workflow_name: str) -> list[str]:
        if not workflow_name:
            return []
        return [f"workflow:{workflow_name}:template"]
