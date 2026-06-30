from __future__ import annotations

import yaml
import logging
from pathlib import Path
from typing import Dict

from src.models.ontology_models import OntologyDocument

logger = logging.getLogger("sgct.ontology.loader")


REQUIRED_KEYS = {"ontology_name", "version", "updated_at_utc", "entries"}


def load_ontology_file(path: str) -> OntologyDocument:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Ontology file not found: {path}")
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Malformed ontology file: {path}")
    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ValueError(f"Ontology file {path} missing keys: {missing}")
    # Pydantic will validate entries
    doc = OntologyDocument(**data)
    return doc


def load_ontologies(paths: Dict[str, str]) -> Dict[str, OntologyDocument]:
    docs: Dict[str, OntologyDocument] = {}
    for name, p in paths.items():
        try:
            docs[name] = load_ontology_file(p)
        except Exception as e:
            logger.error("Failed to load ontology %s from %s: %s", name, p, e)
            raise
    return docs
