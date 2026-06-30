"""Resume DOCX adapter: extracts raw text and performs token extraction deterministically."""
from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Any

from docx import Document

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
from src.utils.extractors import (
    extract_emails,
    extract_phones,
    extract_links,
    extract_name,
    extract_sections,
)
from src.utils.ids import new_uuid_hex, deterministic_candidate_id
from src.utils.hashing import sha256_text
from src.utils.normalizers import normalize_email, normalize_phone, normalize_whitespace
from src.models.domain_models import TransformationRecord, DecisionTrace
from src.models.enums import SemanticResolutionStage, ResolverType, EntityDomain
from datetime import datetime, UTC

logger = logging.getLogger("sgct.adapters.resume_docx")


class ResumeDOCXAdapter(BaseAdapter):
    def adapt(self, raw_input: str | bytes, context) -> CandidateFragment:
        text = ""
        try:
            if isinstance(raw_input, (bytes, bytearray)):
                # python-docx does not support loading from bytes directly; expect a path in practice
                logger.warning("DOCX adapter received bytes; expecting file path. Returning empty text.")
                text = ""
            else:
                doc = Document(raw_input)
                paragraphs = [p.text for p in doc.paragraphs]
                text = "\n".join(paragraphs)
        except Exception as e:
            logger.warning("Failed to open DOCX: %s", e)
            text = ""

        src_meta = SourceMetadata(
            source_name="resume_docx",
            source_record_id=sha256_text(str(raw_input))[:12],
            source_file=str(raw_input) if isinstance(raw_input, str) else "bytes",
            ingested_at_utc=datetime.now(UTC),
            extractor_name="resume_docx_adapter",
            extractor_version="1.0",
            extraction_quality=0.8,
            raw_reference_hash=sha256_text(text),
        )

        name = extract_name(text)
        emails = [Email(value=e, normalized=normalize_email(e), confidence=0.0) for e in extract_emails(text)]
        phones = []
        for p in extract_phones(text):
            phones.append(Phone(raw=p, normalized_e164=normalize_phone(p), confidence=0.0))

        links = Links()
        for l in extract_links(text):
            if "linkedin.com" in l:
                links.linkedin = l
            elif "github.com" in l:
                links.github = l
            else:
                links.other.append(l)

        sections = extract_sections(text)
        location = Location(raw=None, confidence=0.0)
        if "location" in sections:
            location.raw = sections["location"]

        # per-field transformation records and evidence
        def make_tr(field_name: str, original_val: object) -> TransformationRecord:
            return TransformationRecord(
                record_id=new_uuid_hex(),
                field=field_name,
                original_value=original_val,
                canonical_value=None,
                resolver=ResolverType.ONTOLOGY_LOADER.value,
                rule_name="docx_extraction",
                ontology_domain="",
                matched_alias=None,
                semantic_confidence=0.0,
                resolution_stage=SemanticResolutionStage.UNKNOWN_VALUE,
                related_to_applied=[],
                timestamp_utc=datetime.now(UTC),
            )

        fes = []
        trs = []

        tr_text = make_tr("docx_text", text)
        fe_text = FieldEvidence(
            evidence_id=new_uuid_hex(),
            field="docx_text",
            original_value=text,
            canonical_value=None,
            source=src_meta,
            method="docx_text_extraction",
            semantic_rule=None,
            confidence=0.0,
            timestamp_utc=datetime.now(UTC),
            transformation_ref=tr_text.record_id,
        )
        fes.append(fe_text)
        trs.append(tr_text)

        tr_name = make_tr("full_name", name)
        fe_name = FieldEvidence(
            evidence_id=new_uuid_hex(),
            field="full_name",
            original_value=name,
            canonical_value=None,
            source=src_meta,
            method="docx_text_extraction",
            semantic_rule=None,
            confidence=0.0,
            timestamp_utc=datetime.now(UTC),
            transformation_ref=tr_name.record_id,
        )
        fes.append(fe_name)
        trs.append(tr_name)

        fragment = CandidateFragment(
            fragment_id=new_uuid_hex(),
            external_candidate_id=deterministic_candidate_id(name or "", "docx"),
            source_metadata=src_meta,
            full_name=normalize_whitespace(name),
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
