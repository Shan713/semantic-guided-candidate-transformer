from __future__ import annotations

from collections import OrderedDict
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
        grouped: OrderedDict[tuple[Any, Any, Any, Any], dict[str, Any]] = OrderedDict()
        for record in records:
            key = (record.field, record.source, record.method, record.transformation_rule)
            bucket = grouped.setdefault(
                key,
                {
                    "template": record,
                    "original_values": [],
                    "canonical_values": [],
                    "source_record_ids": [],
                    "timestamps": [],
                    "confidences": [],
                },
            )
            bucket["original_values"].append(record.original_value)
            bucket["canonical_values"].append(record.canonical_value)
            bucket["timestamps"].append(record.timestamp_utc)
            if record.source_record_id:
                bucket["source_record_ids"].append(record.source_record_id)
            if record.confidence is not None:
                bucket["confidences"].append(record.confidence)

        compacted: list[ProvenanceRecord] = []
        for bucket in grouped.values():
            template: ProvenanceRecord = bucket["template"]
            original_values = self._compact_values(bucket["original_values"])
            canonical_values = self._compact_values(bucket["canonical_values"])
            source_record_ids = self._compact_text(bucket["source_record_ids"])
            timestamps = [stamp for stamp in bucket["timestamps"] if stamp is not None]
            compacted.append(
                ProvenanceRecord(
                    field=template.field,
                    original_value=original_values,
                    canonical_value=canonical_values,
                    source=template.source,
                    method=template.method,
                    timestamp_utc=max(timestamps) if timestamps else template.timestamp_utc,
                    transformation_rule=template.transformation_rule,
                    confidence=max(bucket["confidences"]) if bucket["confidences"] else template.confidence,
                    source_record_id=source_record_ids,
                )
            )
        return compacted

    def _compact_values(self, values: list[Any]) -> Any:
        deduped = []
        seen = set()
        for value in values:
            key = self._stringify(value)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(value)
        if not deduped:
            return None
        if len(deduped) == 1:
            return deduped[0]
        return deduped

    def _compact_text(self, values: list[str]) -> str | None:
        deduped = []
        seen = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        if not deduped:
            return None
        return " | ".join(deduped)

    def _stringify(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)
