"""Deterministic normalization helpers."""
from __future__ import annotations

import unicodedata
from typing import Iterable
import re
from urllib.parse import urlsplit, urlunsplit

from phonenumbers import parse as _parse, format_number, PhoneNumberFormat, NumberParseException


_WS_RE = re.compile(r"\s+")
_LINE_BREAK_HYPHEN_RE = re.compile(r"(?<=\w)[-‐‑‒–—]\s*\n\s*(?=\w)")
_NON_BREAKING_SPACE_REPLACEMENTS = {
    "\u00a0": " ",
    "\u2007": " ",
    "\u202f": " ",
}


def normalize_whitespace(text: str | None) -> str | None:
    if text is None:
        return None
    t = text.strip()
    return _WS_RE.sub(" ", t)


def normalize_extracted_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = unicodedata.normalize("NFKC", text)
    for source, target in _NON_BREAKING_SPACE_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _LINE_BREAK_HYPHEN_RE.sub("", normalized)
    normalized = re.sub(r"[•·●▪◦]", "\n", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized


def normalize_merged_words(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", normalized)
    normalized = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", normalized)
    normalized = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", normalized)
    normalized = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", normalized)
    return normalize_whitespace(normalized)


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


def normalize_url(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if not text.startswith(("http://", "https://")):
        text = f"https://{text.lstrip('/')}"
    split = urlsplit(text)
    netloc = split.netloc.lower().removeprefix("www.")
    path = split.path.rstrip("/")
    normalized = urlunsplit((split.scheme.lower(), netloc, path, split.query, split.fragment))
    return normalized.lower()
