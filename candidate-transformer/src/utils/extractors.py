"""Deterministic extraction utilities using regex and heuristics.

No semantic inference. Purely extracts tokens from raw text.
"""
from __future__ import annotations

import re
from typing import List, Tuple, Dict
from datetime import datetime

import dateparser

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
URL_RE = re.compile(r"https?://[\w\-./?&=%#]+|www\.[\w\-./?&=%#]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")

SECTION_HEADERS = [
    "experience",
    "work experience",
    "professional experience",
    "education",
    "skills",
    "projects",
    "summary",
    "contact",
]


def extract_emails(text: str) -> List[str]:
    if not text:
        return []
    return list({m.group(0) for m in EMAIL_RE.finditer(text)})


def extract_links(text: str) -> List[str]:
    if not text:
        return []
    return list({m.group(0) for m in URL_RE.finditer(text)})


def extract_phones(text: str) -> List[str]:
    if not text:
        return []
    return list({m.group(0) for m in PHONE_RE.finditer(text)})


def extract_dates(text: str) -> List[datetime]:
    if not text:
        return []
    found = []
    # naive: look for year-like tokens or month-year
    tokens = re.findall(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})(?:[\w\s\.-]{0,15}\d{4})?\b", text, flags=re.I)
    for t in tokens:
        dt = dateparser.parse(t)
        if dt:
            found.append(dt)
    return found


def extract_name(text: str) -> str | None:
    if not text:
        return None
    # Heuristic: first non-empty line that contains at least two words and no email/phone
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if EMAIL_RE.search(s) or PHONE_RE.search(s):
            continue
        parts = s.split()
        if 1 < len(parts) <= 6:
            # likely a name
            return s
    return None


def extract_sections(text: str) -> Dict[str, str]:
    if not text:
        return {}
    lower = text.lower()
    sections: Dict[str, str] = {}
    for header in SECTION_HEADERS:
        idx = lower.find(header)
        if idx != -1:
            # capture a window of text following header
            start = idx
            end = min(len(text), start + 2000)
            sections[header] = text[start:end]
    return sections
