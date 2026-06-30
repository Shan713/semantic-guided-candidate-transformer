from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from src.interfaces.base_confidence_engine import BaseConfidenceEngine
from src.models.domain_models import (
    CanonicalCandidate,
    ConfidenceBreakdown,
    ConfidenceRecord,
    FieldConfidence,
    OverallConfidence,
    SemanticCandidateFragment,
)
from src.models.enums import SemanticResolutionStage, SourceType
from src.transformation.config import load_transformation_config_bundle


class ConfidenceEngine(BaseConfidenceEngine):
    """Deterministic confidence scoring based on configured reliability weights."""

    def __init__(self, config_bundle: dict[str, Any] | None = None) -> None:
        self.config_bundle = config_bundle or load_transformation_config_bundle()
        self.confidence_config = self.config_bundle.get("confidence", {})
        self.source_reliability_config = self.config_bundle.get("source_reliability", {})
        self.scorer_version = self.confidence_config.get("version", "1.0")
        self.stage_scores = {
            SemanticResolutionStage.EXACT_ALIAS_MATCH: 1.0,
            SemanticResolutionStage.CANONICAL_MATCH: 0.90,
            SemanticResolutionStage.PARENT_CATEGORY_RESOLUTION: 0.75,
            SemanticResolutionStage.ENTITY_LINKING: 0.70,
            SemanticResolutionStage.DETERMINISTIC_FUZZY_MATCH: 0.55,
            SemanticResolutionStage.UNKNOWN_VALUE: 0.20,
        }

    def score(self, candidate: CanonicalCandidate, context) -> CanonicalCandidate:
        field_confidences: list[FieldConfidence] = []
        confidence_records: list[ConfidenceRecord] = []

        for field_name in self._field_order():
            field_confidence = self._score_field(candidate, field_name)
            field_confidences.append(field_confidence)
            confidence_records.append(
                ConfidenceRecord(
                    field=field_confidence.field,
                    score=field_confidence.score,
                    breakdown=field_confidence.breakdown,
                    computed_at_utc=field_confidence.computed_at_utc,
                    scorer_version=field_confidence.scorer_version,
                )
            )

        overall_breakdown = self._combine_breakdowns(field_confidences)
        overall_score = self._combine_scores(field_confidences)
        overall_confidence = OverallConfidence(
            score=overall_score,
            breakdown=overall_breakdown,
            field_confidences=field_confidences,
            computed_at_utc=datetime.now(UTC),
            scorer_version=self.scorer_version,
        )

        return candidate.model_copy(
            update={
                "confidence_records": confidence_records,
                "overall_confidence_internal": overall_confidence.score,
            }
        )

    def _field_order(self) -> list[str]:
        return [
            "full_name",
            "emails",
            "phones",
            "location",
            "links",
            "headline",
            "years_experience",
            "skills",
            "experience",
            "education",
        ]

    def _score_field(self, candidate: CanonicalCandidate, field_name: str) -> FieldConfidence:
        evidence, sources, transformations, values = self._field_support(candidate, field_name)
        source_base, source_adjusted, override_applied = self._source_reliability(evidence, sources, field_name)
        cross_source_agreement = self._cross_source_agreement(sources)
        extraction_quality = self._average_extraction_quality(evidence)
        semantic_certainty, semantic_reason = self._semantic_certainty(transformations, field_name, values)
        conflict_penalty = self._conflict_penalty(values)
        missing_penalty = self._missing_penalty(candidate, field_name, values)

        weights = self.confidence_config.get("score_components", {})
        source_weight = float(weights.get("source_reliability_weight", 0.30))
        cross_weight = float(weights.get("cross_source_agreement_weight", 0.25))
        extraction_weight = float(weights.get("extraction_quality_weight", 0.20))
        semantic_weight = float(weights.get("semantic_certainty_weight", 0.20))
        conflict_weight = float(weights.get("conflict_penalty_weight", 0.05))
        missing_weight = float(weights.get("missing_value_penalty_weight", 0.10))

        positive_total = source_weight + cross_weight + extraction_weight + semantic_weight
        positive_score = (
            (source_adjusted * source_weight)
            + (cross_source_agreement * cross_weight)
            + (extraction_quality * extraction_weight)
            + (semantic_certainty * semantic_weight)
        ) / positive_total if positive_total else 0.0
        score = positive_score - (conflict_penalty * conflict_weight) - (missing_penalty * missing_weight)
        score = self._clamp(score)

        reason_codes = self._reason_codes(
            source_adjusted=source_adjusted,
            override_applied=override_applied,
            cross_source_agreement=cross_source_agreement,
            extraction_quality=extraction_quality,
            semantic_reason=semantic_reason,
            conflict_penalty=conflict_penalty,
            missing_penalty=missing_penalty,
        )

        breakdown = ConfidenceBreakdown(
            source_reliability=self._clamp(source_adjusted),
            source_reliability_base=self._clamp(source_base),
            source_reliability_field_adjusted=self._clamp(source_adjusted),
            reliability_override_applied=override_applied,
            cross_source_agreement=self._clamp(cross_source_agreement),
            extraction_quality=self._clamp(extraction_quality),
            semantic_certainty=self._clamp(semantic_certainty),
            conflict_penalty=self._clamp(conflict_penalty),
            llm_penalty=None,
            notes=reason_codes,
        )

        return FieldConfidence(
            field=field_name,
            score=score,
            breakdown=breakdown,
            computed_at_utc=datetime.now(UTC),
            scorer_version=self.scorer_version,
            reason_codes=reason_codes,
            source_count=len(sources),
        )

    def _field_support(
        self,
        candidate: CanonicalCandidate,
        field_name: str,
    ) -> tuple[list[Any], list[str], list[Any], list[Any]]:
        evidence = []
        sources: list[str] = []
        transformations = []
        values = []

        field_aliases = {
            "full_name": {"full_name"},
            "emails": {"emails", "email"},
            "phones": {"phones", "phone"},
            "location": {"location", "country", "city"},
            "links": {"links"},
            "headline": {"headline"},
            "years_experience": {"years_experience"},
            "skills": {"skills"},
            "experience": {"experience", "company", "job_title"},
            "education": {"education", "degree"},
        }

        aliases = field_aliases.get(field_name, {field_name})
        for item in candidate.field_evidence:
            if item.field in aliases:
                evidence.append(item)
                if item.source:
                    source_name = item.source.source_name
                    sources.append(source_name.value if hasattr(source_name, "value") else str(source_name))
                if item.canonical_value is not None:
                    values.append(item.canonical_value)
                elif item.original_value is not None:
                    values.append(item.original_value)

        if field_name in {"experience", "education", "skills", "location"}:
            for item in getattr(candidate, field_name, []):
                for evidence_id in getattr(item, "evidence_ids", []):
                    evidence_item = next((ev for ev in candidate.field_evidence if ev.evidence_id == evidence_id), None)
                    if evidence_item:
                        evidence.append(evidence_item)
                        if evidence_item.source:
                            source_name = evidence_item.source.source_name
                            sources.append(source_name.value if hasattr(source_name, "value") else str(source_name))
                values.append(item)

        for record in candidate.transformation_history:
            if record.field in aliases or record.field == field_name:
                transformations.append(record)

        if not sources and candidate.source_summaries:
            for source in candidate.source_summaries:
                source_name = source.source_name
                sources.append(source_name.value if hasattr(source_name, "value") else str(source_name))

        return evidence, self._dedupe_keep_order(sources), transformations, values

    def _source_reliability(self, evidence: list[Any], sources: list[str], field_name: str) -> tuple[float, float, bool]:
        if not sources:
            return 0.5, 0.5, False

        reliabilities = self.source_reliability_config.get("reliability", {})
        overrides = self.source_reliability_config.get("field_overrides", {})

        base_scores = [float(reliabilities.get(source, 0.5)) for source in sources]
        base = sum(base_scores) / len(base_scores)
        override_scores = []
        override_applied = False
        for source in sources:
            source_overrides = overrides.get(source, {})
            if field_name in source_overrides:
                override_scores.append(float(source_overrides[field_name]))
                override_applied = True
        adjusted = sum(override_scores) / len(override_scores) if override_scores else base
        return base, adjusted, override_applied

    def _cross_source_agreement(self, sources: list[str]) -> float:
        unique_sources = len(set(sources))
        if unique_sources == 0:
            return 0.0
        return unique_sources / (unique_sources + 1.0)

    def _average_extraction_quality(self, evidence: list[Any]) -> float:
        qualities = [float(item.source.extraction_quality) for item in evidence if getattr(item, "source", None)]
        if not qualities:
            return 0.5
        return sum(qualities) / len(qualities)

    def _semantic_certainty(self, transformations: list[Any], field_name: str, values: list[Any]) -> tuple[float, str]:
        if not transformations:
            return (1.0 if values else 0.0), "no_semantic_transformation"
        scores = []
        reasons = []
        for record in transformations:
            scores.append(self.stage_scores.get(record.resolution_stage, 0.0))
            reasons.append(record.resolution_stage.value)
        return (sum(scores) / len(scores) if scores else 0.0), ",".join(self._dedupe_keep_order(reasons))

    def _conflict_penalty(self, values: list[Any]) -> float:
        normalized = [self._stringify(value) for value in values if self._stringify(value)]
        unique_count = len(set(normalized))
        if unique_count <= 1:
            return 0.0
        return (unique_count - 1) / unique_count

    def _missing_penalty(self, candidate: CanonicalCandidate, field_name: str, values: list[Any]) -> float:
        if values:
            return 0.0
        required_fields = {"full_name", "emails", "phones", "skills"}
        if field_name in required_fields:
            return 1.0
        if field_name in {"experience", "education"} and getattr(candidate, field_name):
            return 0.0
        return 0.5

    def _combine_breakdowns(self, field_confidences: list[FieldConfidence]) -> ConfidenceBreakdown:
        if not field_confidences:
            return ConfidenceBreakdown(
                source_reliability=0.0,
                source_reliability_base=0.0,
                source_reliability_field_adjusted=0.0,
                reliability_override_applied=False,
                cross_source_agreement=0.0,
                extraction_quality=0.0,
                semantic_certainty=0.0,
                conflict_penalty=0.0,
                llm_penalty=None,
                notes=["missing_evidence"],
            )
        source_reliability = sum(item.breakdown.source_reliability for item in field_confidences) / len(field_confidences)
        source_reliability_base = sum(item.breakdown.source_reliability_base for item in field_confidences) / len(field_confidences)
        source_reliability_field_adjusted = sum(item.breakdown.source_reliability_field_adjusted for item in field_confidences) / len(field_confidences)
        cross_source_agreement = sum(item.breakdown.cross_source_agreement for item in field_confidences) / len(field_confidences)
        extraction_quality = sum(item.breakdown.extraction_quality for item in field_confidences) / len(field_confidences)
        semantic_certainty = sum(item.breakdown.semantic_certainty for item in field_confidences) / len(field_confidences)
        conflict_penalty = sum(item.breakdown.conflict_penalty for item in field_confidences) / len(field_confidences)
        notes = []
        for item in field_confidences:
            notes.extend(item.breakdown.notes)
        return ConfidenceBreakdown(
            source_reliability=source_reliability,
            source_reliability_base=source_reliability_base,
            source_reliability_field_adjusted=source_reliability_field_adjusted,
            reliability_override_applied=any(item.breakdown.reliability_override_applied for item in field_confidences),
            cross_source_agreement=cross_source_agreement,
            extraction_quality=extraction_quality,
            semantic_certainty=semantic_certainty,
            conflict_penalty=conflict_penalty,
            llm_penalty=None,
            notes=self._dedupe_keep_order(notes),
        )

    def _combine_scores(self, field_confidences: list[FieldConfidence]) -> float:
        if not field_confidences:
            return 0.0
        return sum(item.score for item in field_confidences) / len(field_confidences)

    def _reason_codes(
        self,
        *,
        source_adjusted: float,
        override_applied: bool,
        cross_source_agreement: float,
        extraction_quality: float,
        semantic_reason: str,
        conflict_penalty: float,
        missing_penalty: float,
    ) -> list[str]:
        reason_codes = []
        reason_map = self.confidence_config.get("reason_codes", [])
        if source_adjusted >= 0.8 and "high_source_reliability" in reason_map:
            reason_codes.append("high_source_reliability")
        if override_applied and "field_reliability_override" in reason_map:
            reason_codes.append("field_reliability_override")
        if cross_source_agreement >= 0.66 and "strong_cross_source_agreement" in reason_map:
            reason_codes.append("strong_cross_source_agreement")
        elif "weak_cross_source_agreement" in reason_map:
            reason_codes.append("weak_cross_source_agreement")
        if extraction_quality >= 0.8 and "high_extraction_quality" in reason_map:
            reason_codes.append("high_extraction_quality")
        if semantic_reason and "semantic_alias_match" in reason_map and "exact_alias_match" in semantic_reason:
            reason_codes.append("semantic_alias_match")
        if semantic_reason and "semantic_fuzzy_match" in reason_map and "deterministic_fuzzy_match" in semantic_reason:
            reason_codes.append("semantic_fuzzy_match")
        if conflict_penalty > 0 and "unresolved_conflict" in reason_map:
            reason_codes.append("unresolved_conflict")
        if missing_penalty > 0 and "missing_evidence" in reason_map:
            reason_codes.append("missing_evidence")
        return self._dedupe_keep_order(reason_codes)

    def _stringify(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return str(value)

    def _dedupe_keep_order(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, value))
