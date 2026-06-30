from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import dateparser

from src.models.domain_models import (
    CandidateFragment,
    DecisionTrace,
    Education,
    Email,
    Experience,
    FieldEvidence,
    Links,
    Location,
    Phone,
    ProvenanceRecord,
    Skill,
    SourceMetadata,
    TransformationRecord,
)
from src.models.enums import EntityDomain, ResolverType, SemanticResolutionStage, SourceType
from src.utils.ids import deterministic_candidate_id, new_uuid_hex
from src.utils.normalizers import dedupe_keep_order, filter_skill_tokens, is_likely_skill_token, normalize_email, normalize_extracted_text, normalize_merged_words, normalize_phone, normalize_whitespace, repair_ocr_tokens


SECTION_ALIASES = {
    "summary": ["summary"],
    "experience": ["experience", "work experience", "professional experience"],
    "education": ["education"],
    "skills": ["skills"],
    "projects": ["projects"],
    "certifications": ["certifications", "certification"],
    "languages": ["languages", "language"],
    "achievements": ["achievements", "awards"],
}

SKILL_SECTION_PREFIXES = [
    "Programming Languages",
    "Core CS Fundamentals",
    "Backend & Web Development",
    "Databases & Data Management",
    "Systems & Networking",
    "Embedded Systems & IoT",
    "Tools & Platforms",
    "Automation & Engineering Practices",
]


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


def split_multivalue(text: str | None) -> list[str]:
    if not text:
        return []
    parts = [normalize_whitespace(piece) for piece in re.split(r"[;,|\n]", text) if normalize_whitespace(piece)]
    return dedupe_keep_order([part for part in parts if part])


def _normalize_skill_token(text: str) -> str:
    expanded = normalize_merged_words(text)
    return expanded or text


def parse_date_value(value: str | None) -> date | None:
    if not value:
        return None
    parsed = dateparser.parse(value)
    return parsed.date() if parsed else None


def parse_year_value(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", value)
    return int(match.group(0)) if match else None


def parse_range_text(text: str | None) -> tuple[int | None, int | None, date | None, date | None, str]:
    if not text:
        return None, None, None, None, ""
    cleaned = normalize_whitespace(text) or ""
    cleaned = cleaned.replace("–", "-")
    year_match = re.match(r"^(?P<start>\d{4})\s*-\s*(?P<end>\d{4})\s*(?P<body>.*)$", cleaned)
    if year_match:
        start_year = int(year_match.group("start"))
        end_year = int(year_match.group("end"))
        return start_year, end_year, None, None, year_match.group("body").strip()
    date_match = re.match(
        r"^(?P<start>[A-Za-z]{3,9}\s+\d{4})\s*-\s*(?P<end>[A-Za-z]{3,9}\s+\d{4}|Present)\s*(?P<body>.*)$",
        cleaned,
        flags=re.I,
    )
    if date_match:
        start_date = parse_date_value(date_match.group("start"))
        end_text = date_match.group("end")
        end_date = None if end_text.lower() == "present" else parse_date_value(end_text)
        return None, None, start_date, end_date, date_match.group("body").strip()
    return None, None, None, None, cleaned


def make_records(
    *,
    field_name: str,
    original_value: Any,
    canonical_value: Any,
    source: SourceMetadata,
    method: str,
    rule_name: str,
    confidence: float = 1.0,
) -> tuple[FieldEvidence, TransformationRecord, DecisionTrace, ProvenanceRecord]:
    record_id = new_uuid_hex()
    evidence_id = new_uuid_hex()
    tr = TransformationRecord(
        record_id=record_id,
        field=field_name,
        original_value=original_value,
        canonical_value=canonical_value,
        resolver=ResolverType.ONTOLOGY_LOADER.value,
        rule_name=rule_name,
        ontology_domain="",
        matched_alias=None,
        semantic_confidence=confidence,
        resolution_stage=SemanticResolutionStage.UNKNOWN_VALUE,
        related_to_applied=[],
        timestamp_utc=datetime.now(UTC),
    )
    fe = FieldEvidence(
        evidence_id=evidence_id,
        field=field_name,
        original_value=original_value,
        canonical_value=canonical_value,
        source=source,
        method=method,
        semantic_rule=rule_name,
        confidence=confidence,
        timestamp_utc=datetime.now(UTC),
        transformation_ref=record_id,
    )
    dt = DecisionTrace(
        trace_id=new_uuid_hex(),
        stage="extraction",
        field=field_name,
        decision_type="parse",
        candidates_considered=[original_value] if original_value is not None else [],
        selected_value=canonical_value,
        rationale=f"Deterministic extraction for {field_name}",
        rule_or_policy=rule_name,
        confidence=confidence,
        resolution_order_step=0,
        fallback_used=False,
        timestamp_utc=datetime.now(UTC),
    )
    pr = ProvenanceRecord(
        field=field_name,
        original_value=original_value,
        canonical_value=canonical_value,
        source=source.source_name.value if hasattr(source.source_name, "value") else str(source.source_name),
        method=method,
        timestamp_utc=datetime.now(UTC),
        transformation_rule=rule_name,
        confidence=confidence,
        source_record_id=source.source_record_id,
    )
    return fe, tr, dt, pr


def build_text_fragment(text: str, source: SourceMetadata, source_label: str) -> CandidateFragment:
    normalized_text = normalize_extracted_text(text.replace("\\n", "\n")) or ""
    # Apply generic OCR repair to the full extracted text
    normalized_text = repair_ocr_tokens(normalized_text) or normalized_text
    lines = [normalize_merged_words(normalize_whitespace(line)) for line in normalized_text.splitlines()]
    lines = [line for line in lines if line]
    sections = _split_sections(lines)

    full_name = _extract_name(lines)
    email_values = [normalize_email(email) for email in _extract_emails(text)]
    email_values = [value for value in email_values if value]
    phone_values = [normalize_phone(phone, None) for phone in _extract_phones(text)]
    phone_values = [value for value in phone_values if value]
    link_values = [_normalize_link(link) for link in _extract_links(text)]
    link_values = [value for value in link_values if value]

    summary_text = _combine_lines(sections.get("summary", []))
    # Apply OCR repair to summary/headline
    summary_text = repair_ocr_tokens(summary_text) or summary_text
    headline = summary_text or None

    skills = _parse_skills(sections.get("skills", []))
    experiences = _parse_experiences(sections.get("experience", []))
    educations = _parse_educations(sections.get("education", []))

    field_evidence: list[FieldEvidence] = []
    transformation_history: list[TransformationRecord] = []
    decision_trace: list[DecisionTrace] = []
    provenance: list[ProvenanceRecord] = []

    if full_name:
        _append_record(field_evidence, transformation_history, decision_trace, provenance, make_records(
            field_name="full_name",
            original_value=full_name,
            canonical_value=full_name,
            source=source,
            method=f"{source_label}_text_extraction",
            rule_name=f"{source_label}_name_extraction",
        ))

    for email in email_values:
        _append_record(field_evidence, transformation_history, decision_trace, provenance, make_records(
            field_name="emails",
            original_value=email,
            canonical_value=email,
            source=source,
            method=f"{source_label}_text_extraction",
            rule_name=f"{source_label}_email_extraction",
        ))

    for phone in phone_values:
        _append_record(field_evidence, transformation_history, decision_trace, provenance, make_records(
            field_name="phones",
            original_value=phone,
            canonical_value=phone,
            source=source,
            method=f"{source_label}_text_extraction",
            rule_name=f"{source_label}_phone_extraction",
        ))

    links = Links()
    for link in link_values:
        if "linkedin.com" in link and not links.linkedin:
            links.linkedin = link
        elif "github.com" in link and not links.github:
            links.github = link
        elif not links.portfolio:
            links.portfolio = link
        else:
            links.other.append(link)
        _append_record(field_evidence, transformation_history, decision_trace, provenance, make_records(
            field_name="links",
            original_value=link,
            canonical_value=link,
            source=source,
            method=f"{source_label}_text_extraction",
            rule_name=f"{source_label}_link_extraction",
        ))

    location = Location(raw=None, confidence=0.0)
    location_candidates = _extract_location_candidates(lines)
    if location_candidates:
        location.raw = location_candidates[0]
        _append_record(field_evidence, transformation_history, decision_trace, provenance, make_records(
            field_name="location",
            original_value=location.raw,
            canonical_value=location.raw,
            source=source,
            method=f"{source_label}_text_extraction",
            rule_name=f"{source_label}_location_extraction",
        ))

    if headline:
        _append_record(field_evidence, transformation_history, decision_trace, provenance, make_records(
            field_name="headline",
            original_value=headline,
            canonical_value=headline,
            source=source,
            method=f"{source_label}_text_extraction",
            rule_name=f"{source_label}_summary_extraction",
        ))

    skill_objects: list[Skill] = []
    for skill in skills:
        fe, tr, dt, pr = make_records(
            field_name="skills",
            original_value=skill,
            canonical_value=skill,
            source=source,
            method=f"{source_label}_text_extraction",
            rule_name=f"{source_label}_skill_extraction",
        )
        field_evidence.append(fe)
        transformation_history.append(tr)
        decision_trace.append(dt)
        provenance.append(pr)
        skill_objects.append(Skill(name=skill, confidence=1.0, sources=[source.source_name.value if hasattr(source.source_name, "value") else str(source.source_name)], evidence_ids=[fe.evidence_id]))

    experience_objects: list[Experience] = []
    for experience in experiences:
        fe, tr, dt, pr = make_records(
            field_name="experience",
            original_value=experience["raw"],
            canonical_value={k: v for k, v in experience.items() if k != "raw"},
            source=source,
            method=f"{source_label}_text_extraction",
            rule_name=f"{source_label}_experience_extraction",
        )
        field_evidence.append(fe)
        transformation_history.append(tr)
        decision_trace.append(dt)
        provenance.append(pr)
        experience_objects.append(
            Experience(
                company=experience["company"],
                company_canonical=experience.get("company_canonical"),
                title=experience["title"],
                title_canonical=experience.get("title_canonical"),
                start=experience.get("start"),
                end=experience.get("end"),
                summary=experience.get("summary"),
                confidence=1.0,
                evidence_ids=[fe.evidence_id],
            )
        )

    education_objects: list[Education] = []
    for education in educations:
        # Apply OCR repair to education text fields
        institution = repair_ocr_tokens(education["institution"]) or education["institution"]
        degree = repair_ocr_tokens(education["degree"]) or education["degree"]
        field = repair_ocr_tokens(education.get("field")) or education.get("field")
        fe, tr, dt, pr = make_records(
            field_name="education",
            original_value=education["raw"],
            canonical_value={k: v for k, v in education.items() if k != "raw"},
            source=source,
            method=f"{source_label}_text_extraction",
            rule_name=f"{source_label}_education_extraction",
        )
        field_evidence.append(fe)
        transformation_history.append(tr)
        decision_trace.append(dt)
        provenance.append(pr)
        education_objects.append(
            Education(
                institution=institution,
                degree=degree,
                field=field,
                start_year=education.get("start_year"),
                end_year=education.get("end_year"),
                confidence=1.0,
                evidence_ids=[fe.evidence_id],
            )
        )

    for section_name in ("projects", "certifications", "languages", "achievements"):
        if sections.get(section_name):
            section_text = _combine_lines(sections[section_name])
            _append_record(field_evidence, transformation_history, decision_trace, provenance, make_records(
                field_name=section_name,
                original_value=section_text,
                canonical_value=section_text,
                source=source,
                method=f"{source_label}_text_extraction",
                rule_name=f"{source_label}_{section_name}_extraction",
            ))

    candidate_id_seed = full_name or (email_values[0] if email_values else source_label)
    external_candidate_id = deterministic_candidate_id(candidate_id_seed, email_values[0] if email_values else source_label)

    return CandidateFragment(
        fragment_id=new_uuid_hex(),
        external_candidate_id=external_candidate_id,
        source_metadata=source,
        full_name=full_name,
        emails=[Email(value=email, normalized=email, confidence=1.0) for email in email_values],
        phones=[Phone(raw=phone, normalized_e164=phone, confidence=1.0) for phone in phone_values],
        location=location,
        links=links,
        headline=headline,
        skills=skill_objects,
        experience=experience_objects,
        education=education_objects,
        field_evidence=field_evidence,
        provenance=provenance,
        decision_trace=decision_trace,
        transformation_history=transformation_history,
        confidence_records=[],
        validation_warnings=[],
    )


def _append_record(
    field_evidence: list[FieldEvidence],
    transformation_history: list[TransformationRecord],
    decision_trace: list[DecisionTrace],
    provenance: list[ProvenanceRecord],
    record_bundle: tuple[FieldEvidence, TransformationRecord, DecisionTrace, ProvenanceRecord],
) -> None:
    fe, tr, dt, pr = record_bundle
    field_evidence.append(fe)
    transformation_history.append(tr)
    decision_trace.append(dt)
    provenance.append(pr)


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {name: [] for name in SECTION_ALIASES}
    current: str | None = None
    for line in lines:
        header = _match_header(line)
        if header:
            current = header
            continue
        if current:
            sections[current].append(line)
    return sections


def _match_header(line: str) -> str | None:
    normalized = line.strip().lstrip("-•·●▪◦").strip().lower().rstrip(":")
    for canonical, aliases in SECTION_ALIASES.items():
        if normalized in aliases:
            return canonical
    return None


def _combine_lines(lines: list[str]) -> str:
    return normalize_whitespace(" ".join(lines)) or ""


def _extract_name(lines: list[str]) -> str | None:
    for line in lines[:5]:
        if "@" in line or re.search(r"\+?\d[\d\s().-]{6,}\d", line):
            continue
        if len(line.split()) >= 2 and len(line.split()) <= 6:
            return line
    return None


def _extract_emails(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)))


def _extract_phones(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\+?\d[\d\s().-]{6,}\d", text)))


def _extract_links(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"https?://[\w\-./?&=%#]+|www\.[\w\-./?&=%#]+", text)))


def _normalize_link(value: str) -> str:
    return normalize_url(value) or value


def _extract_location_candidates(lines: list[str]) -> list[str]:
    candidates: list[str] = []
    for line in lines[:6]:
        if "@" in line or re.search(r"\+?\d[\d\s().-]{6,}\d", line):
            continue
        if "," in line and len(line.split()) <= 8:
            candidates.append(line)
    return candidates


def _parse_skills(lines: list[str]) -> list[str]:
    if not lines:
        return []
    cleaned = []
    for line in lines:
        normalized_line = normalize_whitespace(line) or ""
        if not normalized_line:
            continue
        # Apply OCR repair before splitting
        normalized_line = repair_ocr_tokens(normalized_line) or normalized_line
        for prefix in SKILL_SECTION_PREFIXES:
            normalized_line = re.sub(rf"(?i)\b{re.escape(prefix)}\b", "|", normalized_line)
        tokens = re.split(r"[|,;\n]", normalized_line)
        for token in tokens:
            text = normalize_whitespace(token)
            if not text:
                continue
            text = text.strip("-•")
            text = _normalize_skill_token(text)
            # Repair OCR artifacts in individual tokens
            text = repair_ocr_tokens(text) or text
            if text and text not in SKILL_SECTION_PREFIXES:
                cleaned.append(text)
    # Filter orphan/noise tokens before dedup
    return filter_skill_tokens(dedupe_keep_order(cleaned))


def _parse_experiences(lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    header_patterns = [
        re.compile(r"^(?P<title>.+?) at (?P<company>.+?)(?: \((?P<context>.+?)\))?\s+(?P<start>[A-Za-z]{3} \d{4})\s*[-–]\s*(?P<end>[A-Za-z]{3} \d{4}|Present)$", re.I),
        re.compile(r"^(?P<title>.+?), (?P<company>.+?)(?: \((?P<context>.+?)\))?\s+(?P<start>[A-Za-z]{3} \d{4})\s*[-–]\s*(?P<end>[A-Za-z]{3} \d{4}|Present)$", re.I),
    ]
    for line in lines:
        parsed = None
        for pattern in header_patterns:
            match = pattern.match(line)
            if match:
                parsed = match
                break
        if parsed:
            if current:
                entries.append(current)
            start_date = parse_date_value(parsed.group("start"))
            end_text = parsed.group("end")
            end_date = None if end_text.lower() == "present" else parse_date_value(end_text)
            current = {
                "title": normalize_whitespace(parsed.group("title")) or parsed.group("title"),
                "company": normalize_whitespace(parsed.group("company")) or parsed.group("company"),
                "start": start_date,
                "end": end_date,
                "summary_lines": [],
                "raw": line,
            }
            continue
        if current is not None:
            if line.startswith(("-", "–", "•", "—")):
                current["summary_lines"].append(line.lstrip("-–•— "))
            elif line and not line.lower().startswith(tuple(SECTION_ALIASES.keys())):
                current["summary_lines"].append(line)
    if current:
        entries.append(current)

    parsed_entries: list[dict[str, Any]] = []
    for entry in entries:
        summary = normalize_whitespace(" ".join(entry.get("summary_lines", [])))
        # Apply OCR repair to experience summaries (generic)
        summary = repair_ocr_tokens(summary) or summary
        parsed_entries.append(
            {
                "company": entry["company"],
                "title": entry["title"],
                "start": entry.get("start"),
                "end": entry.get("end"),
                "summary": summary or None,
                "raw": entry["raw"],
            }
        )
    return parsed_entries


def _parse_educations(lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    range_pattern = re.compile(r"^(?P<start>\d{4})\s*[–-]\s*(?P<end>\d{4})\s+(?P<body>.+)$")
    for line in lines:
        match = range_pattern.match(line)
        if match:
            if current:
                entries.append(current)
            start_year = int(match.group("start"))
            end_year = int(match.group("end"))
            body = normalize_whitespace(match.group("body")) or ""
            degree = body
            field = None
            grade_hint = None
            if "CGPA:" in body:
                degree, grade_hint = body.split("CGPA:", 1)
            elif "Percentage:" in body:
                degree, grade_hint = body.split("Percentage:", 1)
            degree = normalize_whitespace(degree.rstrip()) or body
            if "," in degree:
                degree_part, field_part = [normalize_whitespace(part) for part in degree.split(",", 1)]
                degree = degree_part or degree
                field = field_part or None
            current = {
                "start_year": start_year,
                "end_year": end_year,
                "degree": degree,
                "field": field,
                "grade_hint": normalize_whitespace(grade_hint) if grade_hint else None,
                "institution_lines": [],
                "raw": line,
            }
            continue
        if current is not None:
            current["institution_lines"].append(line)
    if current:
        entries.append(current)

    parsed_entries: list[dict[str, Any]] = []
    for entry in entries:
        institution = normalize_whitespace(" ".join(entry.get("institution_lines", []))) or ""
        if "," in institution:
            institution = normalize_whitespace(institution.split(",", 1)[0]) or institution
        parsed_entries.append(
            {
                "institution": institution or "",
                "degree": entry["degree"],
                "field": entry.get("field"),
                "start_year": entry.get("start_year"),
                "end_year": entry.get("end_year"),
                "raw": entry["raw"],
            }
        )
    return parsed_entries