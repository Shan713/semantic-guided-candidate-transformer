import json
from pathlib import Path
from datetime import datetime, UTC

from src.adapters.ats_json_adapter import ATSJSONAdapter
from src.adapters.enrichment_helpers import build_text_fragment
from src.adapters.csv_adapter import CSVAdapter
from src.adapters.resume_pdf_adapter import ResumePDFAdapter
from src.models.domain_models import SourceMetadata
from src.models.enums import SourceType


ROOT = Path(__file__).resolve().parents[1] / "sample_inputs"


def test_csv_adapter_richer_fields():
    frag = CSVAdapter().adapt((ROOT / "candidate_recruiter.csv").read_text(encoding="utf-8"), None)

    assert frag.full_name == "Shantharam P"
    assert frag.headline == "Backend Developer"
    assert frag.location.city == "Coimbatore"
    assert frag.location.country == "India"
    assert len(frag.emails) == 1
    assert len(frag.phones) == 1
    assert len(frag.experience) == 1
    assert frag.experience[0].company == "GalaxyZ Space"
    assert frag.experience[0].title == "Backend Developer"
    assert frag.field_evidence
    assert any(record.field == "experience" for record in frag.field_evidence)
    assert any(record.field == "headline" for record in frag.field_evidence)
    assert all(record.transformation_ref for record in frag.field_evidence)


def test_csv_adapter_conflict_source_keeps_realistic_merge_conflict():
    frag = CSVAdapter().adapt((ROOT / "candidate_conflict.csv").read_text(encoding="utf-8"), None)

    assert frag.full_name == "Shantharam P"
    assert len(frag.emails) == 1
    assert frag.emails[0].normalized == "shanthu2005.alt@gmail.com"
    assert len(frag.phones) == 0
    assert frag.headline == "Software Developer Intern"
    assert frag.experience[0].title == "Software Developer Intern"
    assert any(record.field == "recruiter_notes" for record in frag.field_evidence)


def test_ats_json_adapter_nested_structures():
    payload = json.loads((ROOT / "candidate_ats.json").read_text(encoding="utf-8"))
    frag = ATSJSONAdapter().adapt(payload, None)

    assert frag.full_name == "Shantharam P"
    assert frag.headline == "Backend Developer"
    assert len(frag.emails) == 1
    assert len(frag.phones) == 1
    assert frag.location.city == "Coimbatore"
    assert frag.location.country == "India"
    assert len(frag.skills) >= 5
    assert len(frag.experience) >= 2
    assert len(frag.education) >= 2
    assert any(skill.name == "Python" for skill in frag.skills)
    assert any(experience.company == "Sony SSUP" for experience in frag.experience)
    assert any(education.institution == "Amrita Vishwa Vidyapeetham" for education in frag.education)
    assert any(record.field == "skills" for record in frag.field_evidence)
    assert any(record.field == "experience" for record in frag.field_evidence)
    assert any(record.field == "education" for record in frag.field_evidence)


def test_resume_pdf_adapter_extracts_richer_profile():
    frag = ResumePDFAdapter().adapt(str(ROOT / "resume.pdf"), None)

    assert frag.full_name == "Shantharam P"
    assert frag.headline
    assert len(frag.emails) == 1
    assert len(frag.phones) == 1
    assert len(frag.skills) >= 8
    assert len(frag.experience) == 2
    assert len(frag.education) == 2
    assert any(skill.name == "Python" for skill in frag.skills)
    assert any(experience.company == "Sony SSUP" for experience in frag.experience)
    assert any(education.institution == "Amrita Vishwa Vidyapeetham" for education in frag.education)
    assert any(record.field == "projects" for record in frag.field_evidence)


def test_build_text_fragment_normalizes_generic_pdf_artifacts():
    source = SourceMetadata(
        source_name=SourceType.RESUME_PDF,
        source_record_id="test-resume",
        source_file="test-resume.pdf",
        ingested_at_utc=datetime.now(UTC),
        extractor_name="test",
        extractor_version="1.0",
        extraction_quality=0.9,
        raw_reference_hash="hash-test",
    )
    text = """
Jane Doe
Summary
Backend-
Engineer with backend systems experience.
Skills
Python, Django • REST API Development
Experience
Backend Engineer at Acme Corp Jan 2020 - Present
Education
2020 - 2024 B.Tech, Computer Science and Engineering
University of Example
"""

    frag = build_text_fragment(text, source, "pdf")

    assert frag.full_name == "Jane Doe"
    assert [skill.name for skill in frag.skills] == ["Python", "Django", "REST API Development"]
    assert frag.headline == "Backend Engineer with backend systems experience."
    assert frag.experience[0].company == "Acme Corp"
    assert frag.education[0].institution == "University of Example"
