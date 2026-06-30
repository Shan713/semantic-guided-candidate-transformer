from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field

from src.models.domain_models import DecisionTrace, IdentityResolutionResult, SemanticCandidateFragment
from src.models.enums import SemanticResolutionStage
from src.transformation.config import load_transformation_config_bundle
from src.utils.ids import new_uuid_hex
from src.utils.normalizers import normalize_email, normalize_phone, normalize_whitespace


@dataclass
class _IdentityGroup:
    fragments: list[SemanticCandidateFragment] = field(default_factory=list)
    matched_candidate_ids: list[str] = field(default_factory=list)
    identity_key_used: str = "different_candidates"
    key_priority: int = 999
    match_reason: str = "No deterministic identity key matched"
    confidence: float = 0.0
    supporting_evidence: list[str] = field(default_factory=list)
    decision_trace: list[DecisionTrace] = field(default_factory=list)


class IdentityResolutionEngine:
    """Deterministically cluster semantic fragments by stable identity keys."""

    _PRIORITY = [
        "linkedin_url",
        "email",
        "phone",
        "github_url",
        "full_name",
        "full_name_country",
        "full_name_city",
    ]

    _CONFIDENCE_BY_KEY = {
        "linkedin_url": 1.0,
        "email": 0.98,
        "phone": 0.96,
        "github_url": 0.94,
        "full_name": 0.90,
        "full_name_country": 0.88,
        "full_name_city": 0.86,
    }

    def __init__(self, config_bundle: dict[str, Any] | None = None) -> None:
        self.config_bundle = config_bundle or load_transformation_config_bundle()
        fusion_config = self.config_bundle.get("fusion", {})
        matching_config = fusion_config.get("identity_resolution", {})
        self.case_insensitive = bool(matching_config.get("case_insensitive", True))
        self.email_exact_match = bool(matching_config.get("email_exact_match", True))
        self.phone_normalized_match = bool(matching_config.get("phone_normalized_match", True))
        self.name_location_support = bool(matching_config.get("name_location_support", True))

    def resolve(self, fragments: list[SemanticCandidateFragment], context: Any | None = None) -> list[IdentityResolutionResult]:
        groups, _ = self._cluster_fragments(fragments)
        results: list[IdentityResolutionResult] = []
        for group in groups:
            results.append(
                IdentityResolutionResult(
                    matched_candidate_ids=list(group.matched_candidate_ids),
                    identity_key_used=group.identity_key_used,
                    match_reason=group.match_reason,
                    confidence=group.confidence,
                    supporting_evidence=list(group.supporting_evidence),
                    decision_trace=list(group.decision_trace),
                    fragments=list(group.fragments),
                )
            )
        return results

    def cluster(self, fragments: list[SemanticCandidateFragment], context: Any | None = None) -> list[list[SemanticCandidateFragment]]:
        groups, _ = self._cluster_fragments(fragments)
        return [list(group.fragments) for group in groups]

    def _cluster_fragments(
        self,
        fragments: list[SemanticCandidateFragment],
    ) -> tuple[list[_IdentityGroup], dict[str, dict[str, int]]]:
        groups: list[_IdentityGroup] = []
        key_index: dict[str, dict[str, int]] = {key: {} for key in self._PRIORITY}
        for fragment in fragments:
            candidate_id = fragment.external_candidate_id or fragment.fragment_id
            fragment_keys = self._fragment_keys(fragment)
            matched_group_index: int | None = None
            matched_key: str | None = None
            matched_key_value: str | None = None

            for key_name, normalized_value, evidence in fragment_keys:
                if not normalized_value:
                    continue
                group_index = key_index.get(key_name, {}).get(normalized_value)
                if group_index is not None:
                    matched_group_index = group_index
                    matched_key = key_name
                    matched_key_value = normalized_value
                    break

            if matched_group_index is None:
                group = _IdentityGroup(
                    fragments=[fragment],
                    matched_candidate_ids=[candidate_id],
                    identity_key_used="different_candidates",
                    key_priority=999,
                    match_reason="No deterministic identity key matched",
                    confidence=0.0,
                    supporting_evidence=self._evidence_summaries(fragment_keys),
                    decision_trace=[
                        self._trace(
                            stage="identity_resolution",
                            field="identity",
                            decision_type="new_candidate",
                            rationale="No deterministic identity key matched",
                            rule_or_policy="priority_keys",
                            confidence=0.0,
                            selected_value=candidate_id,
                            candidates_considered=self._candidate_key_strings(fragment_keys),
                        )
                    ],
                )
                groups.append(group)
                group_index = len(groups) - 1
                for key_name, normalized_value, _ in fragment_keys:
                    if normalized_value:
                        key_index.setdefault(key_name, {})[normalized_value] = group_index
                continue

            group = groups[matched_group_index]
            group.fragments.append(fragment)
            group.matched_candidate_ids.append(candidate_id)
            group.supporting_evidence.extend(self._evidence_summaries(fragment_keys))

            priority_index = self._priority_index(matched_key)
            if priority_index < group.key_priority:
                group.key_priority = priority_index
                group.identity_key_used = matched_key or group.identity_key_used
                group.match_reason = self._match_reason(matched_key or "")
                group.confidence = self._CONFIDENCE_BY_KEY.get(matched_key or "", 0.0)

            group.decision_trace.append(
                self._trace(
                    stage="identity_resolution",
                    field="identity",
                    decision_type="match",
                    rationale=group.match_reason,
                    rule_or_policy=matched_key or "priority_keys",
                    confidence=group.confidence,
                    selected_value=candidate_id,
                    candidates_considered=self._candidate_key_strings(fragment_keys),
                )
            )

            for key_name, normalized_value, _ in fragment_keys:
                if normalized_value:
                    key_index.setdefault(key_name, {})[normalized_value] = matched_group_index

        # Normalize group evidence order and confidence for singleton groups.
        for group in groups:
            group.supporting_evidence = self._dedupe_keep_order(group.supporting_evidence)
            if len(group.fragments) == 1 and group.identity_key_used == "different_candidates":
                group.confidence = 0.0
        return groups, key_index

    def _fragment_keys(self, fragment: SemanticCandidateFragment) -> list[tuple[str, str | None, str]]:
        keys: list[tuple[str, str | None, str]] = []

        linkedin = self._normalize_url(fragment.links.linkedin if fragment.links else None)
        if linkedin:
            keys.append(("linkedin_url", linkedin, f"linkedin:{linkedin}"))

        emails = [normalize_email(email.normalized or email.value) for email in fragment.emails]
        for email in emails:
            if email:
                keys.append(("email", email, f"email:{email}"))

        phones = [self._normalize_phone(phone.normalized_e164 or phone.raw) for phone in fragment.phones]
        for phone in phones:
            if phone:
                keys.append(("phone", phone, f"phone:{phone}"))

        github = self._normalize_url(fragment.links.github if fragment.links else None)
        if github:
            keys.append(("github_url", github, f"github:{github}"))

        full_name = normalize_whitespace(fragment.full_name)
        if full_name:
            normalized_name = self._normalize_text(full_name)
            keys.append(("full_name", normalized_name, f"full_name:{normalized_name}"))

            country_value = self._normalize_text(
                fragment.location.country_code if fragment.location and fragment.location.country_code else fragment.location.country if fragment.location else None
            )
            if country_value:
                keys.append(("full_name_country", f"{normalized_name}|{country_value}", f"full_name_country:{normalized_name}|{country_value}"))

            city_value = self._normalize_text(fragment.location.city if fragment.location else None)
            if city_value:
                keys.append(("full_name_city", f"{normalized_name}|{city_value}", f"full_name_city:{normalized_name}|{city_value}"))

        return keys

    def _normalize_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if self.case_insensitive:
            return text.lower()
        return text

    def _normalize_phone(self, value: str | None) -> str | None:
        if not value:
            return None
        text = value.strip()
        if not text:
            return None
        return text

    def _normalize_url(self, value: str | None) -> str | None:
        if not value:
            return None
        text = value.strip()
        if not text:
            return None
        if not text.startswith(("http://", "https://")):
            text = f"https://{text.lstrip('/')}"
        split = urlsplit(text)
        netloc = split.netloc.lower().removeprefix("www.")
        path = split.path.rstrip("/")
        normalized = urlunsplit((split.scheme.lower(), netloc, path, split.query, split.fragment))
        return normalized.lower() if self.case_insensitive else normalized

    def _candidate_key_strings(self, fragment_keys: list[tuple[str, str | None, str]]) -> list[str]:
        return [evidence for _, _, evidence in fragment_keys if evidence]

    def _evidence_summaries(self, fragment_keys: list[tuple[str, str | None, str]]) -> list[str]:
        return self._candidate_key_strings(fragment_keys)

    def _priority_index(self, key_name: str | None) -> int:
        if not key_name:
            return 999
        try:
            return self._PRIORITY.index(key_name)
        except ValueError:
            return 999

    def _match_reason(self, key_name: str) -> str:
        mapping = {
            "linkedin_url": "Matched on LinkedIn URL",
            "email": "Matched on normalized email address",
            "phone": "Matched on normalized phone number",
            "github_url": "Matched on GitHub URL",
            "full_name": "Matched on exact full name",
            "full_name_country": "Matched on full name and country",
            "full_name_city": "Matched on full name and city",
        }
        return mapping.get(key_name, "Matched on deterministic identity key")

    def _trace(
        self,
        *,
        stage: str,
        field: str,
        decision_type: str,
        rationale: str,
        rule_or_policy: str,
        confidence: float,
        selected_value: Any,
        candidates_considered: list[str],
    ) -> DecisionTrace:
        return DecisionTrace(
            trace_id=new_uuid_hex(),
            stage=stage,
            field=field,
            decision_type=decision_type,
            candidates_considered=candidates_considered,
            selected_value=selected_value,
            rationale=rationale,
            rule_or_policy=rule_or_policy,
            confidence=confidence,
            resolution_order_step=1,
            fallback_used=decision_type != "match",
            timestamp_utc=datetime.now(UTC),
        )

    def _dedupe_keep_order(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result
