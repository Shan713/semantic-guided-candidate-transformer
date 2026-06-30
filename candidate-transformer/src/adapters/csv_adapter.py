"""CSV adapter: parses recruiter CSV files into CandidateFragment."""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, UTC
from typing import Dict, Any

from src.interfaces.base_adapter import BaseAdapter
from src.models.domain_models import (
    CandidateFragment,
    SourceMetadata,
    FieldEvidence,
    Email,
    Phone,
    Links,
    Location,
)
from src.utils.ids import new_uuid_hex, deterministic_candidate_id
from src.utils.hashing import sha256_text
from src.utils.normalizers import normalize_email, normalize_phone, normalize_whitespace, dedupe_keep_order
from src.models.domain_models import TransformationRecord, DecisionTrace
from src.models.enums import SemanticResolutionStage, ResolverType, EntityDomain
from datetime import datetime, UTC

logger = logging.getLogger("sgct.adapters.csv")


HEADER_MAP = {
    "full_name": ["full_name", "candidate_name", "name"],
    "emails": ["email", "emails", "mail"],
    "phones": ["phone", "mobile", "phone_number"],
    "current_company": ["company", "current_company", "employer"],
    "title": ["title", "designation", "position"],
    "headline": ["headline", "summary", "headline_text"],
    "skills": ["skills", "skill_list"],
    "location": ["location", "city", "region"],
    "linkedin": ["linkedin"],
    "github": ["github"],
    "portfolio": ["portfolio"],
}


def _invert_header_map() -> Dict[str, str]:
    m = {}
    for canonical, variants in HEADER_MAP.items():
        for v in variants:
            m[v.lower()] = canonical
    return m


_INVERTED = _invert_header_map()


class CSVAdapter(BaseAdapter):
    def adapt(self, raw_input: bytes | str, context) -> CandidateFragment:
        # raw_input may be bytes or string; handle encoding
        if isinstance(raw_input, bytes):
            try:
                text = raw_input.decode("utf-8")
            except UnicodeDecodeError:
                text = raw_input.decode("latin-1", errors="ignore")
        else:
            text = str(raw_input)

        stream = io.StringIO(text)
        reader = csv.DictReader(stream)

        # If no rows, return empty fragment
        rows = list(reader)
        if not rows:
            # Build minimal fragment
            src_meta = SourceMetadata(
                source_name="recruiter_csv",
                source_record_id="",
                source_file="",
                ingested_at_utc=datetime.now(UTC),
                extractor_name="csv_adapter",
                extractor_version=None,
                extraction_quality=0.0,
                raw_reference_hash=sha256_text(text),
            )
            return CandidateFragment(fragment_id=new_uuid_hex(), source_metadata=src_meta)

        # For this phase we only process the first non-empty row deterministically
        row = rows[0]
        mapped: Dict[str, Any] = {}
        for h, v in row.items():
            if h is None:
                continue
            key = _INVERTED.get(h.strip().lower())
            if not key:
                continue
            mapped[key] = v if v is not None else ""

        src_meta = SourceMetadata(
            source_name="recruiter_csv",
            source_record_id=sha256_text(text)[:12],
            source_file="recruiter_csv",
            ingested_at_utc=datetime.now(UTC),
            extractor_name="csv_adapter",
            extractor_version="1.0",
            extraction_quality=0.9,
            raw_reference_hash=sha256_text(text),
        )

        # Build CandidateFragment fields
        full_name = normalize_whitespace(mapped.get("full_name"))
        emails_raw = mapped.get("emails") or mapped.get("email") or ""
        emails = []
        for e in (emails_raw.split(";") if emails_raw else []):
            ne = normalize_email(e)
            if ne:
                emails.append(Email(value=e.strip(), normalized=ne, confidence=0.0))

        phones_raw = mapped.get("phones") or mapped.get("phone") or ""
        phones = []
        for p in (phones_raw.split(";") if phones_raw else []):
            np = normalize_phone(p, None)
            if np:
                phones.append(Phone(raw=p.strip(), normalized_e164=np, confidence=0.0))

        links = Links(
            linkedin=normalize_whitespace(mapped.get("linkedin")),
            github=normalize_whitespace(mapped.get("github")),
            portfolio=normalize_whitespace(mapped.get("portfolio")),
            other=[],
        )

        location = Location(raw=normalize_whitespace(mapped.get("location")), confidence=0.0)

        # field evidence and transformation records per extracted field
        fes = []
        trs = []

        def make_tr(field_name: str, original_val: Any) -> TransformationRecord:
            return TransformationRecord(
                record_id=new_uuid_hex(),
                field=field_name,
                original_value=original_val,
                canonical_value=None,
                resolver=ResolverType.ONTOLOGY_LOADER.value,
                rule_name="csv_extraction",
                ontology_domain="",
                matched_alias=None,
                semantic_confidence=0.0,
                resolution_stage=SemanticResolutionStage.UNKNOWN_VALUE,
                related_to_applied=[],
                timestamp_utc=datetime.now(UTC),
            )

        # full_name
        tr_name = make_tr("full_name", full_name)
        fe_name = FieldEvidence(
            evidence_id=new_uuid_hex(),
            field="full_name",
            original_value=full_name,
            canonical_value=None,
            source=src_meta,
            method="csv_parsing",
            semantic_rule=None,
            confidence=0.0,
            timestamp_utc=datetime.now(UTC),
            transformation_ref=tr_name.record_id,
        )
        fes.append(fe_name)
        trs.append(tr_name)

        # emails
        tr_em = make_tr("emails", emails_raw)
        fe_em = FieldEvidence(
            evidence_id=new_uuid_hex(),
            field="emails",
            original_value=emails_raw,
            canonical_value=None,
            source=src_meta,
            method="csv_parsing",
            semantic_rule=None,
            confidence=0.0,
            timestamp_utc=datetime.now(UTC),
            transformation_ref=tr_em.record_id,
        )
        fes.append(fe_em)
        trs.append(tr_em)

        # phones
        tr_ph = make_tr("phones", phones_raw)
        fe_ph = FieldEvidence(
            evidence_id=new_uuid_hex(),
            field="phones",
            original_value=phones_raw,
            canonical_value=None,
            source=src_meta,
            method="csv_parsing",
            semantic_rule=None,
            confidence=0.0,
            timestamp_utc=datetime.now(UTC),
            transformation_ref=tr_ph.record_id,
        )
        fes.append(fe_ph)
        trs.append(tr_ph)

        # location
        tr_loc = make_tr("location", location.raw)
        fe_loc = FieldEvidence(
            evidence_id=new_uuid_hex(),
            field="location",
            original_value=location.raw,
            canonical_value=None,
            source=src_meta,
            method="csv_parsing",
            semantic_rule=None,
            confidence=0.0,
            timestamp_utc=datetime.now(UTC),
            transformation_ref=tr_loc.record_id,
        )
        fes.append(fe_loc)
        trs.append(tr_loc)

        fragment = CandidateFragment(
            fragment_id=new_uuid_hex(),
            external_candidate_id=deterministic_candidate_id(full_name or "", emails_raw or ""),
            source_metadata=src_meta,
            full_name=full_name,
            emails=emails,
            phones=phones,
            location=location,
            links=links,
            field_evidence=fes,
            provenance=[],
            decision_trace=[],
            transformation_history=trs,
            confidence_records=[],
            validation_warnings=[],
        )

        return fragment
