"""Hashing helpers."""
from __future__ import annotations

import hashlib


def sha256_text(text: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    return h.hexdigest()
