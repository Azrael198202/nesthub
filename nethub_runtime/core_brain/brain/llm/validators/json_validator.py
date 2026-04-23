from __future__ import annotations

import json
from typing import Any


def parse_json_text(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None
