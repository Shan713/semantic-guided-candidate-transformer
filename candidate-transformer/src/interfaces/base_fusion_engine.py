from abc import ABC, abstractmethod

from src.models.domain_models import CandidateFragment, CanonicalCandidate, PipelineContext


class BaseFusionEngine(ABC):
    @abstractmethod
    def fuse(self, fragments: list[CandidateFragment], context: PipelineContext) -> CanonicalCandidate:
        ...
