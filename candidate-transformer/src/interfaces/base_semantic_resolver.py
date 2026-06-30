from abc import ABC, abstractmethod

from src.models.domain_models import CandidateFragment, PipelineContext


class BaseSemanticResolver(ABC):
    @abstractmethod
    def resolve(self, fragment: CandidateFragment, context: PipelineContext) -> CandidateFragment:
        ...
