from __future__ import annotations

from datetime import datetime, UTC
from typing import Iterable

from src.models.domain_models import CanonicalCandidate, ConfidenceRecord, DecisionTrace, FieldEvidence, MergeDecision, ProvenanceRecord, RuntimeMetadata, SourceMetadata, TransformationRecord
from src.utils.hashing import sha256_text
from src.utils.ids import deterministic_candidate_id


class CanonicalCandidateBuilder:
    """Builds and freezes the final canonical candidate."""

    def build(
        self,
        candidate_id_seed: str,
        full_name: str | None,
        emails,
        phones,
        location,
        links,
        headline,
        years_experience,
        skills,
        experience,
        education,
        field_evidence: list[FieldEvidence],
        provenance: list[ProvenanceRecord],
        confidence_records: list[ConfidenceRecord],
        transformation_history: list[TransformationRecord],
        merge_decisions: list[MergeDecision],
        decision_trace: list[DecisionTrace],
        source_summaries: list[SourceMetadata],
        overall_confidence_internal: float,
    ) -> CanonicalCandidate:
        candidate_id = deterministic_candidate_id(candidate_id_seed, sha256_text("|".join([candidate_id_seed, full_name or ""])))
        return CanonicalCandidate(
            candidate_id=candidate_id,
            full_name=full_name,
            emails=emails,
            phones=phones,
            location=location,
            links=links,
            headline=headline,
            years_experience=years_experience,
            skills=skills,
            experience=experience,
            education=education,
            field_evidence=field_evidence,
            provenance=provenance,
            confidence_records=confidence_records,
            transformation_history=transformation_history,
            merge_decisions=merge_decisions,
            decision_trace=decision_trace,
            source_summaries=source_summaries,
            overall_confidence_internal=overall_confidence_internal,
            finalized_at_utc=datetime.now(UTC),
        )
