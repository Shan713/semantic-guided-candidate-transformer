from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.models.enums import (
    EntityDomain,
    MissingValueStrategy,
    ProjectionMode,
    SemanticResolutionStage,
    SourceType,
)


class SourceMetadata(BaseModel):
    source_name: SourceType
    source_record_id: str | None = None
    source_file: str | None = None
    ingested_at_utc: datetime
    extractor_name: str
    extractor_version: str | None = None
    extraction_quality: float = Field(ge=0.0, le=1.0)
    raw_reference_hash: str | None = None


class Email(BaseModel):
    value: str
    normalized: str
    is_primary: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class Phone(BaseModel):
    raw: str
    normalized_e164: str | None = None
    country_code: str | None = None
    is_primary: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class Location(BaseModel):
    raw: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    country_code: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class Links(BaseModel):
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    other: list[str] = Field(default_factory=list)


class ConfidenceBreakdown(BaseModel):
    source_reliability: float = Field(ge=0.0, le=1.0)
    source_reliability_base: float = Field(ge=0.0, le=1.0)
    source_reliability_field_adjusted: float = Field(ge=0.0, le=1.0)
    reliability_override_applied: bool = False
    cross_source_agreement: float = Field(ge=0.0, le=1.0)
    extraction_quality: float = Field(ge=0.0, le=1.0)
    semantic_certainty: float = Field(ge=0.0, le=1.0)
    conflict_penalty: float = Field(ge=0.0, le=1.0)
    llm_penalty: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class ConfidenceRecord(BaseModel):
    field: str
    score: float = Field(ge=0.0, le=1.0)
    breakdown: ConfidenceBreakdown
    computed_at_utc: datetime
    scorer_version: str


class ProvenanceRecord(BaseModel):
    field: str
    original_value: Any = None
    canonical_value: Any = None
    source: str
    method: str
    timestamp_utc: datetime
    transformation_rule: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_record_id: str | None = None


class TransformationRecord(BaseModel):
    record_id: str
    field: str
    original_value: Any = None
    canonical_value: Any = None
    resolver: str
    rule_name: str
    ontology_domain: str
    matched_alias: str | None = None
    semantic_confidence: float = Field(ge=0.0, le=1.0)
    resolution_stage: SemanticResolutionStage
    related_to_applied: list[str] = Field(default_factory=list)
    timestamp_utc: datetime


class DecisionTrace(BaseModel):
    trace_id: str
    stage: str
    field: str
    decision_type: str
    candidates_considered: list[Any] = Field(default_factory=list)
    selected_value: Any = None
    rationale: str
    rule_or_policy: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    resolution_order_step: int | None = None
    fallback_used: bool = False
    timestamp_utc: datetime


class MergeDecision(BaseModel):
    decision_id: str
    entity: str
    field: str
    strategy: str
    competing_values: list[Any] = Field(default_factory=list)
    selected_value: Any = None
    rejected_values: list[Any] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp_utc: datetime


class EntityLinkRecord(BaseModel):
    link_id: str
    input_value: str
    canonical_entity: str
    entity_domain: EntityDomain
    category: str | None = None
    parent_category: str | None = None
    related_entities: list[str] = Field(default_factory=list)
    link_method: str
    link_confidence: float = Field(ge=0.0, le=1.0)
    timestamp_utc: datetime


class FieldReliabilityRecord(BaseModel):
    source_name: SourceType
    field_name: str
    reliability_score: float = Field(ge=0.0, le=1.0)
    rationale: str
    version: str


class FieldEvidence(BaseModel):
    evidence_id: str
    field: str
    original_value: Any = None
    canonical_value: Any = None
    source: SourceMetadata | None = None
    method: str
    semantic_rule: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp_utc: datetime
    provenance_ref: str | None = None
    transformation_ref: str | None = None
    entity_link_id: str | None = None
    resolved_domain: EntityDomain | None = None
    resolved_category: str | None = None
    resolved_parent_category: str | None = None


class Skill(BaseModel):
    name: str
    original_names: list[str] = Field(default_factory=list)
    category: str | None = None
    parent_category: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    company: str
    company_canonical: str | None = None
    title: str
    title_canonical: str | None = None
    start: date | None = None
    end: date | None = None
    summary: str | None = None
    location: Location | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str
    degree: str
    degree_canonical: str | None = None
    field: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class RuntimeMetadata(BaseModel):
    environment: str
    app_version: str
    config_version: str
    ontology_versions: dict[str, str] = Field(default_factory=dict)
    host_info: dict[str, str] = Field(default_factory=dict)


class PipelineStats(BaseModel):
    fragments_processed: int = 0
    semantic_resolutions_total: int = 0
    exact_matches: int = 0
    canonical_matches: int = 0
    parent_resolutions: int = 0
    entity_links_created: int = 0
    fuzzy_matches: int = 0
    unknown_values: int = 0
    conflicts_detected: int = 0
    warnings_count: int = 0


class ProjectionRule(BaseModel):
    rule_id: str
    source_path: str
    target_path: str
    operation: str
    default_value: Any = None
    transform_hint: str | None = None
    required: bool = False
    enabled: bool = True


class ProjectionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: ProjectionMode
    output_schema_name: str
    output_schema_version: str
    rules: list[ProjectionRule] = Field(default_factory=list)
    include_provenance: bool = True
    include_confidence: bool = True
    missing_value_strategy: MissingValueStrategy = MissingValueStrategy.NULL
    strict_unmapped_target_fields: bool = True
    freeze_canonical_input: bool = True
    emit_validation_errors: bool = True


class CandidateFragment(BaseModel):
    fragment_id: str
    external_candidate_id: str | None = None
    source_metadata: SourceMetadata | None = None
    full_name: str | None = None
    emails: list[Email] = Field(default_factory=list)
    phones: list[Phone] = Field(default_factory=list)
    location: Location | None = None
    links: Links | None = None
    headline: str | None = None
    years_experience: float | None = None
    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    field_evidence: list[FieldEvidence] = Field(default_factory=list)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    decision_trace: list[DecisionTrace] = Field(default_factory=list)
    transformation_history: list[TransformationRecord] = Field(default_factory=list)
    confidence_records: list[ConfidenceRecord] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)


class SemanticCandidateFragment(CandidateFragment):
    """Semantic fragment contract after ontology resolution."""


class IdentityResolutionResult(BaseModel):
    matched_candidate_ids: list[str] = Field(default_factory=list)
    identity_key_used: str
    match_reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)
    decision_trace: list[DecisionTrace] = Field(default_factory=list)
    fragments: list[SemanticCandidateFragment] = Field(default_factory=list)


class FieldConfidence(BaseModel):
    field: str
    score: float = Field(ge=0.0, le=1.0)
    breakdown: ConfidenceBreakdown
    computed_at_utc: datetime
    scorer_version: str
    reason_codes: list[str] = Field(default_factory=list)
    source_count: int = 0


class OverallConfidence(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    breakdown: ConfidenceBreakdown
    field_confidences: list[FieldConfidence] = Field(default_factory=list)
    computed_at_utc: datetime
    scorer_version: str


class CanonicalCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    full_name: str | None = None
    emails: list[Email] = Field(default_factory=list)
    phones: list[Phone] = Field(default_factory=list)
    location: Location | None = None
    links: Links = Field(default_factory=Links)
    headline: str | None = None
    years_experience: float | None = None
    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    field_evidence: list[FieldEvidence] = Field(default_factory=list)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    confidence_records: list[ConfidenceRecord] = Field(default_factory=list)
    transformation_history: list[TransformationRecord] = Field(default_factory=list)
    merge_decisions: list[MergeDecision] = Field(default_factory=list)
    decision_trace: list[DecisionTrace] = Field(default_factory=list)
    source_summaries: list[SourceMetadata] = Field(default_factory=list)
    overall_confidence_internal: float = Field(ge=0.0, le=1.0)
    finalized_at_utc: datetime


class OutputSkill(BaseModel):
    name: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)


class OutputExperience(BaseModel):
    company: str | None = None
    title: str | None = None
    start: str | None = None
    end: str | None = None
    summary: str | None = None


class OutputEducation(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    end_year: int | None = None


class OutputProvenance(BaseModel):
    field: str
    source: str
    method: str


class OutputLocation(BaseModel):
    city: str | None = None
    region: str | None = None
    country: str | None = None


class OutputLinks(BaseModel):
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    other: list[str] = Field(default_factory=list)


class OutputCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    full_name: str | None = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    location: OutputLocation = Field(default_factory=OutputLocation)
    links: OutputLinks = Field(default_factory=OutputLinks)
    headline: str | None = None
    years_experience: float | None = None
    skills: list[OutputSkill] = Field(default_factory=list)
    experience: list[OutputExperience] = Field(default_factory=list)
    education: list[OutputEducation] = Field(default_factory=list)
    provenance: list[OutputProvenance] = Field(default_factory=list)
    overall_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class PipelineContext(BaseModel):
    execution_id: str
    started_at_utc: datetime
    config_bundle: dict[str, Any] = Field(default_factory=dict)
    ontology_registry_ref: str
    logger_ref: str
    runtime_metadata: RuntimeMetadata
    pipeline_stats: PipelineStats = Field(default_factory=PipelineStats)
    semantic_config_loaded: bool = False
    projection_mode: ProjectionMode = ProjectionMode.DEFAULT
