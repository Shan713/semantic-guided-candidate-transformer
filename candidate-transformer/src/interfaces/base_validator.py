from abc import ABC, abstractmethod

from src.models.domain_models import OutputCandidate, PipelineContext


class BaseValidator(ABC):
    @abstractmethod
    def validate(self, output: OutputCandidate, context: PipelineContext) -> None:
        ...
