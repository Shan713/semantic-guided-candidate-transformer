from src.ontology.ontology_registry import OntologyRegistry
from src.models.enums import EntityDomain
import os


def test_ontology_registry_load_and_alias_lookup():
    # prepare paths from src/ontology
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
    ent = reg.get_by_alias(EntityDomain.SKILL, "python3")
    assert ent is not None
    assert ent.canonical_name.lower() == "python"
