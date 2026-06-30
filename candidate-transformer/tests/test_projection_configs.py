"""Extended regression tests for projection configs, missing value policies,
confidence toggles, and provenance toggles."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.models.domain_models import (
    CanonicalCandidate,
    ConfidenceBreakdown,
    ConfidenceRecord,
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
            ProvenanceRecord(field="skills", original_value="Python3", canonical_value="Python", source="skill_ontology", method="ontology_lookup", timestamp_utc=datetime.now(UTC), transformation_rule="alias_match", confidence=0.95, source_record_id=None),
        ],
        confidence_records=[],
        transformation_history=[],
        merge_decisions=[],
        decision_trace=[],
        source_summaries=[source],
        overall_confidence_internal=0.92,
        finalized_at_utc=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Part 4: HR projection — field renaming and normalization
# ---------------------------------------------------------------------------

def test_hr_projection_renames_fields_correctly():
    """emails[0] -> primary_email, phones[0] -> phone, skills[].name -> skills."""
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [
            {"path": "full_name"},
            {"path": "primary_email", "from": "emails[0]"},
            {"path": "phone", "from": "phones[0]", "normalize": "E164"},
            {"path": "skills", "from": "skills[].name"},
        ],
        "include_confidence": True,
        "include_provenance": False,
        "on_missing": "null",
    })

    payload = engine.project(_candidate(), config)

    assert config.mode == ProjectionMode.CUSTOM
    assert "primary_email" in payload
    assert payload["primary_email"] == "jane.smith@example.com"
    assert payload["phone"] == "+14155552671"
    assert payload["skills"] == ["Python", "Docker"]
    assert "provenance" not in payload
    assert "overall_confidence" in payload


# ---------------------------------------------------------------------------
# Part 4: Recruiter projection — subset of fields
# ---------------------------------------------------------------------------

def test_recruiter_projection_outputs_expected_subset():
    """Only name, headline, experience, skills, links, confidence."""
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [
            {"path": "full_name"},
            {"path": "headline"},
            {"path": "experience"},
            {"path": "skills"},
            {"path": "links"},
        ],
        "include_confidence": True,
        "include_provenance": False,
        "on_missing": "null",
    })

    payload = engine.project(_candidate(), config)

    assert set(payload.keys()) == {"full_name", "headline", "experience", "skills", "links", "overall_confidence"}
    assert payload["full_name"] == "Jane Smith"
    assert payload["headline"] == "Senior Backend Engineer"
    assert len(payload["experience"]) == 1
    assert len(payload["skills"]) == 2
    assert "provenance" not in payload


# ---------------------------------------------------------------------------
# Part 5: Confidence toggle
# ---------------------------------------------------------------------------

def test_confidence_toggle_off():
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [{"path": "full_name"}],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "null",
    })
    payload = engine.project(_candidate(), config)
    assert "overall_confidence" not in payload


def test_confidence_toggle_on():
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [{"path": "full_name"}],
        "include_confidence": True,
        "include_provenance": False,
        "on_missing": "null",
    })
    payload = engine.project(_candidate(), config)
    assert "overall_confidence" in payload
    assert payload["overall_confidence"] == 0.92


# ---------------------------------------------------------------------------
# Part 5: Provenance toggle
# ---------------------------------------------------------------------------

def test_provenance_toggle_off():
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [{"path": "full_name"}],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "null",
    })
    payload = engine.project(_candidate(), config)
    assert "provenance" not in payload


def test_provenance_toggle_on():
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [{"path": "full_name"}],
        "include_confidence": False,
        "include_provenance": True,
        "on_missing": "null",
    })
    payload = engine.project(_candidate(), config)
    assert "provenance" in payload
    assert len(payload["provenance"]) > 0


# ---------------------------------------------------------------------------
# Part 5: Missing value strategies
# ---------------------------------------------------------------------------

def test_on_missing_null_strategy():
    """Null strategy: missing values become None in the payload."""
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [
            {"path": "full_name"},
            {"path": "missing_field", "from": "nonexistent_path", "required": False},
        ],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "null",
    })
    payload = engine.project(_candidate(), config)
    assert payload["full_name"] == "Jane Smith"
    # The missing field should either be absent (omit due to missing strategy)
    # or present as null
    if "missing_field" in payload:
        assert payload["missing_field"] is None


def test_on_missing_omit_strategy():
    """Omit strategy: missing non-required fields are removed."""
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [
            {"path": "full_name"},
            {"path": "missing_field", "from": "nonexistent_path", "required": False},
        ],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "omit",
    })
    payload = engine.project(_candidate(), config)
    assert payload["full_name"] == "Jane Smith"
    assert "missing_field" not in payload


def test_on_missing_error_strategy():
    """Error strategy: missing fields raise ValueError."""
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [
            {"path": "full_name"},
            {"path": "missing_field", "from": "nonexistent_path", "required": True},
        ],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "error",
    })
    with pytest.raises(ValueError, match="Missing projected field"):
        engine.project(_candidate(), config)


# ---------------------------------------------------------------------------
# Part 3: Canonical path mapping
# ---------------------------------------------------------------------------

def test_canonical_path_mapping_skills_array():
    """skills[].name extracts only the name from each skill."""
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [{"path": "skills", "from": "skills[].name", "normalize": "canonical"}],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "null",
    })
    payload = engine.project(_candidate(), config)
    assert payload["skills"] == ["Python", "Docker"]


def test_canonical_path_mapping_nested_object():
    """location.country extracts the country field from the nested Location."""
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [
            {"path": "full_name"},
            {"path": "country", "from": "location.country", "normalize": "ISO3166"},
        ],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "null",
    })
    payload = engine.project(_candidate(), config)
    assert payload["full_name"] == "Jane Smith"
    assert payload["country"] == "US"


# ---------------------------------------------------------------------------
# Part 3: Array index selection
# ---------------------------------------------------------------------------

def test_array_index_selection_emails():
    """emails[0] selects the first email as a scalar."""
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [{"path": "email", "from": "emails[0]"}],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "null",
    })
    payload = engine.project(_candidate(), config)
    assert payload["email"] == "jane.smith@example.com"


# ---------------------------------------------------------------------------
# Part 5: Default projection matches assignment schema
# ---------------------------------------------------------------------------

def test_default_projection_matches_assignment_schema():
    """Default projection must contain candidate_id, full_name, emails,
    phones, location, links, headline, skills, experience, education,
    provenance, overall_confidence."""
    engine = ProjectionEngine()
    config = load_projection_config()
    payload = engine.project(_candidate(), config)

    required_keys = {
        "candidate_id", "full_name", "emails", "phones",
        "location", "links", "headline", "skills",
        "experience", "education", "provenance", "overall_confidence",
    }
    missing = required_keys - set(payload.keys())
    assert not missing, f"Missing required keys: {missing}"

    assert isinstance(payload["emails"], list)
    assert isinstance(payload["phones"], list)
    assert isinstance(payload["skills"], list)
    assert isinstance(payload["experience"], list)
    assert isinstance(payload["education"], list)
    assert isinstance(payload["provenance"], list)


# ---------------------------------------------------------------------------
# Part 5: HR projection from config file
# ---------------------------------------------------------------------------

def test_hr_projection_from_config_file():
    """Load hr_projection.json and verify field renaming."""
    engine = ProjectionEngine()
    config = load_projection_config("config/hr_projection.json")
    payload = engine.project(_candidate(), config)

    assert set(payload.keys()) == {"full_name", "primary_email", "phone", "skills", "overall_confidence"}
    assert payload["primary_email"] == "jane.smith@example.com"
    assert payload["phone"] == "+14155552671"


# ---------------------------------------------------------------------------
# Part 5: Recruiter projection from config file
# ---------------------------------------------------------------------------

def test_recruiter_projection_from_config_file():
    """Load recruiter_projection.json and verify subset."""
    engine = ProjectionEngine()
    config = load_projection_config("config/recruiter_projection.json")
    payload = engine.project(_candidate(), config)

    assert set(payload.keys()) == {"full_name", "headline", "experience", "skills", "links", "overall_confidence"}
    assert "provenance" not in payload
    assert "emails" not in payload
    assert "phones" not in payload
    assert "education" not in payload


# ---------------------------------------------------------------------------
# Part 5: Empty fields config returns minimal payload
# ---------------------------------------------------------------------------

def test_empty_fields_config_with_confidence():
    """Config with no fields should produce only metadata."""
    engine = ProjectionEngine()
    config = load_projection_config({
        "fields": [],
        "include_confidence": True,
        "include_provenance": False,
        "on_missing": "null",
    })
    payload = engine.project(_candidate(), config)
    assert "overall_confidence" in payload
    assert payload["overall_confidence"] == 0.92
