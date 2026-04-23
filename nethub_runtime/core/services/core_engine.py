from __future__ import annotations

from nethub_runtime.core_brain.engine import CoreBrainEngine


class AICore(CoreBrainEngine):
    """Backward-compatible alias.

    Legacy modules may still import ``AICore``. The runtime implementation is now
    fully delegated to ``CoreBrainEngine``.
    """

    pass
