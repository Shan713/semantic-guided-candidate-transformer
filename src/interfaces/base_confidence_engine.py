from abc import ABC, abstractmethod

from src.models.domain_models import CanonicalCandidate, PipelineContext


class BaseConfidenceEngine(ABC):
    @abstractmethod
    def score(self, candidate: CanonicalCandidate, context: PipelineContext) -> CanonicalCandidate:
        ...
