"""Deterministic id helpers."""
from __future__ import annotations

import uuid
from hashlib import sha256


def new_uuid_hex() -> str:
    return uuid.uuid4().hex


def deterministic_candidate_id(*parts: str) -> str:
    """Create a deterministic candidate id from input parts.

    This is a pure helper (no business logic) used to create stable ids
    for testing and plumbing. It returns the hex sha256 of joined parts.
    """
    joined = "::".join(p.strip().lower() for p in parts if p)
    if not joined:
        return new_uuid_hex()
    return sha256(joined.encode("utf-8")).hexdigest()
