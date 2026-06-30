from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from src.models.domain_models import (
    ConfidenceBreakdown,
    DecisionTrace,
    MergeDecision,
    ProvenanceRecord,
    TransformationRecord,
    IdentityResolutionResult,
    FieldConfidence,
)


class MergePolicy(BaseModel):
    strategy: str
    sort_order: str | None = None
    dedupe_key: str | None = None


class FusionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    policies: dict[str, MergePolicy] = Field(default_factory=dict)
    version: str = "1.0"


class ConfidenceResult(BaseModel):
    field_confidences: list[FieldConfidence] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)


class ProvenanceBundle(BaseModel):
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    transformation_history: list[TransformationRecord] = Field(default_factory=list)
    decision_traces: list[DecisionTrace] = Field(default_factory=list)
    merge_decisions: list[MergeDecision] = Field(default_factory=list)
