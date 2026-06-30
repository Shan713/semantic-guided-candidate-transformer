from __future__ import annotations

from src.models.domain_models import CanonicalCandidate, DecisionTrace, FieldEvidence, MergeDecision, ProvenanceRecord, TransformationRecord


class EvidenceAggregationEngine:
    """Ensures merged evidence remains attached to the canonical candidate."""

    def aggregate(self, candidate: CanonicalCandidate) -> CanonicalCandidate:
        provenance = list(candidate.provenance)
        for evidence in candidate.field_evidence:
            if evidence.provenance_ref is None:
                evidence.provenance_ref = evidence.evidence_id
            provenance.append(
                ProvenanceRecord(
                    field=evidence.field,
                    original_value=evidence.original_value,
                    canonical_value=evidence.canonical_value,
                    source=evidence.source.source_name.value if evidence.source else "unknown",
                    method=evidence.method,
                    timestamp_utc=evidence.timestamp_utc,
                    transformation_rule=evidence.semantic_rule,
                    confidence=evidence.confidence,
                    source_record_id=evidence.source.source_record_id if evidence.source else None,
                )
            )

        for decision in candidate.merge_decisions:
            provenance.append(
                ProvenanceRecord(
                    field=decision.field,
                    original_value=decision.competing_values,
                    canonical_value=decision.selected_value,
                    source="merge_engine",
                    method=decision.strategy,
                    timestamp_utc=decision.timestamp_utc,
                    transformation_rule=decision.strategy,
                    confidence=decision.confidence,
                    source_record_id=decision.decision_id,
                )
            )

        return candidate.model_copy(update={"provenance": provenance})
