from __future__ import annotations


class WebAdapter:
    """Placeholder adapter for future web querying integration."""

    def fetch(self, _query: str) -> dict:
        return {"enabled": False, "message": "Web adapter is not enabled in local core runtime."}
