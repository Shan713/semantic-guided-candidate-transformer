from abc import ABC, abstractmethod

from src.models.domain_models import CanonicalCandidate, OutputCandidate, PipelineContext, ProjectionConfig


class BaseProjector(ABC):
    @abstractmethod
    def project(
        self,
        candidate: CanonicalCandidate,
        projection_config: ProjectionConfig,
        context: PipelineContext,
    ) -> OutputCandidate:
        ...
