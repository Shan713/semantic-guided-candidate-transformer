from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from src.models.domain_models import CanonicalCandidate


class CanonicalCandidateBuilder:
    """Validate and finalize a canonical candidate before downstream use."""

    def build(self, candidate: CanonicalCandidate, context: Any | None = None) -> CanonicalCandidate:
        if not candidate.candidate_id:
            raise ValueError("CanonicalCandidate requires a candidate_id")
        finalized = candidate
        if finalized.finalized_at_utc is None:
            finalized = finalized.model_copy(update={"finalized_at_utc": datetime.now(UTC)})
        return CanonicalCandidate.model_validate(finalized.model_dump())
