from __future__ import annotations

from uuid import uuid4


def generate_id(prefix: str) -> str:
    """Generate a short prefixed ID for core runtime objects."""
    safe_prefix = prefix.strip().lower().replace(" ", "_") or "id"
    return f"{safe_prefix}_{uuid4().hex[:12]}"
