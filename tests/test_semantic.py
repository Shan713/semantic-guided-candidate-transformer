from src.ontology.ontology_registry import OntologyRegistry
from src.semantic.semantic_engine import SemanticResolutionEngine
from src.models.domain_models import CandidateFragment, FieldEvidence, Location
from src.utils.ids import new_uuid_hex
from datetime import datetime, UTC
import os


def test_semantic_skill_resolution():
    base = os.path.join(os.path.dirname(__file__), "..", "src", "ontology")
    base = os.path.abspath(base)
    paths = {
        "skills": os.path.join(base, "skills.yml"),
        "companies": os.path.join(base, "companies.yml"),
        "job_titles": os.path.join(base, "job_titles.yml"),
        "degrees": os.path.join(base, "degrees.yml"),
        "countries": os.path.join(base, "countries.yml"),
    }
    reg = OntologyRegistry()
    reg.load(paths)
    reg.validate()
    engine = SemanticResolutionEngine(reg, fuzzy_threshold=75)

    fe = FieldEvidence(
        evidence_id=new_uuid_hex(),
        field="skills",
        original_value="Python3, Tensor Flow",
        source=None,  # not needed for unit test
        method="test",
        semantic_rule=None,
        confidence=0.0,
        timestamp_utc=datetime.now(UTC),
    )

    frag = CandidateFragment(fragment_id=new_uuid_hex(), source_metadata=None, field_evidence=[fe])
    out = engine.resolve_fragment(frag, None)
    names = [s.name.lower() for s in out.skills]
    assert "python" in names
    assert "tensorflow" in names


def test_semantic_country_resolution_uses_ontology_iso_code():
    base = os.path.join(os.path.dirname(__file__), "..", "src", "ontology")
    base = os.path.abspath(base)
    paths = {
        "skills": os.path.join(base, "skills.yml"),
        "companies": os.path.join(base, "companies.yml"),
        "job_titles": os.path.join(base, "job_titles.yml"),
        "degrees": os.path.join(base, "degrees.yml"),
        "countries": os.path.join(base, "countries.yml"),
    }
    reg = OntologyRegistry()
    reg.load(paths)
    reg.validate()
    engine = SemanticResolutionEngine(reg, fuzzy_threshold=75)

    frag = CandidateFragment(
        fragment_id=new_uuid_hex(),
        source_metadata=None,
        location=Location(raw="Coimbatore, India", country="India", confidence=0.0),
    )

    out = engine.resolve_fragment(frag, None)

    assert out.location is not None
    assert out.location.country == "India"
    assert out.location.country_code == "IN"
