from abc import ABC, abstractmethod

from src.models.domain_models import CanonicalCandidate, PipelineContext


class BaseProvenanceEngine(ABC):
    @abstractmethod
    def enrich(self, candidate: CanonicalCandidate, context: PipelineContext) -> CanonicalCandidate:
        ...
