from typing import Any

from pydantic import BaseModel, Field


class OntologyEntry(BaseModel):
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    category: str
    parent_category: str | None = None
    related_to: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OntologyDocument(BaseModel):
    ontology_name: str
    version: str
    updated_at_utc: str
    entries: list[OntologyEntry] = Field(default_factory=list)
