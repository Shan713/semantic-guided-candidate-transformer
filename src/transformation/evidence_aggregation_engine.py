from __future__ import annotations

import json
from typing import Any

from src.models.domain_models import CanonicalCandidate, CandidateFragment, FieldEvidence, ProvenanceRecord, TransformationRecord, DecisionTrace, SourceMetadata
from src.utils.normalizers import dedupe_keep_order


class EvidenceAggregationEngine:
    """Aggregate all fragment-level evidence onto the canonical candidate."""

    def aggregate(
        self,
        candidate: CanonicalCandidate,
        fragments: list[CandidateFragment],
        context: Any | None = None,
    ) -> CanonicalCandidate:
        field_evidence = self._unique_by_id([*candidate.field_evidence, *self._collect_field_evidence(fragments)])
        transformation_history = self._unique_transformations([*candidate.transformation_history, *self._collect_transformations(fragments)])
        decision_trace = self._unique_decision_traces([*candidate.decision_trace, *self._collect_decision_traces(fragments)])
        provenance = self._unique_provenance([*candidate.provenance, *self._collect_provenance(fragments)])
        source_summaries = self._unique_source_summaries([*candidate.source_summaries, *self._collect_source_summaries(fragments)])

        return candidate.model_copy(
            update={
                "field_evidence": field_evidence,
                "transformation_history": transformation_history,
                "decision_trace": decision_trace,
                "provenance": provenance,
                "source_summaries": source_summaries,
            }
        )

    def _collect_field_evidence(self, fragments: list[CandidateFragment]) -> list[FieldEvidence]:
        collected: list[FieldEvidence] = []
        for fragment in fragments:
            collected.extend(fragment.field_evidence)
        return collected

    def _collect_transformations(self, fragments: list[CandidateFragment]) -> list[TransformationRecord]:
        collected: list[TransformationRecord] = []
        for fragment in fragments:
            collected.extend(fragment.transformation_history)
        return collected

    def _collect_decision_traces(self, fragments: list[CandidateFragment]) -> list[DecisionTrace]:
        collected: list[DecisionTrace] = []
        for fragment in fragments:
            collected.extend(fragment.decision_trace)
        return collected

    def _collect_provenance(self, fragments: list[CandidateFragment]) -> list[ProvenanceRecord]:
        collected: list[ProvenanceRecord] = []
        for fragment in fragments:
            collected.extend(fragment.provenance)
        return collected

    def _collect_source_summaries(self, fragments: list[CandidateFragment]) -> list[SourceMetadata]:
        collected: list[SourceMetadata] = []
        for fragment in fragments:
            if fragment.source_metadata:
                collected.append(fragment.source_metadata)
        return collected

    def _unique_by_id(self, records: list[FieldEvidence]) -> list[FieldEvidence]:
        ordered: dict[str, FieldEvidence] = {}
        for record in records:
            ordered[record.evidence_id] = record
        return list(ordered.values())

    def _unique_transformations(self, records: list[TransformationRecord]) -> list[TransformationRecord]:
        ordered: dict[str, TransformationRecord] = {}
        for record in records:
            ordered[record.record_id] = record
        return list(ordered.values())

    def _unique_decision_traces(self, records: list[DecisionTrace]) -> list[DecisionTrace]:
        ordered: dict[str, DecisionTrace] = {}
        for record in records:
            ordered[record.trace_id] = record
        return list(ordered.values())

    def _unique_provenance(self, records: list[ProvenanceRecord]) -> list[ProvenanceRecord]:
        ordered: dict[tuple[Any, Any, Any, Any], ProvenanceRecord] = {}
        for record in records:
            key = (record.field, record.source, record.method, self._hashable_value(record.original_value))
            ordered[key] = record
        return list(ordered.values())

    def _hashable_value(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True, default=str)
        if isinstance(value, list):
            return json.dumps(value, sort_keys=True, default=str)
        return str(value)

    def _unique_source_summaries(self, records: list[SourceMetadata]) -> list[SourceMetadata]:
        ordered: dict[str, SourceMetadata] = {}
        for record in records:
            key = record.source_record_id or f"{record.source_name.value if hasattr(record.source_name, 'value') else record.source_name}:{record.source_file or ''}"
            ordered[key] = record
        return list(ordered.values())
