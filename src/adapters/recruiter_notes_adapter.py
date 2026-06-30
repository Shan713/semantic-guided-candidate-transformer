from __future__ import annotations

from src.interfaces.base_adapter import BaseAdapter
from src.models.domain_models import CandidateFragment, PipelineContext


class RecruiterNotesAdapter(BaseAdapter):
    def adapt(self, raw_input: object, context: PipelineContext) -> CandidateFragment:
        raise NotImplementedError("RecruiterNotesAdapter is a placeholder and not implemented in Phase 1")
