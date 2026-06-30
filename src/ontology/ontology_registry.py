from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
from abc import ABC
from typing import Dict, Tuple, Optional, List

from rapidfuzz import process, fuzz

from src.models.ontology_models import OntologyDocument, OntologyEntry
from src.models.enums import EntityDomain
from src.ontology.ontology_loader import load_ontologies
from src.utils.ids import new_uuid_hex

logger = logging.getLogger("sgct.ontology.registry")


@dataclass
class OntologyRegistryState:
    documents: dict[str, OntologyDocument] = field(default_factory=dict)
    alias_index: dict[Tuple[str, str], OntologyEntry] = field(default_factory=dict)
    canonical_index: dict[Tuple[str, str], OntologyEntry] = field(default_factory=dict)


class OntologyRegistry(ABC):
    """Concrete filesystem-backed ontology registry.

    Loads YAML ontology documents and exposes deterministic lookup APIs.
    """

    def __init__(self) -> None:
        self._state = OntologyRegistryState()

    @property
    def state(self) -> OntologyRegistryState:
        return self._state

    def _document_key_for_domain(self, domain: EntityDomain) -> str:
        if domain == EntityDomain.SKILL:
            return "skills"
        if domain == EntityDomain.COMPANY:
            return "companies"
        if domain == EntityDomain.JOB_TITLE:
            return "job_titles"
        if domain == EntityDomain.DEGREE:
            return "degrees"
        if domain == EntityDomain.COUNTRY:
            return "countries"
        return domain.value

    def load(self, ontology_paths: dict[str, str]) -> None:
        docs = load_ontologies(ontology_paths)
        self._state.documents = docs
        # build indexes
        for name, doc in docs.items():
            for entry in doc.entries:
                key_can = (name, entry.canonical_name.strip().lower())
                self._state.canonical_index[key_can] = entry
                for a in entry.aliases:
                    key_alias = (name, str(a).strip().lower())
                    self._state.alias_index[key_alias] = entry

    def validate(self) -> None:
        # ensure each document and entry has canonical_name and category
        for name, doc in self._state.documents.items():
            if not doc.entries:
                logger.warning("Ontology %s has no entries", name)
            for e in doc.entries:
                if not e.canonical_name or not e.category:
                    raise ValueError(f"Malformed ontology entry in {name}: {e}")

    def get_by_alias(self, domain: EntityDomain, value: str) -> OntologyEntry | None:
        document_key = self._document_key_for_domain(domain)
        normalized_value = value.strip().lower()
        return self._state.alias_index.get((document_key, normalized_value))

    def get_by_canonical(self, domain: EntityDomain, value: str) -> OntologyEntry | None:
        document_key = self._document_key_for_domain(domain)
        normalized_value = value.strip().lower()
        return self._state.canonical_index.get((document_key, normalized_value))

    def get_parent_category(self, domain: EntityDomain, canonical_name: str) -> str | None:
        ent = self.get_by_canonical(domain, canonical_name)
        if ent:
            return ent.parent_category
        return None

    def get_related_entities(self, domain: EntityDomain, canonical_name: str) -> list[str]:
        ent = self.get_by_canonical(domain, canonical_name)
        if not ent:
            return []
        return ent.related_to

    def exists(self, domain: EntityDomain, value: str) -> bool:
        return bool(self.get_by_alias(domain, value) or self.get_by_canonical(domain, value))

    def list_aliases(self, domain: EntityDomain, canonical_name: str) -> list[str]:
        ent = self.get_by_canonical(domain, canonical_name)
        if not ent:
            return []
        return ent.aliases

    def list_categories(self, domain: EntityDomain) -> list[str]:
        cats = set()
        document_key = self._document_key_for_domain(domain)
        for (docname, key), ent in self._state.canonical_index.items():
            if docname == document_key:
                cats.add(ent.category)
        return sorted(cats)

    def deterministic_fuzzy_match(
        self,
        domain: EntityDomain,
        value: str,
        threshold: int = 80,
    ) -> OntologyEntry | None:
        # candidates are canonical names and aliases within domain
        candidates = []
        mapping: Dict[str, OntologyEntry] = {}
        document_key = self._document_key_for_domain(domain)
        for (docname, key), ent in self._state.canonical_index.items():
            if docname != document_key:
                continue
            candidates.append(ent.canonical_name)
            mapping[ent.canonical_name] = ent
            for a in ent.aliases:
                candidates.append(a)
                mapping[a] = ent

        if not candidates:
            return None
        # use rapidfuzz extractOne
        choice = process.extractOne(value, candidates, scorer=fuzz.WRatio)
        if not choice:
            return None
        match, score, _ = choice
        if score >= threshold:
            return mapping.get(match)
        return None

