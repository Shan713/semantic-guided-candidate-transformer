"""CSV adapter: parses recruiter CSV files into CandidateFragment."""
from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, datetime
from typing import Any, Dict

from src.adapters.enrichment_helpers import make_records, normalize_url, parse_date_value, split_multivalue
from src.interfaces.base_adapter import BaseAdapter
from src.models.domain_models import CandidateFragment, Education, Email, Experience, FieldEvidence, Links, Location, Phone, Skill, SourceMetadata
from src.utils.hashing import sha256_text
from src.utils.ids import deterministic_candidate_id, new_uuid_hex
from src.utils.normalizers import normalize_email, normalize_phone, normalize_whitespace

logger = logging.getLogger("sgct.adapters.csv")


HEADER_MAP = {
    "full_name": ["full_name", "candidate_name", "name"],
    "emails": ["email", "emails", "mail"],
    "phones": ["phone", "mobile", "phone_number"],
    "current_company": ["company", "current_company", "employer"],
    "title": ["title", "designation", "position"],
    "headline": ["headline", "summary", "headline_text"],
    "skills": ["skills", "skill_list"],
    "education": ["education"],
    "experience": ["experience"],
    "linkedin": ["linkedin"],
    "github": ["github"],
    "website": ["website", "web", "url"],
    "portfolio": ["portfolio"],
    "country": ["country"],
    "city": ["city"],
    "state": ["state", "region"],
    "projects": ["projects"],
    "certifications": ["certifications", "certification"],
    "languages": ["languages", "language"],
    "recruiter_notes": ["recruiter_notes", "notes"],
    "start_date": ["start_date", "employment_start", "start"],
    "end_date": ["end_date", "employment_end", "end"],
    "institution": ["institution", "school", "college", "university"],
    "degree": ["degree"],
    "field": ["field", "specialization", "major"],
    "grade": ["grade", "cgpa", "percentage"],
}


def _invert_header_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for canonical, variants in HEADER_MAP.items():
        for variant in variants:
            mapping[variant.lower()] = canonical
    return mapping


_INVERTED = _invert_header_map()


class CSVAdapter(BaseAdapter):
    def adapt(self, raw_input: bytes | str, context) -> CandidateFragment:
        if isinstance(raw_input, bytes):
            try:
                text = raw_input.decode("utf-8")
            except UnicodeDecodeError:
                text = raw_input.decode("latin-1", errors="ignore")
        else:
            text = str(raw_input)

        stream = io.StringIO(text)
        reader = csv.DictReader(stream)
        rows = list(reader)

        src_meta = SourceMetadata(
            source_name="recruiter_csv",
            source_record_id=sha256_text(text)[:12],
            source_file="recruiter_csv",
            ingested_at_utc=datetime.now(UTC),
            extractor_name="csv_adapter",
            extractor_version="1.0",
            extraction_quality=0.92 if rows else 0.0,
            raw_reference_hash=sha256_text(text),
        )

        if not rows:
            return CandidateFragment(fragment_id=new_uuid_hex(), source_metadata=src_meta)

        row = rows[0]
        mapped: Dict[str, Any] = {}
        for header, value in row.items():
            if header is None:
                continue
            key = _INVERTED.get(header.strip().lower())
            if key:
                mapped[key] = value if value is not None else ""

        full_name = normalize_whitespace(mapped.get("full_name"))
        email_values = [normalize_email(value) for value in split_multivalue(mapped.get("emails") or mapped.get("email") or "")]
        email_values = [value for value in email_values if value]
        phone_values = [normalize_phone(value, None) for value in split_multivalue(mapped.get("phones") or mapped.get("phone") or "")]
        phone_values = [value for value in phone_values if value]

        links = Links(
            linkedin=normalize_url(mapped.get("linkedin")),
            github=normalize_url(mapped.get("github")),
            portfolio=normalize_url(mapped.get("portfolio") or mapped.get("website")),
            other=[],
        )
        if mapped.get("website") and not links.portfolio:
            links.portfolio = normalize_url(mapped.get("website"))

        city = normalize_whitespace(mapped.get("city"))
        region = normalize_whitespace(mapped.get("state"))
        country = normalize_whitespace(mapped.get("country"))
        location_raw = normalize_whitespace(mapped.get("location"))
        if not location_raw:
            parts = [part for part in [city, region, country] if part]
            location_raw = ", ".join(parts) if parts else None
        location = Location(raw=location_raw, city=city, region=region, country=country, confidence=0.0)

        headline = normalize_whitespace(mapped.get("headline") or mapped.get("summary") or mapped.get("title") or mapped.get("recruiter_notes"))

        skills = [Skill(name=value, confidence=1.0, sources=[src_meta.source_name.value], evidence_ids=[]) for value in split_multivalue(mapped.get("skills") or "") if value]

        experience: list[Experience] = []
        company = normalize_whitespace(mapped.get("current_company"))
        title = normalize_whitespace(mapped.get("title"))
        if company and title:
            experience.append(
                Experience(
                    company=company,
                    title=title,
                    start=parse_date_value(mapped.get("start_date")),
                    end=parse_date_value(mapped.get("end_date")),
                    summary=normalize_whitespace(mapped.get("recruiter_notes")),
                    confidence=1.0,
                    evidence_ids=[],
                )
            )

        education: list[Education] = []
        institution = normalize_whitespace(mapped.get("institution"))
        degree = normalize_whitespace(mapped.get("degree") or mapped.get("education"))
        field = normalize_whitespace(mapped.get("field"))
        if institution or degree or field:
            education.append(
                Education(
                    institution=institution or "",
                    degree=degree or "",
                    field=field,
                    start_year=None,
                    end_year=None,
                    confidence=1.0,
                    evidence_ids=[],
                )
            )

        field_evidence: list[FieldEvidence] = []
        transformation_history = []
        decision_trace = []
        provenance = []

        def add(field_name: str, original_value: Any, canonical_value: Any) -> None:
            fe, tr, dt, pr = make_records(
                field_name=field_name,
                original_value=original_value,
                canonical_value=canonical_value,
                source=src_meta,
                method="csv_parsing",
                rule_name="csv_row_extraction",
            )
            field_evidence.append(fe)
            transformation_history.append(tr)
            decision_trace.append(dt)
            provenance.append(pr)

        if full_name:
            add("full_name", full_name, full_name)
        for email in email_values:
            add("emails", email, email)
        for phone in phone_values:
            add("phones", phone, phone)
        if location_raw:
            add("location", location_raw, location_raw)
        if headline:
            add("headline", headline, headline)
        if company or title:
            add("experience", {"company": company, "title": title}, {"company": company, "title": title})
        if institution or degree or field:
            add("education", {"institution": institution, "degree": degree, "field": field}, {"institution": institution, "degree": degree, "field": field})
        for skill in skills:
            add("skills", skill.name, skill.name)
        for key in ("projects", "certifications", "languages", "recruiter_notes"):
            if mapped.get(key):
                add(key, mapped.get(key), mapped.get(key))
        for link_name, value in (("linkedin", links.linkedin), ("github", links.github), ("portfolio", links.portfolio)):
            if value:
                add("links", {link_name: value}, {link_name: value})

        candidate_id_seed = full_name or (email_values[0] if email_values else src_meta.source_record_id or "recruiter_csv")
        fragment = CandidateFragment(
            fragment_id=new_uuid_hex(),
            external_candidate_id=deterministic_candidate_id(candidate_id_seed, email_values[0] if email_values else src_meta.source_record_id or "recruiter_csv"),
            source_metadata=src_meta,
            full_name=full_name,
            emails=[Email(value=email, normalized=email, confidence=1.0, evidence_ids=[fe.evidence_id for fe in field_evidence if fe.field == "emails"]) for email in email_values],
            phones=[Phone(raw=phone, normalized_e164=phone, confidence=1.0, evidence_ids=[fe.evidence_id for fe in field_evidence if fe.field == "phones"]) for phone in phone_values],
            location=location,
            links=links,
            headline=headline,
            skills=skills,
            experience=experience,
            education=education,
            field_evidence=field_evidence,
            provenance=provenance,
            decision_trace=decision_trace,
            transformation_history=transformation_history,
            confidence_records=[],
            validation_warnings=[],
        )

        return fragment
