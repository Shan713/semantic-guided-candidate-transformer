from __future__ import annotations

from datetime import datetime, UTC, date

from src.confidence import ConfidenceEngine
from src.core.pipeline import PipelineOrchestrator
from src.fusion import CandidateFusionEngine
from src.models.domain_models import (
    CandidateFragment,
    DecisionTrace,
    Education,
    Email,
    Experience,
    FieldEvidence,
    IdentityResolutionResult,
    Links,
    Location,
    OverallConfidence,
    Phone,
    SemanticCandidateFragment,
    Skill,
    SourceMetadata,
    TransformationRecord,
)
from src.models.enums import SemanticResolutionStage, SourceType
from src.provenance import ProvenanceEngine
from src.transformation import CanonicalCandidateBuilder, EvidenceAggregationEngine, IdentityResolutionEngine
from src.utils.ids import new_uuid_hex


def _source(source_name: SourceType, record_id: str, quality: float) -> SourceMetadata:
    return SourceMetadata(
        source_name=source_name,
        source_record_id=record_id,
        source_file=f"{record_id}.json",
        ingested_at_utc=datetime.now(UTC),
        extractor_name="test",
        extractor_version="1.0",
        extraction_quality=quality,
        raw_reference_hash=f"hash-{record_id}",
    )


def _fragment_one() -> SemanticCandidateFragment:
    source = _source(SourceType.ATS_JSON, "candidate-1", 0.95)
    return SemanticCandidateFragment(
        fragment_id=new_uuid_hex(),
        external_candidate_id="external-1",
        source_metadata=source,
        full_name="Jane Smith",
        emails=[Email(value="JANE.SMITH@example.com", normalized="jane.smith@example.com", confidence=0.92)],
        phones=[Phone(raw="+1 (415) 555-2671", normalized_e164="+14155552671", confidence=0.90)],
        location=Location(raw="New York, NY, US", city="New York", region="NY", country="United States", country_code="US", confidence=0.88),
        links=Links(linkedin="https://www.linkedin.com/in/jane-smith", github="https://github.com/janesmith", portfolio="https://jane.example.com", other=["https://blog.example.com"]),
        headline="Senior Backend Engineer",
        years_experience=7.0,
        skills=[Skill(name="Python", original_names=["Python3"], category="Programming Language", parent_category="Software Development", confidence=0.95, sources=["skill_ontology"], evidence_ids=["skill-1"]), Skill(name="TensorFlow", original_names=["Tensor Flow"], category="Framework", parent_category="Machine Learning", confidence=0.90, sources=["skill_ontology"], evidence_ids=["skill-2"])],
        experience=[
            Experience(company="Google LLC", company_canonical="Google", title="Backend Developer", title_canonical="Software Engineer", start=date(2021, 1, 1), end=None, summary="Built internal APIs", confidence=0.92, evidence_ids=["exp-1"]),
            Experience(company="Acme Corp", company_canonical="Acme Corp", title="Engineer", title_canonical="Software Engineer", start=date(2019, 1, 1), end=date(2020, 12, 31), summary="Early role", confidence=0.80, evidence_ids=["exp-2"]),
        ],
        education=[
            Education(institution="State University", degree="Bachelor of Technology", degree_canonical="Bachelor of Technology", field="Computer Science", start_year=2013, end_year=2017, confidence=0.91, evidence_ids=["edu-1"]),
            Education(institution="State University", degree="B.Tech", degree_canonical="Bachelor of Technology", field="Computer Science", start_year=2013, end_year=2017, confidence=0.88, evidence_ids=["edu-2"]),
        ],
        field_evidence=[
            FieldEvidence(evidence_id="skill-1", field="skills", original_value="Python3", canonical_value="Python", source=source, method="test", semantic_rule="exact_alias_match", confidence=0.95, timestamp_utc=datetime.now(UTC)),
            FieldEvidence(evidence_id="skill-2", field="skills", original_value="Tensor Flow", canonical_value="TensorFlow", source=source, method="test", semantic_rule="exact_alias_match", confidence=0.90, timestamp_utc=datetime.now(UTC)),
            FieldEvidence(evidence_id="exp-1", field="experience", original_value="Google LLC / Backend Developer", canonical_value="Google / Software Engineer", source=source, method="test", semantic_rule="entity_linking", confidence=0.92, timestamp_utc=datetime.now(UTC)),
            FieldEvidence(evidence_id="edu-1", field="education", original_value="B.Tech", canonical_value="Bachelor of Technology", source=source, method="test", semantic_rule="exact_alias_match", confidence=0.91, timestamp_utc=datetime.now(UTC)),
        ],
        transformation_history=[
            TransformationRecord(record_id="tr-skill-1", field="skills", original_value="Python3", canonical_value="Python", resolver="skill_canonicalizer", rule_name="alias", ontology_domain="skill", matched_alias="python3", semantic_confidence=0.95, resolution_stage=SemanticResolutionStage.EXACT_ALIAS_MATCH, related_to_applied=[], timestamp_utc=datetime.now(UTC)),
            TransformationRecord(record_id="tr-skill-2", field="skills", original_value="Tensor Flow", canonical_value="TensorFlow", resolver="skill_canonicalizer", rule_name="alias", ontology_domain="skill", matched_alias="tensor flow", semantic_confidence=0.90, resolution_stage=SemanticResolutionStage.EXACT_ALIAS_MATCH, related_to_applied=[], timestamp_utc=datetime.now(UTC)),
            TransformationRecord(record_id="tr-exp-1", field="job_title", original_value="Backend Developer", canonical_value="Software Engineer", resolver="job_title_resolver", rule_name="entity_linking", ontology_domain="job_title", matched_alias="backend developer", semantic_confidence=0.70, resolution_stage=SemanticResolutionStage.ENTITY_LINKING, related_to_applied=[], timestamp_utc=datetime.now(UTC)),
            TransformationRecord(record_id="tr-edu-1", field="degree", original_value="B.Tech", canonical_value="Bachelor of Technology", resolver="degree_resolver", rule_name="alias", ontology_domain="degree", matched_alias="b.tech", semantic_confidence=0.95, resolution_stage=SemanticResolutionStage.EXACT_ALIAS_MATCH, related_to_applied=[], timestamp_utc=datetime.now(UTC)),
        ],
        decision_trace=[
            DecisionTrace(trace_id="dt-skill-1", stage="semantic_resolution", field="skills", decision_type="resolution", candidates_considered=["Python3"], selected_value="Python", rationale="Exact alias", rule_or_policy="ontology", confidence=0.95, resolution_order_step=1, fallback_used=False, timestamp_utc=datetime.now(UTC)),
        ],
    )


def _fragment_two() -> SemanticCandidateFragment:
    source = _source(SourceType.RESUME_PDF, "candidate-2", 0.82)
    return SemanticCandidateFragment(
        fragment_id=new_uuid_hex(),
        external_candidate_id="external-2",
        source_metadata=source,
        full_name="Jane A. Smith",
        emails=[Email(value="jane.smith@example.com", normalized="jane.smith@example.com", confidence=0.93)],
        phones=[Phone(raw="14155552671", normalized_e164="+14155552671", confidence=0.86)],
        location=Location(raw="New York, NY, US", city="New York", region="NY", country="United States", country_code="US", confidence=0.90),
        links=Links(linkedin="https://linkedin.com/in/jane-smith/", github="https://github.com/janesmith", portfolio=None, other=["https://blog.example.com", "https://jane.example.com"]),
        headline="Lead Backend Engineer",
        years_experience=9.0,
        skills=[Skill(name="Python", original_names=["Python"], category="Programming Language", parent_category="Software Development", confidence=0.96, sources=["skill_ontology"], evidence_ids=["skill-3"]), Skill(name="Docker", original_names=["Docker"], category="DevOps Tool", parent_category="Infrastructure", confidence=0.88, sources=["skill_ontology"], evidence_ids=["skill-4"])],
        experience=[
            Experience(company="Google", company_canonical="Google", title="Software Engineer", title_canonical="Software Engineer", start=date(2021, 1, 1), end=None, summary="API ownership", confidence=0.94, evidence_ids=["exp-3"]),
        ],
        education=[
            Education(institution="State University", degree="Bachelor of Technology", degree_canonical="Bachelor of Technology", field="Computer Science", start_year=2013, end_year=2017, confidence=0.92, evidence_ids=["edu-3"]),
        ],
        field_evidence=[
            FieldEvidence(evidence_id="skill-3", field="skills", original_value="Python", canonical_value="Python", source=source, method="test", semantic_rule="canonical_match", confidence=0.96, timestamp_utc=datetime.now(UTC)),
            FieldEvidence(evidence_id="skill-4", field="skills", original_value="Docker", canonical_value="Docker", source=source, method="test", semantic_rule="canonical_match", confidence=0.88, timestamp_utc=datetime.now(UTC)),
            FieldEvidence(evidence_id="exp-3", field="experience", original_value="Google / Software Engineer", canonical_value="Google / Software Engineer", source=source, method="test", semantic_rule="canonical_match", confidence=0.94, timestamp_utc=datetime.now(UTC)),
            FieldEvidence(evidence_id="edu-3", field="education", original_value="Bachelor of Technology", canonical_value="Bachelor of Technology", source=source, method="test", semantic_rule="canonical_match", confidence=0.92, timestamp_utc=datetime.now(UTC)),
        ],
        transformation_history=[
            TransformationRecord(record_id="tr-skill-3", field="skills", original_value="Python", canonical_value="Python", resolver="skill_canonicalizer", rule_name="canonical", ontology_domain="skill", matched_alias=None, semantic_confidence=0.96, resolution_stage=SemanticResolutionStage.CANONICAL_MATCH, related_to_applied=[], timestamp_utc=datetime.now(UTC)),
            TransformationRecord(record_id="tr-skill-4", field="skills", original_value="Docker", canonical_value="Docker", resolver="skill_canonicalizer", rule_name="canonical", ontology_domain="skill", matched_alias=None, semantic_confidence=0.88, resolution_stage=SemanticResolutionStage.CANONICAL_MATCH, related_to_applied=[], timestamp_utc=datetime.now(UTC)),
        ],
        decision_trace=[
            DecisionTrace(trace_id="dt-skill-3", stage="semantic_resolution", field="skills", decision_type="resolution", candidates_considered=["Python"], selected_value="Python", rationale="Canonical match", rule_or_policy="ontology", confidence=0.96, resolution_order_step=2, fallback_used=False, timestamp_utc=datetime.now(UTC)),
        ],
    )


def test_identity_resolution_by_email_and_conflicting_names():
    engine = IdentityResolutionEngine()
    results = engine.resolve([_fragment_one(), _fragment_two()])
    assert len(results) == 1
    result = results[0]
    assert result.identity_key_used == "linkedin_url"
    assert set(result.matched_candidate_ids) == {"external-1", "external-2"}
    assert result.confidence >= 0.99
    assert any("linkedin:" in evidence for evidence in result.supporting_evidence)
    assert result.decision_trace


def test_candidate_fusion_merge_policies():
    engine = CandidateFusionEngine()
    candidate = engine.fuse([_fragment_one(), _fragment_two()], None)

    assert candidate.full_name == "Jane Smith"
    assert [email.normalized for email in candidate.emails] == ["jane.smith@example.com"]
    assert [phone.normalized_e164 for phone in candidate.phones] == ["+14155552671"]
    assert len(candidate.links.other) == 1
    assert [skill.name for skill in candidate.skills] == ["Python", "TensorFlow", "Docker"]
    assert candidate.years_experience == 9.0
    assert candidate.headline == "Senior Backend Engineer"
    assert candidate.location and candidate.location.city == "New York"
    assert candidate.merge_decisions


def test_candidate_fusion_consolidates_duplicate_experience_and_education():
    source = _source(SourceType.RECRUITER_CSV, "candidate-3", 0.9)
    fragment = SemanticCandidateFragment(
        fragment_id=new_uuid_hex(),
        external_candidate_id="external-3",
        source_metadata=source,
        full_name="Alex Rivera",
        experience=[
            Experience(
                company="Acme Corporation",
                company_canonical="Acme",
                title="Backend Developer",
                title_canonical="Software Engineer",
                start=date(2022, 1, 1),
                end=None,
                summary="Built backend APIs",
                confidence=0.9,
                evidence_ids=["exp-a"],
            ),
            Experience(
                company="Acme Corp",
                company_canonical="Acme",
                title="Software Engineer",
                title_canonical="Software Engineer",
                start=date(2022, 2, 1),
                end=None,
                summary="Built backend APIs and services",
                confidence=0.85,
                evidence_ids=["exp-b"],
            ),
        ],
        education=[
            Education(
                institution="State University",
                degree="B.Tech",
                degree_canonical="Bachelor of Technology",
                field="Computer Science",
                start_year=2018,
                end_year=2022,
                confidence=0.9,
                evidence_ids=["edu-a"],
            ),
            Education(
                institution="State University",
                degree="Bachelor of Technology",
                degree_canonical="Bachelor of Technology",
                field="Computer Science",
                start_year=2018,
                end_year=2022,
                confidence=0.88,
                evidence_ids=["edu-b"],
            ),
        ],
    )

    candidate = CandidateFusionEngine().fuse([fragment], None)

    assert len(candidate.experience) == 1
    assert candidate.experience[0].title == "Software Engineer"
    assert candidate.experience[0].start == date(2022, 1, 1)
    assert candidate.experience[0].evidence_ids == ["exp-a", "exp-b"]
    assert len(candidate.education) == 1
    assert candidate.education[0].degree == "Bachelor of Technology"
    assert candidate.education[0].evidence_ids == ["edu-a", "edu-b"]


def test_evidence_aggregation_confidence_provenance_and_builder():
    fusion = CandidateFusionEngine()
    aggregation = EvidenceAggregationEngine()
    confidence = ConfidenceEngine()
    provenance = ProvenanceEngine()
    builder = CanonicalCandidateBuilder()

    fused = fusion.fuse([_fragment_one(), _fragment_two()], None)
    aggregated = aggregation.aggregate(fused, [_fragment_one(), _fragment_two()], None)
    scored = confidence.score(aggregated, None)
    provenanced = provenance.enrich(scored, None)
    canonical = builder.build(provenanced, None)

    assert canonical.field_evidence
    assert canonical.transformation_history
    assert canonical.provenance
    assert canonical.confidence_records
    assert canonical.overall_confidence_internal > 0.0
    assert canonical.finalized_at_utc is not None


def test_provenance_engine_compacts_repeated_field_traces():
    fusion = CandidateFusionEngine()
    aggregation = EvidenceAggregationEngine()
    provenance = ProvenanceEngine()

    fused = fusion.fuse([_fragment_one(), _fragment_two()], None)
    aggregated = aggregation.aggregate(fused, [_fragment_one(), _fragment_two()], None)
    provenanced = provenance.enrich(aggregated, None)
    raw_provenance_count = len(aggregated.provenance) + len(aggregated.field_evidence) + len(aggregated.merge_decisions)

    assert provenanced.provenance
    assert len(provenanced.provenance) < raw_provenance_count
    assert any(isinstance(record.original_value, list) for record in provenanced.provenance)


def test_pipeline_orchestrator_transformation_flow():
    orchestrator = PipelineOrchestrator.build()
    canonical_candidates = orchestrator.transform([_fragment_one(), _fragment_two()])

    assert len(canonical_candidates) == 1
    canonical = canonical_candidates[0]
    assert canonical.candidate_id
    assert canonical.overall_confidence_internal > 0.0
    assert canonical.provenance
