"""Small deterministic helpers and safe-access utilities."""
from __future__ import annotations

from typing import Any


def safe_get(d: dict | None, key: str, default: Any = None) -> Any:
    if not d:
        return default
    return d.get(key, default)


def ensure_list(x: Any) -> list:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]
