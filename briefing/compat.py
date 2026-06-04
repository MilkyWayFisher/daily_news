from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any


def dataclass_compat(*args: Any, **kwargs: Any) -> Any:
    """Use dataclass slots where supported, while keeping Python 3.8 compatibility."""
    if kwargs.get("slots") and sys.version_info < (3, 10):
        kwargs = {**kwargs}
        kwargs.pop("slots", None)
    return dataclass(*args, **kwargs)
