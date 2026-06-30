from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Iterable
from urllib.parse import urlparse

from src.models.domain_models import CandidateFragment, DecisionTrace
from src.models.transformation_models import IdentityResolutionResult
from src.utils.ids import new_uuid_hex
from src.utils.normalizers import normalize_email, normalize_phone, normalize_whitespace


@dataclass(frozen=True)
class _IdentityKey:
    name: str
    value: str
    confidence: float
    evidence: str


class IdentityResolutionEngine:
    """Deterministically groups fragments by identity signals in priority order."""

    def __init__(self) -> None:
        self._priority = [
            ("linkedin", self._linkedin_key, 1.0),
            ("email", self._email_key, 0.98),
            ("phone", self._phone_key, 0.96),
            ("github", self._github_key, 0.92),
            ("full_name", self._full_name_key, 0.84),
            ("full_name_country", self._full_name_country_key, 0.80),
            ("full_name_city", self._full_name_city_key, 0.78),
        ]

    def resolve(self, fragments: list[CandidateFragment]) -> list[IdentityResolutionResult]:
        if not fragments:
            return []

        groups: list[list[CandidateFragment]] = []
        traces: list[list[DecisionTrace]] = []

        for fragment in fragments:
            placed = False
            for index, group in enumerate(groups):
                match_trace = None
                for existing in group:
                    match_trace = self._compare_fragments(existing, fragment)
                    if match_trace is not None:
                        break
                if match_trace is not None:
                    group.append(fragment)
                    traces[index].append(match_trace)
                    placed = True
                    break
            if not placed:
                groups.append([fragment])
                traces.append([])

        results: list[IdentityResolutionResult] = []
        for index, group in enumerate(groups):
            matched_candidate_ids = [self._fragment_identity(fragment) for fragment in group]
            identity_key_used = None
            match_reason = "different candidates"
            confidence = 0.0
            supporting_evidence: list[str] = []

            if len(group) > 1 and traces[index]:
                first_trace = traces[index][0]
                identity_key_used = first_trace.field
                match_reason = first_trace.rationale
                confidence = first_trace.confidence or 0.0
                supporting_evidence = [f"{first_trace.field}:{first_trace.selected_value}"]

            results.append(
                IdentityResolutionResult(
                    matched_candidate_ids=matched_candidate_ids,
                    identity_key_used=identity_key_used,
                    match_reason=match_reason,
                    confidence=confidence,
                    supporting_evidence=supporting_evidence,
                    decision_traces=traces[index],
                )
            )
        return results

    def _compare_fragments(self, left: CandidateFragment, right: CandidateFragment) -> DecisionTrace | None:
        for step, (key_name, extractor, score) in enumerate(self._priority, start=1):
            left_value = extractor(left)
            right_value = extractor(right)
            if left_value and right_value:
                if left_value == right_value:
                    return DecisionTrace(
                        trace_id=new_uuid_hex(),
                        stage="identity_resolution",
                        field=key_name,
                        decision_type="match",
                        candidates_considered=[left_value, right_value],
                        selected_value=left_value,
                        rationale=f"Matched on {key_name}",
                        rule_or_policy="priority_identity_resolution",
                        confidence=score,
                        resolution_order_step=step,
                        fallback_used=False,
                        timestamp_utc=datetime.now(UTC),
                    )
                return None
        return None

    def _fragment_identity(self, fragment: CandidateFragment) -> str:
        return fragment.external_candidate_id or fragment.fragment_id

    def _linkedin_key(self, fragment: CandidateFragment) -> str | None:
        if fragment.links and fragment.links.linkedin:
            return self._normalize_url(fragment.links.linkedin)
        return None

    def _email_key(self, fragment: CandidateFragment) -> str | None:
        if not fragment.emails:
            return None
        return normalize_email(fragment.emails[0].normalized or fragment.emails[0].value)

    def _phone_key(self, fragment: CandidateFragment) -> str | None:
        if not fragment.phones:
            return None
        phone = fragment.phones[0].normalized_e164 or fragment.phones[0].raw
        return normalize_phone(phone, None)

    def _github_key(self, fragment: CandidateFragment) -> str | None:
        if fragment.links and fragment.links.github:
            return self._normalize_url(fragment.links.github)
        return None

    def _full_name_key(self, fragment: CandidateFragment) -> str | None:
        return normalize_whitespace(fragment.full_name).lower() if fragment.full_name else None

    def _full_name_country_key(self, fragment: CandidateFragment) -> str | None:
        if not fragment.full_name or not fragment.location or not fragment.location.country:
            return None
        return f"{normalize_whitespace(fragment.full_name).lower()}|{normalize_whitespace(fragment.location.country).lower()}"

    def _full_name_city_key(self, fragment: CandidateFragment) -> str | None:
        if not fragment.full_name or not fragment.location or not fragment.location.city:
            return None
        return f"{normalize_whitespace(fragment.full_name).lower()}|{normalize_whitespace(fragment.location.city).lower()}"

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url.strip())
        netloc = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.rstrip("/").lower()
        return f"{netloc}{path}"
