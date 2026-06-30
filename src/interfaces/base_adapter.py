from abc import ABC, abstractmethod

from src.models.domain_models import CandidateFragment, PipelineContext


class BaseAdapter(ABC):
    @abstractmethod
    def adapt(self, raw_input: object, context: PipelineContext) -> CandidateFragment:
        ...
