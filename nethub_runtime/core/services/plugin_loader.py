from __future__ import annotations

import importlib
from typing import Any


def load_plugin(path: str) -> Any:
    """
    Load plugin from dotted path:
    - package.module:ClassName
    - package.module.factory_function
    """
    if ":" in path:
        module_name, attr_name = path.split(":", 1)
    else:
        module_name, attr_name = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    target = getattr(module, attr_name)
    return target() if callable(target) else target
