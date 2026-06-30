"""Pipeline orchestrator for the SGCT transformation engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.core.settings import get_settings
from src.core.logging import get_logger
from src.models.domain_models import PipelineContext, CandidateFragment, CanonicalCandidate
from src.models.semantic_models import SemanticCandidateFragment
from src.transformation import (
    CanonicalCandidateBuilder,
    EvidenceAggregationEngine,
    IdentityResolutionEngine,
    load_transformation_config_bundle,
)
from src.fusion import CandidateFusionEngine
from src.confidence import ConfidenceEngine
from src.provenance import ProvenanceEngine
from src.projection import ProjectionEngine, load_projection_config
from src.validation import ValidationEngine
from src.semantic.semantic_engine import SemanticResolutionEngine
from src.ontology.ontology_registry import OntologyRegistry
from src.models.validation_models import ValidationResult


@dataclass
class PipelineOrchestrator:
    """Orchestrates bootstrap of the SGCT pipeline.

    Responsibilities (foundation only):
    - Load runtime configuration into a context bundle
    - Initialize PipelineContext
    - Register adapters (placeholders)
    - Prepare future pipeline stages
    - Provide execute() stub
    """

    settings: Any
    logger: Any
    context: PipelineContext
    identity_resolution_engine: IdentityResolutionEngine | None = field(default=None, init=False, repr=False)
    fusion_engine: CandidateFusionEngine | None = field(default=None, init=False, repr=False)
    evidence_aggregation_engine: EvidenceAggregationEngine | None = field(default=None, init=False, repr=False)
    confidence_engine: ConfidenceEngine | None = field(default=None, init=False, repr=False)
    provenance_engine: ProvenanceEngine | None = field(default=None, init=False, repr=False)
    candidate_builder: CanonicalCandidateBuilder | None = field(default=None, init=False, repr=False)
    semantic_engine: SemanticResolutionEngine | None = field(default=None, init=False, repr=False)
    projection_engine: ProjectionEngine | None = field(default=None, init=False, repr=False)
    validation_engine: ValidationEngine | None = field(default=None, init=False, repr=False)
    ontology_registry: OntologyRegistry | None = field(default=None, init=False, repr=False)

    @classmethod
    def build(cls) -> "PipelineOrchestrator":
        settings = get_settings()
        logger = get_logger("sgct.pipeline")
        # Build minimal context using pipeline_context builder
        from src.core.pipeline_context import build_initial_pipeline_context

        context = build_initial_pipeline_context()
        config_bundle = load_transformation_config_bundle(settings.config_dir)
        context.config_bundle = config_bundle
        context.semantic_config_loaded = True
        context.config_bundle["projection"] = load_projection_config(settings.config_dir / "projection.yml")
        return cls(settings=settings, logger=logger, context=context)

    def register_adapter(self, adapter_name: str, adapter_ctor: Any) -> None:
        self.logger.debug("Registering adapter %s", adapter_name)

    def prepare_stages(self) -> None:
        if self.ontology_registry is None:
            self.ontology_registry = self._build_ontology_registry()
        if self.semantic_engine is None:
            assert self.ontology_registry is not None
            fuzzy_threshold = self._semantic_fuzzy_threshold()
            self.semantic_engine = SemanticResolutionEngine(self.ontology_registry, fuzzy_threshold=fuzzy_threshold)
        if self.identity_resolution_engine is None:
            self.identity_resolution_engine = IdentityResolutionEngine(self.context.config_bundle)
        if self.fusion_engine is None:
            self.fusion_engine = CandidateFusionEngine(self.context.config_bundle)
        if self.evidence_aggregation_engine is None:
            self.evidence_aggregation_engine = EvidenceAggregationEngine()
        if self.confidence_engine is None:
            self.confidence_engine = ConfidenceEngine(self.context.config_bundle)
        if self.provenance_engine is None:
            self.provenance_engine = ProvenanceEngine()
        if self.candidate_builder is None:
            self.candidate_builder = CanonicalCandidateBuilder()
        if self.projection_engine is None:
            self.projection_engine = ProjectionEngine()
        if self.validation_engine is None:
            self.validation_engine = ValidationEngine()
        self.logger.debug("Preparing pipeline stages (transformation engines ready)")

    def semantic_resolve(self, fragments: list[CandidateFragment]) -> list[SemanticCandidateFragment]:
        self.prepare_stages()
        assert self.semantic_engine is not None
        resolved: list[SemanticCandidateFragment] = []
        for fragment in fragments:
            cloned = fragment.model_copy(deep=True)
            semantic_fragment = self.semantic_engine.resolve_fragment(cloned, self.context)
            resolved.append(SemanticCandidateFragment.model_validate(semantic_fragment.model_dump(mode="python")))
        return resolved

    def transform(self, fragments: list[CandidateFragment]) -> list[CanonicalCandidate]:
        self.prepare_stages()
        assert self.identity_resolution_engine is not None
        assert self.fusion_engine is not None
        assert self.evidence_aggregation_engine is not None
        assert self.confidence_engine is not None
        assert self.provenance_engine is not None
        assert self.candidate_builder is not None

        if not fragments:
            return []

        self.context.pipeline_stats.fragments_processed += len(fragments)

        identity_groups = self.identity_resolution_engine.resolve(fragments, self.context)
        self.context.pipeline_stats.semantic_resolutions_total += len(identity_groups)

        canonical_candidates: list[CanonicalCandidate] = []
        for group in identity_groups:
            fused = self.fusion_engine.fuse(group.fragments, self.context)
            aggregated = self.evidence_aggregation_engine.aggregate(fused, group.fragments, self.context)
            scored = self.confidence_engine.score(aggregated, self.context)
            provenanced = self.provenance_engine.enrich(scored, self.context)
            canonical = self.candidate_builder.build(provenanced, self.context)
            canonical_candidates.append(canonical)

        return canonical_candidates

    def execute_transformation(self, fragments: list[CandidateFragment]) -> list[CanonicalCandidate]:
        return self.transform(fragments)

    def project_candidate(self, candidate: CanonicalCandidate, projection_config: Any | None = None) -> dict[str, Any]:
        self.prepare_stages()
        assert self.projection_engine is not None
        config = projection_config or self.context.config_bundle.get("projection")
        return self.projection_engine.project(candidate, config)

    def validate_projection(self, payload: dict[str, Any], projection_config: Any | None = None) -> ValidationResult:
        self.prepare_stages()
        assert self.validation_engine is not None
        config = projection_config or self.context.config_bundle.get("projection")
        return self.validation_engine.validate(payload, config)

    def execute_end_to_end(self, fragments: list[CandidateFragment], projection_config: Any | None = None) -> tuple[list[SemanticCandidateFragment], list[CanonicalCandidate], list[dict[str, Any]], list[ValidationResult]]:
        semantic_fragments = self.semantic_resolve(fragments)
        canonical_candidates = self.transform(semantic_fragments)
        projected = [self.project_candidate(candidate, projection_config) for candidate in canonical_candidates]
        validation_results = [self.validate_projection(item, projection_config) for item in projected]
        return semantic_fragments, canonical_candidates, projected, validation_results

    def execute(self) -> None:
        """Execution stub for Phase 1. No business logic implemented."""
        self.logger.info("Pipeline execute() called (stub) - no action taken")

    def _build_ontology_registry(self) -> OntologyRegistry:
        semantic_config = self._load_yaml(self.settings.config_dir / "semantic.yml")
        ontology_paths = semantic_config.get("ontology_paths", {}) if isinstance(semantic_config, dict) else {}
        base_dir = self.settings.config_dir.parent.parent
        resolved_paths = {name: str((base_dir / Path(path)).resolve()) for name, path in ontology_paths.items()}
        registry = OntologyRegistry()
        registry.load(resolved_paths)
        registry.validate()
        return registry

    def _semantic_fuzzy_threshold(self) -> int:
        semantic_config = self._load_yaml(self.settings.config_dir / "semantic.yml")
        matching = semantic_config.get("matching", {}) if isinstance(semantic_config, dict) else {}
        return int(matching.get("similarity_threshold", 80))

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        return loaded if isinstance(loaded, dict) else {}
