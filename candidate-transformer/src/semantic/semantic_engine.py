from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import List

from src.models.domain_models import (
    CandidateFragment,
    TransformationRecord,
    DecisionTrace,
    ProvenanceRecord,
    EntityLinkRecord,
    FieldEvidence,
    Skill,
)
from src.models.enums import (
    EntityDomain,
    SemanticResolutionStage,
    ResolverType,
)
from src.ontology.ontology_registry import OntologyRegistry
from src.utils.ids import new_uuid_hex

logger = logging.getLogger("sgct.semantic.engine")


class SemanticResolutionEngine:
    def __init__(self, registry: OntologyRegistry, fuzzy_threshold: int = 80) -> None:
        self.registry = registry
        self.fuzzy_threshold = fuzzy_threshold

    def resolve_skill(self, value: str, field_evidence: FieldEvidence) -> tuple[Skill, TransformationRecord, DecisionTrace, ProvenanceRecord] | None:
        if not value:
            return None
        original = value
        # 1. exact alias
        ent = self.registry.get_by_alias(EntityDomain.SKILL, value)
        stage = None
        selected = None
        candidates = []
        if ent:
            stage = SemanticResolutionStage.EXACT_ALIAS_MATCH
            selected = ent
            candidates = [ent.canonical_name]
        else:
            # 2. canonical
            ent = self.registry.get_by_canonical(EntityDomain.SKILL, value)
            if ent:
                stage = SemanticResolutionStage.CANONICAL_MATCH
                selected = ent
                candidates = [ent.canonical_name]

        # 3. parent category
        if not selected:
            # try parent category by searching canonical entries where category matches value
            parent = None
            for (doc, key), e in self.registry.state.canonical_index.items():
                if doc != EntityDomain.SKILL.value:
                    continue
                if e.category and e.category.lower() == value.lower():
                    parent = e
                    break
            if parent:
                stage = SemanticResolutionStage.PARENT_CATEGORY_RESOLUTION
                selected = parent
                candidates = [parent.canonical_name]

        # 4. entity linking (related_to)
        if not selected:
            # look for entries where related_to contains the value
            for (doc, key), e in self.registry.state.canonical_index.items():
                if doc != EntityDomain.SKILL.value:
                    continue
                if any(r.lower() == value.lower() for r in e.related_to):
                    stage = SemanticResolutionStage.ENTITY_LINKING
                    selected = e
                    candidates = [e.canonical_name]
                    break

        # 5. fuzzy
        if not selected:
            ent = self.registry.deterministic_fuzzy_match(EntityDomain.SKILL, value, self.fuzzy_threshold)
            if ent:
                stage = SemanticResolutionStage.DETERMINISTIC_FUZZY_MATCH
                selected = ent
                candidates = [ent.canonical_name]

        # 6 unknown
        if not selected:
            stage = SemanticResolutionStage.UNKNOWN_VALUE

        # build records
        tr = TransformationRecord(
            record_id=new_uuid_hex(),
            field="skills",
            original_value=original,
            canonical_value=selected.canonical_name if selected else None,
            resolver=ResolverType.SKILL_CANONICALIZER.value,
            rule_name="semantic_resolution",
            ontology_domain=EntityDomain.SKILL.value,
            matched_alias=None,
            semantic_confidence=1.0 if stage != SemanticResolutionStage.UNKNOWN_VALUE else 0.0,
            resolution_stage=stage,
            related_to_applied=selected.related_to if selected else [],
            timestamp_utc=datetime.now(UTC),
        )

        dt = DecisionTrace(
            trace_id=new_uuid_hex(),
            stage=stage.value,
            field="skills",
            decision_type="resolution",
            candidates_considered=candidates,
            selected_value=selected.canonical_name if selected else None,
            rationale=f"Resolved skill '{original}' -> '{selected.canonical_name if selected else None}'",
            rule_or_policy="ontology_lookup",
            confidence=tr.semantic_confidence,
            resolution_order_step=0,
            fallback_used=(stage != SemanticResolutionStage.EXACT_ALIAS_MATCH and stage != SemanticResolutionStage.CANONICAL_MATCH),
            timestamp_utc=datetime.now(UTC),
        )

        pr = ProvenanceRecord(
            field="skills",
            original_value=original,
            canonical_value=selected.canonical_name if selected else None,
            source=f"{EntityDomain.SKILL.value}_ontology",
            method="ontology_lookup",
            timestamp_utc=datetime.now(UTC),
            transformation_rule="semantic_resolution",
            confidence=tr.semantic_confidence if stage != SemanticResolutionStage.UNKNOWN_VALUE else None,
            source_record_id=None,
        )

        skill = Skill(
            name=selected.canonical_name if selected else original,
            original_names=[original],
            category=selected.category if selected else None,
            parent_category=selected.parent_category if selected else None,
            confidence=tr.semantic_confidence,
            sources=["skill_ontology"],
            evidence_ids=[field_evidence.evidence_id],
        )

        return skill, tr, dt, pr

    def resolve_fragment(self, fragment: CandidateFragment, context) -> CandidateFragment:
        # resolve skills
        new_skills: List[Skill] = []
        for fe in fragment.field_evidence:
            # only process field evidences that mention skills in field name or original_value
            if fe.field and "skill" in fe.field.lower():
                orig = fe.original_value
                if isinstance(orig, str):
                    tokens = [t.strip() for t in orig.split(",") if t.strip()]
                elif isinstance(orig, list):
                    tokens = orig
                else:
                    tokens = []
                for t in tokens:
                    res = self.resolve_skill(t, fe)
                    if res:
                        skill, tr, dt, pr = res
                        new_skills.append(skill)
                        fragment.transformation_history.append(tr)
                        fragment.decision_trace.append(dt)
                        fragment.provenance.append(pr)
                        # update field evidence
                        fe.canonical_value = skill.name
                        fe.resolved_domain = EntityDomain.SKILL
                        fe.resolved_category = skill.category
                        fe.resolved_parent_category = skill.parent_category
        # merge with existing skills
        fragment.skills = new_skills if new_skills else fragment.skills
        # resolve experience companies and titles if present
        for exp in fragment.experience:
            if exp.company:
                ent = self._resolve_generic(EntityDomain.COMPANY, exp.company)
                if ent:
                    tr, dt, pr, canonical = ent
                    fragment.transformation_history.append(tr)
                    fragment.decision_trace.append(dt)
                    fragment.provenance.append(pr)
                    exp.company_canonical = canonical
            if exp.title:
                ent = self._resolve_generic(EntityDomain.JOB_TITLE, exp.title)
                if ent:
                    tr, dt, pr, canonical = ent
                    fragment.transformation_history.append(tr)
                    fragment.decision_trace.append(dt)
                    fragment.provenance.append(pr)
                    exp.title_canonical = canonical

        # resolve education degrees
        for edu in fragment.education:
            if edu.degree:
                ent = self._resolve_generic(EntityDomain.DEGREE, edu.degree)
                if ent:
                    tr, dt, pr, canonical = ent
                    fragment.transformation_history.append(tr)
                    fragment.decision_trace.append(dt)
                    fragment.provenance.append(pr)
                    edu.degree_canonical = canonical

        # resolve location country if present
        if fragment.location and fragment.location.country:
            ent = self._resolve_generic(EntityDomain.COUNTRY, fragment.location.country)
            if ent:
                tr, dt, pr, canonical = ent
                fragment.transformation_history.append(tr)
                fragment.decision_trace.append(dt)
                fragment.provenance.append(pr)
                fragment.location.country_code = canonical
        return fragment

    def _resolve_generic(self, domain: EntityDomain, value: str):
        if not value:
            return None
        original = value
        selected = self.registry.get_by_alias(domain, value) or self.registry.get_by_canonical(domain, value)
        stage = None
        candidates = []
        if selected:
            stage = SemanticResolutionStage.CANONICAL_MATCH if selected.canonical_name.lower() == value.lower() else SemanticResolutionStage.EXACT_ALIAS_MATCH
            candidates = [selected.canonical_name]
        else:
            # fuzzy
            ent = self.registry.deterministic_fuzzy_match(domain, value, self.fuzzy_threshold)
            if ent:
                selected = ent
                stage = SemanticResolutionStage.DETERMINISTIC_FUZZY_MATCH
                candidates = [ent.canonical_name]
        if not selected:
            stage = SemanticResolutionStage.UNKNOWN_VALUE

        tr = TransformationRecord(
            record_id=new_uuid_hex(),
            field=domain.value,
            original_value=original,
            canonical_value=selected.canonical_name if selected else None,
            resolver=ResolverType.SEMANTIC_RESOLUTION_ENGINE.value,
            rule_name="semantic_generic_resolution",
            ontology_domain=domain.value,
            matched_alias=None,
            semantic_confidence=1.0 if stage != SemanticResolutionStage.UNKNOWN_VALUE else 0.0,
            resolution_stage=stage,
            related_to_applied=selected.related_to if selected else [],
            timestamp_utc=datetime.now(UTC),
        )

        dt = DecisionTrace(
            trace_id=new_uuid_hex(),
            stage=stage.value,
            field=domain.value,
            decision_type="resolution",
            candidates_considered=candidates,
            selected_value=selected.canonical_name if selected else None,
            rationale=f"Resolved {domain.value} '{original}' -> '{selected.canonical_name if selected else None}'",
            rule_or_policy="ontology_lookup",
            confidence=tr.semantic_confidence,
            resolution_order_step=0,
            fallback_used=(stage not in (SemanticResolutionStage.EXACT_ALIAS_MATCH, SemanticResolutionStage.CANONICAL_MATCH)),
            timestamp_utc=datetime.now(UTC),
        )

        pr = ProvenanceRecord(
            field=domain.value,
            original_value=original,
            canonical_value=selected.canonical_name if selected else None,
            source=f"{domain.value}_ontology",
            method="ontology_lookup",
            timestamp_utc=datetime.now(UTC),
            transformation_rule="semantic_resolution",
            confidence=tr.semantic_confidence if stage != SemanticResolutionStage.UNKNOWN_VALUE else None,
            source_record_id=None,
        )

        return tr, dt, pr, (selected.canonical_name if selected else None)
