"""ATS JSON adapter with configurable mapping.

This adapter deterministically maps ATS JSON payload fields into CandidateFragment.
"""
from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Any, Dict

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
from src.models.domain_models import TransformationRecord, DecisionTrace
from src.models.enums import SemanticResolutionStage, ResolverType, EntityDomain
from datetime import datetime, UTC
from src.utils.ids import new_uuid_hex, deterministic_candidate_id
from src.utils.hashing import sha256_text
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


class ATSJSONAdapter(BaseAdapter):
    def __init__(self, mapping: Dict[str, str] | None = None) -> None:
        self.mapping = mapping or DEFAULT_MAPPING

    def adapt(self, raw_input: Dict[str, Any], context) -> CandidateFragment:
        # raw_input expected to be a dict / parsed JSON
        src_meta = SourceMetadata(
            source_name="ats_json",
            source_record_id=str(raw_input.get("id", "")),
            source_file="ats_json",
            ingested_at_utc=datetime.now(UTC),
            extractor_name="ats_json_adapter",
            extractor_version="1.0",
            extraction_quality=0.9,
            raw_reference_hash=sha256_text(str(raw_input)),
        )

        def get_mapped(k: str):
            return raw_input.get(k)

        full_name = normalize_whitespace(get_mapped("candidateName") or get_mapped("candidateName"))

        emails = []
        raw_mail = get_mapped("mail") or get_mapped("emails")
        if isinstance(raw_mail, list):
            for e in raw_mail:
                ne = normalize_email(e)
                if ne:
                    emails.append(Email(value=e, normalized=ne, confidence=0.0))
        elif isinstance(raw_mail, str):
            ne = normalize_email(raw_mail)
            if ne:
                emails.append(Email(value=raw_mail, normalized=ne, confidence=0.0))

        phones = []
        raw_phone = get_mapped("phone") or get_mapped("phones")
        if isinstance(raw_phone, list):
            for p in raw_phone:
                np = normalize_phone(p, None)
                if np:
                    phones.append(Phone(raw=p, normalized_e164=np, confidence=0.0))
        elif isinstance(raw_phone, str) and raw_phone:
            np = normalize_phone(raw_phone, None)
            if np:
                phones.append(Phone(raw=raw_phone, normalized_e164=np, confidence=0.0))

        links = Links(
            linkedin=normalize_whitespace(raw_input.get("linkedin")),
            github=normalize_whitespace(raw_input.get("github")),
            portfolio=normalize_whitespace(raw_input.get("portfolio")),
            other=[],
        )

        location = Location(raw=normalize_whitespace(raw_input.get("location")), confidence=0.0)

        # create per-field transformation records and evidence
        def make_tr(field_name: str, original_val: object) -> TransformationRecord:
            return TransformationRecord(
                record_id=new_uuid_hex(),
                field=field_name,
                original_value=original_val,
                canonical_value=None,
                resolver=ResolverType.ONTOLOGY_LOADER.value,
                rule_name="ats_json_extraction",
                ontology_domain="",
                matched_alias=None,
                semantic_confidence=0.0,
                resolution_stage=SemanticResolutionStage.UNKNOWN_VALUE,
                related_to_applied=[],
                timestamp_utc=datetime.now(UTC),
            )

        fes = []
        trs = []

        tr_name = make_tr("full_name", full_name)
        fe_name = FieldEvidence(
            evidence_id=new_uuid_hex(),
            field="full_name",
            original_value=full_name,
            canonical_value=None,
            source=src_meta,
            method="json_parsing",
            semantic_rule=None,
            confidence=0.0,
            timestamp_utc=datetime.now(UTC),
            transformation_ref=tr_name.record_id,
        )
        fes.append(fe_name)
        trs.append(tr_name)

        tr_em = make_tr("emails", raw_mail)
        fe_em = FieldEvidence(
            evidence_id=new_uuid_hex(),
            field="emails",
            original_value=raw_mail,
            canonical_value=None,
            source=src_meta,
            method="json_parsing",
            semantic_rule=None,
            confidence=0.0,
            timestamp_utc=datetime.now(UTC),
            transformation_ref=tr_em.record_id,
        )
        fes.append(fe_em)
        trs.append(tr_em)

        tr_ph = make_tr("phones", raw_phone)
        fe_ph = FieldEvidence(
            evidence_id=new_uuid_hex(),
            field="phones",
            original_value=raw_phone,
            canonical_value=None,
            source=src_meta,
            method="json_parsing",
            semantic_rule=None,
            confidence=0.0,
            timestamp_utc=datetime.now(UTC),
            transformation_ref=tr_ph.record_id,
        )
        fes.append(fe_ph)
        trs.append(tr_ph)

        tr_loc = make_tr("location", location.raw)
        fe_loc = FieldEvidence(
            evidence_id=new_uuid_hex(),
            field="location",
            original_value=location.raw,
            canonical_value=None,
            source=src_meta,
            method="json_parsing",
            semantic_rule=None,
            confidence=0.0,
            timestamp_utc=datetime.now(UTC),
            transformation_ref=tr_loc.record_id,
        )
        fes.append(fe_loc)
        trs.append(tr_loc)

        fragment = CandidateFragment(
            fragment_id=new_uuid_hex(),
            external_candidate_id=deterministic_candidate_id(full_name or "", str(raw_input.get("id", ""))),
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
