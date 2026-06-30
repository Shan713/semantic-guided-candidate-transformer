from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from src.interfaces.base_provenance_engine import BaseProvenanceEngine
from src.models.domain_models import CanonicalCandidate, ProvenanceRecord


class ProvenanceEngine(BaseProvenanceEngine):
    """Materialize field-level provenance for the canonical candidate."""

    def enrich(self, candidate: CanonicalCandidate, context: Any) -> CanonicalCandidate:
        provenance = list(candidate.provenance)
        provenance.extend(self._from_field_evidence(candidate))
        provenance.extend(self._from_merge_decisions(candidate))
        provenance = self._dedupe_provenance(provenance)
        return candidate.model_copy(update={"provenance": provenance})

    def _from_field_evidence(self, candidate: CanonicalCandidate) -> list[ProvenanceRecord]:
        records: list[ProvenanceRecord] = []
        for evidence in candidate.field_evidence:
            source = evidence.source.source_name.value if hasattr(evidence.source.source_name, "value") else str(evidence.source.source_name)
            records.append(
                ProvenanceRecord(
                    field=evidence.field,
                    original_value=evidence.original_value,
                    canonical_value=evidence.canonical_value,
                    source=source,
                    method=evidence.method,
                    timestamp_utc=evidence.timestamp_utc,
                    transformation_rule=evidence.semantic_rule or evidence.transformation_ref or "extraction",
                    confidence=evidence.confidence,
                    source_record_id=evidence.source.source_record_id,
                )
            )
        return records

    def _from_merge_decisions(self, candidate: CanonicalCandidate) -> list[ProvenanceRecord]:
        records: list[ProvenanceRecord] = []
        for decision in candidate.merge_decisions:
            records.append(
                ProvenanceRecord(
                    field=decision.field,
                    original_value=decision.competing_values,
                    canonical_value=decision.selected_value,
                    source="fusion",
                    method="merge",
                    timestamp_utc=decision.timestamp_utc,
                    transformation_rule=decision.strategy,
                    confidence=decision.confidence,
                    source_record_id=None,
                )
            )
        return records

    def _dedupe_provenance(self, records: list[ProvenanceRecord]) -> list[ProvenanceRecord]:
        ordered: dict[tuple[Any, Any, Any, Any, Any], ProvenanceRecord] = {}
        for record in records:
            key = (record.field, record.source, record.method, self._stringify(record.original_value), self._stringify(record.canonical_value))
            ordered[key] = record
        return list(ordered.values())

    def _stringify(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)
