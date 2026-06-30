"""Deterministic normalization helpers.

Generic, reusable normalization primitives. No resume-specific logic.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

from phonenumbers import format_number, parse as _parse, PhoneNumberFormat, NumberParseException


_WS_RE = re.compile(r"\s+")
_HSPACE_RE = re.compile(r"[^\S\n]+")  # horizontal whitespace only (preserves newlines)
_LINE_BREAK_HYPHEN_RE = re.compile(r"(?<=\w)[-‐‑‒–—]\s*\n\s*(?=\w)")
_NON_BREAKING_SPACE_REPLACEMENTS = {
    " ": " ",
    " ": " ",
    " ": " ",
}

# ---------------------------------------------------------------------------
# Generic OCR token repair patterns — operate on any text, never target a
# specific resume.
# ---------------------------------------------------------------------------

# Broken uppercase acronym tokens:  "REST AP Is" -> "REST APIs"
_BROKEN_ACRONYM_RE = re.compile(
    r"\b([A-Z]{2,})\s+([A-Z][a-z]{1,2})\b(?=\s|$)",
)

# Isolated uppercase fragments after common acronyms
# e.g. "Io T" -> "IoT", "A P I" -> "API"
_FRAGMENTED_ACRONYM_RE = re.compile(
    r"\b([A-Z][a-z]?)\s+([A-Z](?:\s+[A-Z])?)\b",
)

# OCR spacing within compound words: "Postgre SQL" -> "PostgreSQL"
_OCR_SPACING_RE = re.compile(
    r"\b(Postgre|My|Micro|Type|Java|ECMA|Action)\s+(SQL|Script|Soft|Word|Office|Excel|Point|Server|Force|Sheet)\b",
    re.IGNORECASE,
)

# Hyphenated line-break artifacts in mid-paragraph text:
# "DistributedSystemsFundamen-\ntals" -> repaired by _LINE_BREAK_HYPHEN_RE
# But also handle when the broken parts appear on the same line:
# "DistributedSystemsFundamen- tals" (space after hyphen from PDF extraction)
_HYPHEN_SPACE_RE = re.compile(r"(?<=\w)-\s+(?=[a-z])")

# Merged camelCase / PascalCase words split
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_UPPER_CAMEL_SPLIT_RE = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")

# Known common OCR misreads (general, not resume-specific)
_OCR_CHAR_REPLACEMENTS = {
    "‘": "'",   # left single quote
    "’": "'",   # right single quote
    "“": '"',   # left double quote
    "”": '"',   # right double quote
    "–": "-",   # en dash
    "—": "-",   # em dash
    "…": "...",  # ellipsis
    "·": "-",   # middle dot
    "­": "",    # soft hyphen
}

# ---------------------------------------------------------------------------
# Company name normalization patterns — generic, not resume-specific.
# ---------------------------------------------------------------------------

# Punctuation variants of the same token: "Galaxy-Z" -> "Galaxy Z"
_COMPANY_PUNCTUATION_RE = re.compile(r"([A-Za-z0-9])[‐‑‒–—-]([A-Za-z0-9])")

# Whitespace variants merge: "Galaxy  Z" -> "Galaxy Z"
_MULTISPACE_RE = re.compile(r"\s{2,}")


def normalize_whitespace(text: str | None) -> str | None:
    """Collapse all whitespace sequences to a single space and strip."""
    if text is None:
        return None
    t = text.strip()
    return _WS_RE.sub(" ", t)


def normalize_extracted_text(text: str | None) -> str | None:
    """Normalize raw extracted text: Unicode NFKC, line endings, bullets, etc."""
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
    """Split camelCase/PascalCase and digit-letter boundaries generically."""
    if text is None:
        return None
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", normalized)
    normalized = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", normalized)
    normalized = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", normalized)
    normalized = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", normalized)
    return normalize_whitespace(normalized)


# Pattern: OCR-spaced ordinals like "12 th" -> "12th", "3 rd" -> "3rd"
_OCR_ORDINAL_RE = re.compile(r"\b(\d{1,4})\s+(th|st|nd|rd)\b", re.IGNORECASE)


def repair_ocr_tokens(text: str | None) -> str | None:
    """Generic deterministic OCR token repair.

    Repairs common PDF/OCR extraction artifacts without any resume-specific
    knowledge.  Safe to call on any text.

    Repairs performed:
      - Unicode smart quotes, dashes, soft hyphens
      - Broken uppercase acronyms (``REST AP Is`` → ``REST APIs``)
      - Fragmented acronyms (``Io T`` → ``IoT``)
      - OCR spacing between known compound terms
      - Hyphen-space artifacts from line wrapping
    """
    if text is None:
        return None
    result = unicodedata.normalize("NFKC", text)
    for char, replacement in _OCR_CHAR_REPLACEMENTS.items():
        result = result.replace(char, replacement)

    # Repair hyphen-space artifacts (line-wrap remnants on same line)
    result = _HYPHEN_SPACE_RE.sub("", result)

    # Repair known OCR-spaced compound words
    result = _OCR_SPACING_RE.sub(_repair_ocr_spacing, result)

    # Repair broken uppercase acronyms: "REST AP Is" -> "REST APIs"
    result = _BROKEN_ACRONYM_RE.sub(_repair_broken_acronym, result)

    # Repair fragmented short acronyms: "Io T" -> "IoT"
    result = _FRAGMENTED_ACRONYM_RE.sub(_repair_fragmented_acronym, result)

    # Repair OCR-spaced ordinals: "12 th" -> "12th", "3 rd" -> "3rd"
    result = _OCR_ORDINAL_RE.sub(r"\1\2", result)

    # Collapse horizontal whitespace only — preserve line breaks for parsers
    # that rely on newline-separated sections.
    result = _HSPACE_RE.sub(" ", result)
    result = result.strip()
    return result or None


def _repair_ocr_spacing(m: re.Match) -> str:
    """Rejoin OCR-spaced compound words: Postgre SQL → PostgreSQL."""
    return m.group(1) + m.group(2)


def _repair_broken_acronym(m: re.Match) -> str:
    """Repair 'REST AP Is' → 'REST APIs' by merging trailing fragment."""
    acronym = m.group(1)
    fragment = m.group(2)
    # Merge: "AP" + "Is" -> "APIs" (capitalize fragment to match acronym style)
    repaired = acronym + " " + fragment.capitalize()
    return repaired


def _repair_fragmented_acronym(m: re.Match) -> str:
    """Repair 'Io T' → 'IoT' when both parts look like acronym fragments."""
    first = m.group(1)
    second = m.group(2).replace(" ", "")
    combined = first + second
    # Only join if combined looks like a plausible acronym (2-5 uppercase-ish chars)
    if 2 <= len(combined) <= 6 and combined.isalpha():
        return combined
    return m.group(0)


def normalize_company_name(name: str | None) -> str | None:
    """Deterministically normalize a company name for comparison.

    Operations (all generic):
      1. Unicode NFKC normalization
      2. Split PascalCase/camelCase word boundaries (GalaxyZ → Galaxy Z)
      3. Replace en/em dashes and hyphens between words with a single space
      4. Collapse multiple spaces
      5. Strip leading/trailing whitespace

    This is called BEFORE ontology lookup so that variant spellings of the
    same company converge to the same normalized form.
    """
    if name is None:
        return None
    result = unicodedata.normalize("NFKC", name)
    result = result.strip()
    # Split PascalCase/camelCase word boundaries generically
    # "GalaxyZ" → "Galaxy Z", "McKinseyAndCo" → "McKinsey And Co"
    result = _CAMEL_SPLIT_RE.sub(" ", result)
    result = _UPPER_CAMEL_SPLIT_RE.sub(" ", result)
    # Replace any dash-like character between alphanumeric chars with space
    result = _COMPANY_PUNCTUATION_RE.sub(r"\1 \2", result)
    # Collapse whitespace
    result = _MULTISPACE_RE.sub(" ", result)
    result = result.strip()
    if not result:
        return None
    return result


def normalize_company_key(name: str | None) -> str | None:
    """Return a case-folded, punctuation-normalized key for company matching."""
    normalized = normalize_company_name(name)
    if normalized is None:
        return None
    return normalized.lower()


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


# ---------------------------------------------------------------------------
# Generic skill token quality filters — no hardcoded skill names.
# ---------------------------------------------------------------------------

# Tokens that are almost never valid standalone skills
# These are generic English words, not resume-specific
_GENERIC_STOP_WORDS = frozenset({
    "design", "organization", "practices", "management", "development",
    "implementation", "integration", "engineering", "testing", "deployment",
    "maintenance", "support", "operations", "administration", "configuration",
    "analysis", "planning", "execution", "monitoring", "reporting",
    "documentation", "research", "evaluation", "assessment", "optimization",
    "architecture", "strategy", "consulting", "training", "coordination",
    "processing", "validation", "verification", "compliance",
    "backend system", "backend systems", "backend development",
    "frontend development", "web development", "software development",
    "system design", "systems design",
})

# Minimum length for a standalone skill token (shorter tokens are usually
# acronyms which are fine, but single characters are not)
_MIN_SKILL_TOKEN_LENGTH = 2

# Pattern: tokens that look like standalone abstract concepts
# (lowercase single word with no technical indicator)
_ABSTRACT_CONCEPT_RE = re.compile(r"^[a-z]{3,15}$")


def filter_skill_tokens(tokens: list[str]) -> list[str]:
    """Remove tokens that are unlikely to be meaningful standalone skills.

    Filters applied (all generic):
      - Tokens shorter than minimum length
      - Common English stop-words that rarely represent skills alone
      - Single lowercase words that look like abstract concepts rather than
        technical skills (technical skills typically contain uppercase, digits,
        dots, plus signs, hashes, or are acronyms)

    Does NOT hardcode any skill names.  Only removes tokens that a generic
    heuristic identifies as noise.
    """
    if not tokens:
        return []
    filtered: list[str] = []
    for token in tokens:
        text = normalize_whitespace(token)
        if not text:
            continue
        # Too short
        if len(text) < _MIN_SKILL_TOKEN_LENGTH:
            continue
        # Generic stop words
        if text.lower().strip() in _GENERIC_STOP_WORDS:
            continue
        # Abstract concept: single lowercase word with no technical indicators
        if _looks_like_abstract_concept(text):
            continue
        filtered.append(text)
    return dedupe_keep_order(filtered)


def _looks_like_abstract_concept(text: str) -> bool:
    """Return True if text looks like an abstract concept, not a skill.

    A technical skill typically has at least one of:
      - an uppercase letter beyond the first (Java, TypeScript, REST)
      - a digit (C++, HTTP/2, 5G)
      - a non-alpha character (C#, .NET, Node.js, TCP/IP)
      - is an all-caps acronym of 2-5 letters (SQL, HTML, AWS, JSON)
    """
    # All-caps acronyms are valid skills
    if text.isupper() and text.isalpha() and 2 <= len(text) <= 5:
        return False
    # Contains non-alpha characters - likely technical
    if not text.replace(" ", "").replace("-", "").replace("_", "").isalpha():
        return False
    # Contains digits - likely technical
    if any(c.isdigit() for c in text):
        return False
    # Has internal uppercase (camelCase, PascalCase)
    if text[0].isalpha() and any(c.isupper() for c in text[1:]):
        return False
    # Multi-word (has space) - likely descriptive enough
    if " " in text:
        return False
    # Single lowercase word with no technical indicators — likely abstract
    return _ABSTRACT_CONCEPT_RE.match(text) is not None


def is_likely_skill_token(text: str) -> bool:
    """Return True if a single token looks like a plausible skill name."""
    if not text or not text.strip():
        return False
    token = normalize_whitespace(text)
    if not token:
        return False
    if len(token) < _MIN_SKILL_TOKEN_LENGTH:
        return False
    if token.lower() in _GENERIC_STOP_WORDS:
        return False
    if _looks_like_abstract_concept(token):
        return False
    return True
