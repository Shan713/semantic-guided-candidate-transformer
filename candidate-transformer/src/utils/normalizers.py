"""Deterministic normalization helpers."""
from __future__ import annotations

from typing import Iterable
import re

from phonenumbers import parse as _parse, format_number, PhoneNumberFormat, NumberParseException


_WS_RE = re.compile(r"\s+")


def normalize_whitespace(text: str | None) -> str | None:
    if text is None:
        return None
    t = text.strip()
    return _WS_RE.sub(" ", t)


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    e = email.strip().lower()
    return e


def dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for it in items:
        if it is None:
            continue
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


def normalize_phone(raw: str, default_region: str | None = None) -> str | None:
    if not raw:
        return None
    try:
        pn = _parse(raw, default_region)
        return format_number(pn, PhoneNumberFormat.E164)
    except NumberParseException:
        # Best-effort: strip non-digits
        digits = re.sub(r"[^0-9]+", "", raw)
        if not digits:
            return None
        return digits
