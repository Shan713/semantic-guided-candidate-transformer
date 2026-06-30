"""ATS JSON adapter with configurable mapping.

This adapter deterministically maps ATS JSON payload fields into CandidateFragment.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Dict

from src.adapters.enrichment_helpers import make_records, normalize_url, parse_date_value, split_multivalue
from src.interfaces.base_adapter import BaseAdapter
from src.models.domain_models import CandidateFragment, Education, Email, Experience, FieldEvidence, Links, Location, Phone, Skill, SourceMetadata
from src.utils.hashing import sha256_text
from src.utils.ids import deterministic_candidate_id, new_uuid_hex
from src.utils.normalizers import normalize_email, normalize_phone, normalize_whitespace

logger = logging.getLogger("sgct.adapters.ats")


DEFAULT_MAPPING = {
    "candidateName": "full_name",
    "mail": "emails",
    "emails": "emails",
    "currentEmployer": "current_company",
    "position": "title",
    "location": "location",
    "headline": "headline",
}


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("_", "").replace(" ", "")


def _first_matching_value(data: Any, aliases: set[str]) -> Any:
    if isinstance(data, dict):
        for key, value in data.items():
            if _normalize_key(str(key)) in aliases:
                return value
            nested = _first_matching_value(value, aliases)
            if nested is not None:
                return nested
    elif isinstance(data, list):
        for item in data:
            nested = _first_matching_value(item, aliases)
            if nested is not None:
                return nested
    return None


def _collect_matching_values(data: Any, aliases: set[str]) -> list[Any]:
    collected: list[Any] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if _normalize_key(str(key)) in aliases:
                collected.append(value)
            if isinstance(value, (dict, list)):
                collected.extend(_collect_matching_values(value, aliases))
    elif isinstance(data, list):
        for item in data:
            collected.extend(_collect_matching_values(item, aliases))
    return collected


def _to_list_of_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return split_multivalue(value)
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            if isinstance(item, str):
                values.extend(split_multivalue(item))
            elif isinstance(item, dict):
                for candidate in ("name", "value", "label", "skill", "title", "text"):
                    if item.get(candidate):
                        values.extend(split_multivalue(str(item.get(candidate))))
                        break
        return values
    if isinstance(value, dict):
        for candidate in ("name", "value", "label", "text"):
            if value.get(candidate):
                return split_multivalue(str(value.get(candidate)))
    return split_multivalue(str(value))


def _parse_links(raw_input: dict[str, Any]) -> Links:
    links = Links()
    for field, aliases in (
        ("linkedin", ["linkedin", "linkedinurl", "profileurl", "profileURL"]),
        ("github", ["github", "githuburl", "github_url"]),
        ("portfolio", ["portfolio", "website", "websiteurl", "url"]),
    ):
        value = _first_matching_value(raw_input, {_normalize_key(alias) for alias in aliases})
        if isinstance(value, str):
            normalized = normalize_url(value)
            if normalized:
                setattr(links, field, normalized)
    social_links = _collect_matching_values(raw_input, {_normalize_key(name) for name in ["links", "socialLinks", "socialProfiles"]})
    for item in social_links:
        if isinstance(item, dict):
            for key, value in item.items():
                if not isinstance(value, str):
                    continue
                normalized = normalize_url(value)
                if not normalized:
                    continue
                key_name = _normalize_key(str(key))
                if "linkedin" in key_name and not links.linkedin:
                    links.linkedin = normalized
                elif "github" in key_name and not links.github:
                    links.github = normalized
                elif "portfolio" in key_name or "website" in key_name or "url" in key_name:
                    if not links.portfolio:
                        links.portfolio = normalized
                    else:
                        links.other.append(normalized)
        elif isinstance(item, str):
            normalized = normalize_url(item)
            if normalized:
                if "linkedin.com" in normalized and not links.linkedin:
                    links.linkedin = normalized
                elif "github.com" in normalized and not links.github:
                    links.github = normalized
                elif not links.portfolio:
                    links.portfolio = normalized
                else:
                    links.other.append(normalized)
    return links


def _parse_location(value: Any) -> Location:
    if isinstance(value, dict):
        city = normalize_whitespace(value.get("city") or value.get("town"))
        region = normalize_whitespace(value.get("state") or value.get("region") or value.get("province"))
        country = normalize_whitespace(value.get("country") or value.get("countryName"))
        raw = normalize_whitespace(value.get("raw") or value.get("address") or ", ".join(part for part in [city, region, country] if part))
        return Location(raw=raw, city=city, region=region, country=country, confidence=0.0)
    if isinstance(value, str):
        raw = normalize_whitespace(value)
        parts = [normalize_whitespace(part) for part in raw.split(",") if normalize_whitespace(part)]
        city = parts[0] if parts else None
        region = parts[1] if len(parts) == 3 else None
        country = parts[-1] if len(parts) >= 2 else None
        if len(parts) == 2:
            region = None
        return Location(raw=raw, city=city, region=region, country=country, confidence=0.0)
    return Location(raw=None, confidence=0.0)


def _parse_experience_item(item: Any) -> Experience | None:
    if not isinstance(item, dict):
        return None
    company = normalize_whitespace(item.get("company") or item.get("currentEmployer") or item.get("employer") or item.get("organization"))
    title = normalize_whitespace(item.get("title") or item.get("designation") or item.get("position") or item.get("role"))
    if not company and not title:
        return None
    start = parse_date_value(str(item.get("startDate") or item.get("start") or item.get("from") or ""))
    end_text = item.get("endDate") or item.get("end") or item.get("to")
    end = None if isinstance(end_text, str) and end_text.lower() == "present" else parse_date_value(str(end_text or ""))
    summary_source = item.get("summary") or item.get("description") or item.get("highlights")
    if isinstance(summary_source, list):
        summary_source = " ".join(str(part) for part in summary_source if part)
    summary = normalize_whitespace(summary_source) if summary_source is not None else None
    location = _parse_location(item.get("location")) if item.get("location") is not None else None
    return Experience(
        company=company or "",
        title=title or "",
        start=start,
        end=end,
        summary=summary,
        location=location,
        confidence=1.0,
        evidence_ids=[],
    )


def _parse_education_item(item: Any) -> Education | None:
    if not isinstance(item, dict):
        return None
    institution = normalize_whitespace(item.get("institution") or item.get("school") or item.get("university") or item.get("college"))
    degree = normalize_whitespace(item.get("degree") or item.get("qualification") or item.get("program") or item.get("course"))
    field = normalize_whitespace(item.get("field") or item.get("specialization") or item.get("major"))
    if not institution and not degree and not field:
        return None
    start_year = item.get("startYear") or item.get("fromYear") or item.get("start")
    end_year = item.get("endYear") or item.get("toYear") or item.get("end")
    return Education(
        institution=institution or "",
        degree=degree or "",
        field=field,
        start_year=int(start_year) if str(start_year or "").isdigit() else None,
        end_year=int(end_year) if str(end_year or "").isdigit() else None,
        confidence=1.0,
        evidence_ids=[],
    )


class ATSJSONAdapter(BaseAdapter):
    def __init__(self, mapping: Dict[str, str] | None = None) -> None:
        self.mapping = mapping or DEFAULT_MAPPING

    def adapt(self, raw_input: Dict[str, Any], context) -> CandidateFragment:
        src_meta = SourceMetadata(
            source_name="ats_json",
            source_record_id=str(raw_input.get("id", raw_input.get("candidateId", ""))),
            source_file="ats_json",
            ingested_at_utc=datetime.now(UTC),
            extractor_name="ats_json_adapter",
            extractor_version="1.0",
            extraction_quality=0.92,
            raw_reference_hash=sha256_text(str(raw_input)),
        )

        full_name = normalize_whitespace(_first_matching_value(raw_input, {_normalize_key(value) for value in ["candidateName", "full_name", "fullName", "name"]}))
        email_source = _first_matching_value(raw_input, {_normalize_key(value) for value in ["mail", "emails", "email", "primaryEmail", "primary_email"]})
        email_values = [normalize_email(value) for value in split_multivalue(email_source if isinstance(email_source, str) else "")]
        if not email_values and isinstance(email_source, list):
            for entry in email_source:
                if isinstance(entry, dict):
                    candidate = entry.get("email") or entry.get("value") or entry.get("address")
                    if candidate:
                        normalized = normalize_email(str(candidate))
                        if normalized:
                            email_values.append(normalized)
                elif isinstance(entry, str):
                    normalized = normalize_email(entry)
                    if normalized:
                        email_values.append(normalized)
        email_values = [value for value in email_values if value]

        phone_source = _first_matching_value(raw_input, {_normalize_key(value) for value in ["phone", "phones", "mobile", "mobileNumber", "mobile_number"]})
        phone_values = [normalize_phone(value, None) for value in split_multivalue(phone_source if isinstance(phone_source, str) else "")]
        if not phone_values and isinstance(phone_source, list):
            for entry in phone_source:
                if isinstance(entry, dict):
                    candidate = entry.get("phone") or entry.get("value") or entry.get("number") or entry.get("mobile")
                    if candidate:
                        normalized = normalize_phone(str(candidate), None)
                        if normalized:
                            phone_values.append(normalized)
                elif isinstance(entry, str):
                    normalized = normalize_phone(entry, None)
                    if normalized:
                        phone_values.append(normalized)
        phone_values = [value for value in phone_values if value]

        links = _parse_links(raw_input)
        location_value = _first_matching_value(raw_input, {_normalize_key(value) for value in ["location", "locationDetails", "currentLocation", "address", "city", "country"]})
        location = _parse_location(location_value)
        headline = normalize_whitespace(_first_matching_value(raw_input, {_normalize_key(value) for value in ["headline", "designation", "role", "title", "candidateSummary", "profileSummary"]}))

        skill_sources = _collect_matching_values(raw_input, {_normalize_key(value) for value in ["skills", "technicalSkills", "skillSet", "skillset"]})
        skill_values: list[str] = []
        for value in skill_sources:
            skill_values.extend(_to_list_of_strings(value))
        skill_values = [normalize_whitespace(value) for value in skill_values if normalize_whitespace(value)]
        skill_values = list(dict.fromkeys(skill_values))

        experience_sources = _collect_matching_values(raw_input, {_normalize_key(value) for value in ["experience", "employmentHistory", "workHistory", "experienceHistory"]})
        experience: list[Experience] = []
        for source_item in experience_sources:
            if isinstance(source_item, list):
                for item in source_item:
                    parsed = _parse_experience_item(item)
                    if parsed:
                        experience.append(parsed)
            else:
                parsed = _parse_experience_item(source_item)
                if parsed:
                    experience.append(parsed)

        current_company = normalize_whitespace(_first_matching_value(raw_input, {_normalize_key(value) for value in ["currentEmployer", "currentCompany", "company"]}))
        designation = normalize_whitespace(_first_matching_value(raw_input, {_normalize_key(value) for value in ["designation", "position", "title"]}))
        if current_company and designation and not experience:
            experience.append(
                Experience(
                    company=current_company,
                    title=designation,
                    summary=normalize_whitespace(_first_matching_value(raw_input, {_normalize_key(value) for value in ["candidateSummary", "summary", "profileSummary"]})),
                    confidence=1.0,
                    evidence_ids=[],
                )
            )

        education_sources = _collect_matching_values(raw_input, {_normalize_key(value) for value in ["education", "educationHistory", "academics", "educationDetails"]})
        education: list[Education] = []
        for source_item in education_sources:
            if isinstance(source_item, list):
                for item in source_item:
                    parsed = _parse_education_item(item)
                    if parsed:
                        education.append(parsed)
            else:
                parsed = _parse_education_item(source_item)
                if parsed:
                    education.append(parsed)

        if not education:
            institution = normalize_whitespace(_first_matching_value(raw_input, {_normalize_key(value) for value in ["institution", "school", "university", "college"]}))
            degree = normalize_whitespace(_first_matching_value(raw_input, {_normalize_key(value) for value in ["degree", "qualification", "program", "course"]}))
            field = normalize_whitespace(_first_matching_value(raw_input, {_normalize_key(value) for value in ["field", "specialization", "major"]}))
            if institution or degree or field:
                education.append(
                    Education(
                        institution=institution or "",
                        degree=degree or "",
                        field=field,
                        confidence=1.0,
                        evidence_ids=[],
                    )
                )

        projects = _collect_matching_values(raw_input, {_normalize_key(value) for value in ["projects", "project", "portfolioProjects"]})
        certifications = _collect_matching_values(raw_input, {_normalize_key(value) for value in ["certifications", "certification", "certificates"]})
        languages = _collect_matching_values(raw_input, {_normalize_key(value) for value in ["languages", "language"]})

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
                method="json_parsing",
                rule_name="ats_json_extraction",
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
        if location.raw or location.city or location.region or location.country:
            add("location", location.model_dump(exclude_none=True), location.model_dump(exclude_none=True))
        if headline:
            add("headline", headline, headline)
        for skill in skill_values:
            add("skills", skill, skill)
        for item in experience:
            add("experience", item.model_dump(exclude_none=True), item.model_dump(exclude_none=True))
        for item in education:
            add("education", item.model_dump(exclude_none=True), item.model_dump(exclude_none=True))
        for item in projects:
            add("projects", item, item)
        for item in certifications:
            add("certifications", item, item)
        for item in languages:
            add("languages", item, item)
        for link_name, value in (("linkedin", links.linkedin), ("github", links.github), ("portfolio", links.portfolio)):
            if value:
                add("links", {link_name: value}, {link_name: value})

        fragment = CandidateFragment(
            fragment_id=new_uuid_hex(),
            external_candidate_id=deterministic_candidate_id(full_name or "", email_values[0] if email_values else src_meta.source_record_id or "ats_json"),
            source_metadata=src_meta,
            full_name=full_name,
            emails=[Email(value=email, normalized=email, confidence=1.0, evidence_ids=[fe.evidence_id for fe in field_evidence if fe.field == "emails"]) for email in email_values],
            phones=[Phone(raw=phone, normalized_e164=phone, confidence=1.0, evidence_ids=[fe.evidence_id for fe in field_evidence if fe.field == "phones"]) for phone in phone_values],
            location=location,
            links=links,
            headline=headline,
            skills=[Skill(name=skill, confidence=1.0, sources=[src_meta.source_name.value], evidence_ids=[skill_evidence.evidence_id]) for skill, skill_evidence in zip(skill_values, [item for item in field_evidence if item.field == "skills"])],
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
