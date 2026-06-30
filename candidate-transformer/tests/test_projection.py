from __future__ import annotations

from datetime import UTC, date, datetime

from src.models.domain_models import (
    CanonicalCandidate,
    ConfidenceBreakdown,
    ConfidenceRecord,
    DecisionTrace,
    Education,
    Email,
    Experience,
    FieldEvidence,
    Links,
    Location,
    MergeDecision,
    Phone,
    ProvenanceRecord,
    Skill,
    SourceMetadata,
    TransformationRecord,
)
from src.models.enums import MissingValueStrategy, ProjectionMode, SemanticResolutionStage, SourceType
from src.projection import ProjectionEngine, load_projection_config


def _candidate() -> CanonicalCandidate:
    source = SourceMetadata(
        source_name=SourceType.ATS_JSON,
        source_record_id="cand-1",
        source_file="cand-1.json",
        ingested_at_utc=datetime.now(UTC),
        extractor_name="test",
        extractor_version="1.0",
        extraction_quality=1.0,
        raw_reference_hash="hash",
    )
    return CanonicalCandidate(
        candidate_id="candidate-1",
        full_name="Jane Smith",
        emails=[Email(value="Jane.Smith@example.com", normalized="jane.smith@example.com", confidence=0.95)],
        phones=[Phone(raw="4155552671", normalized_e164="+14155552671", confidence=0.9)],
        location=Location(raw="New York, NY, United States", city="New York", region="NY", country="United States", country_code="US", confidence=0.9),
        links=Links(linkedin="https://linkedin.com/in/jane-smith", github="https://github.com/janesmith", portfolio="https://jane.example.com", other=["https://blog.example.com"]),
        headline="Senior Backend Engineer",
        years_experience=9.0,
        skills=[
            Skill(name="Python", original_names=["Python3"], confidence=0.95, sources=["skill_ontology"], evidence_ids=["ev-2"]),
            Skill(name="Docker", original_names=["Docker"], confidence=0.88, sources=["skill_ontology"], evidence_ids=["ev-3"]),
        ],
        experience=[
            Experience(company="Google LLC", company_canonical="Google", title="Backend Developer", title_canonical="Software Engineer", start=date(2020, 1, 1), end=date(2022, 1, 1), summary="Built APIs", confidence=0.92, evidence_ids=["ev-4"]),
        ],
        education=[
            Education(institution="State University", degree="B.Tech", degree_canonical="Bachelor of Technology", field="Computer Science", start_year=2013, end_year=2017, confidence=0.91, evidence_ids=["ev-5"]),
        ],
        field_evidence=[
            FieldEvidence(evidence_id="ev-1", field="emails", original_value="Jane.Smith@example.com", canonical_value="jane.smith@example.com", source=source, method="test", semantic_rule="canonical_match", confidence=0.95, timestamp_utc=datetime.now(UTC)),
        ],
        provenance=[
            ProvenanceRecord(field="emails", original_value="Jane.Smith@example.com", canonical_value="jane.smith@example.com", source="ats_json", method="test", timestamp_utc=datetime.now(UTC), transformation_rule="canonical_match", confidence=0.95, source_record_id="cand-1"),
        ],
        confidence_records=[
            ConfidenceRecord(
                field="emails",
                score=0.95,
                breakdown=ConfidenceBreakdown(
                    source_reliability=1.0,
                    source_reliability_base=1.0,
                    source_reliability_field_adjusted=1.0,
                    reliability_override_applied=False,
                    cross_source_agreement=1.0,
                    extraction_quality=1.0,
                    semantic_certainty=1.0,
                    conflict_penalty=0.0,
                    llm_penalty=None,
                    notes=[],
                ),
                computed_at_utc=datetime.now(UTC),
                scorer_version="1.0",
            )
        ],
        transformation_history=[
            TransformationRecord(record_id="tr-1", field="skills", original_value="Python3", canonical_value="Python", resolver="skill_canonicalizer", rule_name="alias", ontology_domain="skill", matched_alias="python3", semantic_confidence=0.95, resolution_stage=SemanticResolutionStage.EXACT_ALIAS_MATCH, related_to_applied=[], timestamp_utc=datetime.now(UTC)),
        ],
        merge_decisions=[
            MergeDecision(decision_id="md-1", entity="candidate", field="skills", strategy="semantic_union", competing_values=["Python", "Docker"], selected_value=["Python", "Docker"], rejected_values=[], reason_codes=["semantic_union"], confidence=1.0, timestamp_utc=datetime.now(UTC)),
        ],
        decision_trace=[
            DecisionTrace(trace_id="dt-1", stage="semantic_resolution", field="skills", decision_type="resolution", candidates_considered=["Python3"], selected_value="Python", rationale="Exact alias", rule_or_policy="ontology", confidence=0.95, resolution_order_step=1, fallback_used=False, timestamp_utc=datetime.now(UTC)),
        ],
        source_summaries=[source],
        overall_confidence_internal=0.92,
        finalized_at_utc=datetime.now(UTC),
    )


def test_default_projection_schema():
    engine = ProjectionEngine()
    config = load_projection_config()
    payload = engine.project(_candidate(), config)

    assert payload["candidate_id"] == "candidate-1"
    assert payload["full_name"] == "Jane Smith"
    assert payload["emails"] == ["jane.smith@example.com"]
    assert payload["phones"] == ["+14155552671"]
    assert payload["location"]["country"] == "United States"
    assert payload["skills"][0]["name"] == "Python"
    assert payload["overall_confidence"] == 0.92
    assert payload["provenance"]


def test_custom_projection_field_mapping_and_normalization():
    engine = ProjectionEngine()
    config = load_projection_config(
        {
            "fields": [
                {"path": "full_name", "type": "string"},
                {"path": "primary_email", "from": "emails[0]"},
                {"path": "phone", "from": "phones[0]", "normalize": "E164"},
                {"path": "skills", "from": "skills[].name", "normalize": "canonical"},
                {"path": "country", "from": "location.country", "normalize": "ISO3166"},
            ],
            "include_confidence": True,
            "include_provenance": True,
            "on_missing": "null",
        }
    )

    payload = engine.project(_candidate(), config)

    assert config.mode == ProjectionMode.CUSTOM
    assert payload["full_name"] == "Jane Smith"
    assert payload["primary_email"] == "jane.smith@example.com"
    assert payload["phone"] == "+14155552671"
    assert payload["skills"] == ["Python", "Docker"]
    assert payload["country"] == "US"
    assert payload["overall_confidence"] == 0.92
    assert payload["provenance"]


def test_custom_projection_missing_policy_omit():
    engine = ProjectionEngine()
    config = load_projection_config(
        {
            "fields": [
                {"path": "missing_headline", "from": "summary", "required": False},
            ],
            "include_confidence": False,
            "include_provenance": False,
            "on_missing": "omit",
        }
    )

    payload = engine.project(_candidate(), config)
    assert "missing_headline" not in payload
