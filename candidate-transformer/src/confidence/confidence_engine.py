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
    """Deterministic confidence scoring with category-aware weighting.

    Overall confidence is computed from six weighted categories rather than a
    simple average over fields, so identity fields (name, email, phone) carry
    more weight than headline or links.

    Category weights (configurable via confidence.yml):
        identity   (full_name, emails, phones)  → 30%
        experience (experience)                 → 25%
        skills     (skills)                     → 20%
        education  (education)                  → 15%
        location   (location)                   →  5%
        context    (headline, links, yoe)       →  5%
    """

    # ------------------------------------------------------------------
    # Category definitions
    # ------------------------------------------------------------------
    _CATEGORIES: dict[str, list[str]] = {
        "identity": ["full_name", "emails", "phones"],
        "experience": ["experience"],
        "skills": ["skills"],
        "education": ["education"],
        "location": ["location"],
        "context": ["headline", "links", "years_experience"],
    }

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

    def debug_summary(self, candidate: CanonicalCandidate) -> str:
        """Return a human-readable confidence breakdown (Part 2: explainability).

        Produces output like::

            --------------------------------
            Identity                    0.92
            Experience                  0.83
            Education                   0.91
            Skills                      0.79
            Location                    0.85
            Context (headline/links)    0.72
            --------------------------------
            Overall                     0.84

            Boosts
            • Email matched across Resume ATS Recruiter
            • Phone matched across Resume ATS Recruiter
            • 3 sources agree on education

            Penalties
            • Experience present in 1 source only
            • Skills from 1 source only
        """
        field_confidences: list[FieldConfidence] = []
        for field_name in self._field_order():
            field_confidences.append(self._score_field(candidate, field_name))

        category_scores = self._category_scores(field_confidences)
        overall = self._combine_scores(field_confidences)
        boosts, penalties = self._collect_boost_penalties(field_confidences)

        lines = ["--------------------------------"]
        for cat_name in self._CATEGORIES:
            cat_score = category_scores.get(cat_name, 0.0)
            label = _CATEGORY_LABELS.get(cat_name, cat_name)
            lines.append(f"{label:<30} {cat_score:.2f}")
        lines.append("--------------------------------")
        lines.append(f"{'Overall':<30} {overall:.2f}")
        if boosts:
            lines.append("")
            lines.append("Boosts")
            for b in boosts:
                lines.append(f"  • {b}")
        if penalties:
            lines.append("")
            lines.append("Penalties")
            for p in penalties:
                lines.append(f"  • {p}")
        lines.append("--------------------------------")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Field-level scoring
    # ------------------------------------------------------------------

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
        conflict_penalty = self._conflict_penalty(values, field_name)
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
        """Score how many independent sources agree on this field.

        The formula rewards additional confirming sources with diminishing
        returns, bounded by [0, 1].  A single source yields 0.5; two sources
        yield 0.75; three yield 0.875; asymptotically approaching 1.0.

        This is more generous than the previous ``n / (n+1)`` for n>=2
        while remaining principled and explainable.
        """
        unique_sources = len(set(sources))
        if unique_sources == 0:
            return 0.0
        # 1 - 1/2^n  →  n=1:0.5  n=2:0.75  n=3:0.875  n=4:0.9375
        return 1.0 - (1.0 / (2.0 ** unique_sources))

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

    _SCALAR_CONFLICT_FIELDS = frozenset({"full_name", "headline", "years_experience", "location"})

    def _conflict_penalty(self, values: list[Any], field_name: str = "") -> float:
        """Penalize genuine disagreement in scalar fields.

        For list-type fields (emails, phones, skills, experience, education),
        multiple unique values are expected (different positions, skills, etc.)
        and do NOT represent conflicts.  Conflict penalty only applies to
        scalar fields where multiple distinct values indicate disagreement.

        The penalty increases progressively with more conflicting values:
        - 2 conflicting values → 0.50 penalty
        - 3 conflicting values → 0.67 penalty
        - 4 conflicting values → 0.75 penalty

        This ensures conflicts produce a larger reduction than simple absence
        (missing = 0.25 max), as the user requested.
        """
        if field_name not in self._SCALAR_CONFLICT_FIELDS:
            return 0.0
        normalized = [self._stringify(value) for value in values if self._stringify(value)]
        unique_count = len(set(normalized))
        if unique_count <= 1:
            return 0.0
        return (unique_count - 1) / unique_count

    def _missing_penalty(self, candidate: CanonicalCandidate, field_name: str, values: list[Any]) -> float:
        """Small reduction for missing values — simple absence is NOT conflict.

        Required fields (full_name, emails, phones, skills) incur a mild 0.25
        penalty when absent.  Non-required fields incur only 0.10.  Fields
        with data incur no penalty.

        These are deliberately small because missing data does not imply the
        candidate is less qualified — only that the source didn't provide it.
        """
        if values:
            return 0.0
        required_fields = {"full_name", "emails", "phones", "skills"}
        if field_name in required_fields:
            return 0.25
        if field_name in {"experience", "education"} and getattr(candidate, field_name):
            return 0.0
        return 0.10

    # ------------------------------------------------------------------
    # Overall score combination (category-aware)
    # ------------------------------------------------------------------

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
        """Combine field-level confidences using category-aware weighting.

        Step 1 — compute per-category scores (average of fields in that category).
        Step 2 — weighted average of categories using configured category weights.

        Falls back to source-count-weighted average if no category weights are
        configured.
        """
        if not field_confidences:
            return 0.0

        cat_weights = self.confidence_config.get("category_weights", {})
        if not cat_weights:
            # Fallback: source-count-weighted average (legacy behavior)
            total_weight = sum(max(item.source_count, 1) for item in field_confidences)
            if total_weight == 0:
                return sum(item.score for item in field_confidences) / len(field_confidences)
            weighted = sum(
                item.score * max(item.source_count, 1) for item in field_confidences
            ) / total_weight
            return self._apply_caps(weighted, field_confidences)

        # Category-aware weighted average
        category_scores = self._category_scores(field_confidences)
        total_weight = 0.0
        weighted_sum = 0.0
        for cat_name, weight in cat_weights.items():
            cat_weight = float(weight)
            cat_score = category_scores.get(cat_name)
            if cat_score is not None:
                weighted_sum += cat_score * cat_weight
                total_weight += cat_weight

        if total_weight == 0:
            return sum(item.score for item in field_confidences) / len(field_confidences)

        weighted = weighted_sum / total_weight
        return self._apply_caps(weighted, field_confidences)

    def _apply_caps(self, weighted: float, field_confidences: list[FieldConfidence]) -> float:
        """Apply configured caps to the overall score."""
        caps = self.confidence_config.get("caps", {})
        single_source_max = caps.get("single_source_max")
        unresolved_conflict_max = caps.get("unresolved_conflict_max")
        if single_source_max is not None:
            max_sources = max((item.source_count for item in field_confidences), default=0)
            if max_sources <= 1:
                weighted = min(weighted, float(single_source_max))
        if unresolved_conflict_max is not None and weighted > float(unresolved_conflict_max):
            fields_with_conflict = sum(
                1 for item in field_confidences if item.breakdown.conflict_penalty > 0
            )
            total_fields = len(field_confidences)
            if total_fields > 0 and fields_with_conflict / total_fields >= 0.5:
                weighted = min(weighted, float(unresolved_conflict_max))
        return weighted

    def _category_scores(self, field_confidences: list[FieldConfidence]) -> dict[str, float]:
        """Compute per-category scores by averaging fields within each category."""
        field_map: dict[str, FieldConfidence] = {fc.field: fc for fc in field_confidences}
        category_scores: dict[str, float] = {}
        for cat_name, fields in self._CATEGORIES.items():
            cat_fields = [field_map[f] for f in fields if f in field_map]
            if cat_fields:
                # Weight by source_count within category
                total_weight = sum(max(fc.source_count, 1) for fc in cat_fields)
                if total_weight > 0:
                    category_scores[cat_name] = sum(
                        fc.score * max(fc.source_count, 1) for fc in cat_fields
                    ) / total_weight
                else:
                    category_scores[cat_name] = sum(fc.score for fc in cat_fields) / len(cat_fields)
        return category_scores

    # ------------------------------------------------------------------
    # Explainability helpers (Part 2 — debug mode)
    # ------------------------------------------------------------------

    def _collect_boost_penalties(
        self, field_confidences: list[FieldConfidence]
    ) -> tuple[list[str], list[str]]:
        """Analyze field confidences and produce human-readable boost/penalty summaries."""
        boosts: list[str] = []
        penalties: list[str] = []

        for fc in field_confidences:
            field_label = _FIELD_LABELS.get(fc.field, fc.field)
            bd = fc.breakdown

            # Boosts
            if bd.cross_source_agreement >= 0.875 and fc.source_count >= 3:
                boosts.append(f"{field_label} matched across {fc.source_count} sources")
            elif bd.cross_source_agreement >= 0.75 and fc.source_count >= 2:
                boosts.append(f"{field_label} matched across {fc.source_count} sources")
            if bd.semantic_certainty >= 0.90 and fc.source_count > 0:
                boosts.append(f"{field_label} semantically resolved with high certainty")
            if bd.source_reliability >= 0.85:
                boosts.append(f"{field_label} from high-reliability source")
            if bd.extraction_quality >= 0.85:
                boosts.append(f"{field_label} extracted with high quality")

            # Penalties
            if bd.conflict_penalty > 0:
                penalties.append(f"{field_label} has conflicting values across sources")
            if fc.source_count == 1 and bd.cross_source_agreement <= 0.5:
                penalties.append(f"{field_label} present in 1 source only")
            if fc.source_count == 0:
                penalties.append(f"{field_label} missing from all sources")
            if bd.semantic_certainty <= 0.55 and bd.semantic_certainty > 0:
                penalties.append(f"{field_label} resolved via fuzzy match (lower certainty)")

        return boosts, penalties

    # ------------------------------------------------------------------
    # Reason codes
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Human-readable labels for debug output
# ------------------------------------------------------------------

_CATEGORY_LABELS: dict[str, str] = {
    "identity": "Identity (Name/Email/Phone)",
    "experience": "Experience",
    "skills": "Skills",
    "education": "Education",
    "location": "Location",
    "context": "Context (Headline/Links)",
}

_FIELD_LABELS: dict[str, str] = {
    "full_name": "Full Name",
    "emails": "Email",
    "phones": "Phone",
    "location": "Location",
    "links": "Links",
    "headline": "Headline",
    "years_experience": "Years Experience",
    "skills": "Skills",
    "experience": "Experience",
    "education": "Education",
}
