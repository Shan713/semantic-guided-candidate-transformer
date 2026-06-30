from __future__ import annotations

from collections import OrderedDict
from difflib import SequenceMatcher
from datetime import datetime, UTC
from typing import Any

from src.interfaces.base_fusion_engine import BaseFusionEngine
from src.models.domain_models import (
    CandidateFragment,
    CanonicalCandidate,
    DecisionTrace,
    Education,
    Email,
    Experience,
    Links,
    Location,
    MergeDecision,
    Phone,
    Skill,
)
from src.transformation.config import load_transformation_config_bundle
from src.utils.ids import deterministic_candidate_id, new_uuid_hex
from src.utils.normalizers import dedupe_keep_order, normalize_email, normalize_phone, normalize_whitespace


class CandidateFusionEngine(BaseFusionEngine):
    """Deterministically fuse a cluster of semantic fragments into a canonical candidate."""

    def __init__(self, config_bundle: dict[str, Any] | None = None) -> None:
        self.config_bundle = config_bundle or load_transformation_config_bundle()
        fusion_config = self.config_bundle.get("fusion", {})
        self.merge_policies = fusion_config.get("merge_policies", {})
        source_config = self.config_bundle.get("source_reliability", {})
        self.source_reliability = source_config.get("reliability", {})
        self.field_overrides = source_config.get("field_overrides", {})

    def fuse(self, fragments: list[CandidateFragment], context) -> CanonicalCandidate:
        if not fragments:
            raise ValueError("CandidateFusionEngine requires at least one fragment")

        full_name = self._merge_full_name(fragments)
        emails, email_decision = self._merge_emails(fragments)
        phones, phone_decision = self._merge_phones(fragments)
        links, link_decision = self._merge_links(fragments)
        skills, skill_decision = self._merge_skills(fragments)
        experience, experience_decision = self._merge_experience(fragments)
        education, education_decision = self._merge_education(fragments)
        location, location_decision = self._merge_location(fragments)
        years_experience, years_decision = self._merge_years_experience(fragments)
        headline, headline_decision = self._merge_headline(fragments)

        merge_decisions = [
            email_decision,
            phone_decision,
            link_decision,
            skill_decision,
            experience_decision,
            education_decision,
            location_decision,
            years_decision,
            headline_decision,
        ]

        candidate_id = self._candidate_id(fragments, full_name, emails, phones)
        return CanonicalCandidate(
            candidate_id=candidate_id,
            full_name=full_name,
            emails=emails,
            phones=phones,
            location=location,
            links=links,
            headline=headline,
            years_experience=years_experience,
            skills=skills,
            experience=experience,
            education=education,
            field_evidence=[],
            provenance=[],
            confidence_records=[],
            transformation_history=[],
            merge_decisions=merge_decisions,
            decision_trace=[],
            source_summaries=[],
            overall_confidence_internal=0.0,
            finalized_at_utc=datetime.now(UTC),
        )

    def _candidate_id(
        self,
        fragments: list[CandidateFragment],
        full_name: str | None,
        emails: list[Email],
        phones: list[Phone],
    ) -> str:
        if fragments:
            candidate_id = fragments[0].external_candidate_id
            if candidate_id:
                return candidate_id
        email_value = emails[0].normalized if emails else ""
        phone_value = phones[0].normalized_e164 if phones else ""
        return deterministic_candidate_id(full_name or "", email_value or "", phone_value or "", *(fragment.fragment_id for fragment in fragments))

    def _merge_full_name(self, fragments: list[CandidateFragment]) -> str | None:
        candidates: list[tuple[float, int, str]] = []
        for index, fragment in enumerate(fragments):
            if fragment.full_name:
                candidates.append((self._source_reliability(fragment, "full_name"), -index, fragment.full_name))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return normalize_whitespace(candidates[0][2])

    def _merge_emails(self, fragments: list[CandidateFragment]) -> tuple[list[Email], MergeDecision]:
        merged: OrderedDict[str, Email] = OrderedDict()
        competing: list[str] = []
        for fragment in fragments:
            for email in fragment.emails:
                normalized = normalize_email(email.normalized or email.value)
                if not normalized:
                    continue
                competing.append(normalized)
                if normalized not in merged:
                    merged[normalized] = Email(
                        value=email.value,
                        normalized=normalized,
                        is_primary=email.is_primary,
                        confidence=max(email.confidence, self._source_reliability(fragment, "emails")),
                        evidence_ids=list(email.evidence_ids),
                    )
                else:
                    merged_email = merged[normalized]
                    merged_email.evidence_ids = dedupe_keep_order(merged_email.evidence_ids + list(email.evidence_ids))
                    merged_email.confidence = max(merged_email.confidence, email.confidence, self._source_reliability(fragment, "emails"))
        return list(merged.values()), self._merge_decision(
            entity="candidate",
            field="emails",
            strategy=self._strategy_for_field("emails", default="union"),
            competing_values=competing,
            selected_value=[email.normalized for email in merged.values()],
            reason_codes=["strong_cross_source_agreement"] if len(merged) > 1 else ["high_source_reliability"],
        )

    def _merge_phones(self, fragments: list[CandidateFragment]) -> tuple[list[Phone], MergeDecision]:
        merged: OrderedDict[str, Phone] = OrderedDict()
        competing: list[str] = []
        for fragment in fragments:
            for phone in fragment.phones:
                normalized = phone.normalized_e164 or normalize_phone(phone.raw, None)
                if not normalized:
                    continue
                competing.append(normalized)
                if normalized not in merged:
                    merged[normalized] = Phone(
                        raw=phone.raw,
                        normalized_e164=normalized,
                        country_code=phone.country_code,
                        is_primary=phone.is_primary,
                        confidence=max(phone.confidence, self._source_reliability(fragment, "phones")),
                        evidence_ids=list(phone.evidence_ids),
                    )
                else:
                    merged_phone = merged[normalized]
                    merged_phone.evidence_ids = dedupe_keep_order(merged_phone.evidence_ids + list(phone.evidence_ids))
                    merged_phone.confidence = max(merged_phone.confidence, phone.confidence, self._source_reliability(fragment, "phones"))
        return list(merged.values()), self._merge_decision(
            entity="candidate",
            field="phones",
            strategy=self._strategy_for_field("phones", default="union"),
            competing_values=competing,
            selected_value=[phone.normalized_e164 for phone in merged.values()],
            reason_codes=["strong_cross_source_agreement"] if len(merged) > 1 else ["high_source_reliability"],
        )

    def _merge_links(self, fragments: list[CandidateFragment]) -> tuple[Links, MergeDecision]:
        linkedin: str | None = None
        github: str | None = None
        portfolio: str | None = None
        other: list[str] = []
        seen_links: set[str] = set()
        competing: list[str] = []

        for fragment in fragments:
            if not fragment.links:
                continue
            for label, value in (("linkedin", fragment.links.linkedin), ("github", fragment.links.github), ("portfolio", fragment.links.portfolio)):
                if value:
                    normalized = self._normalize_link(value)
                    competing.append(value)
                    if normalized in seen_links:
                        continue
                    if label == "linkedin" and not linkedin:
                        linkedin = value
                        seen_links.add(normalized)
                    elif label == "github" and not github:
                        github = value
                        seen_links.add(normalized)
                    elif label == "portfolio" and not portfolio:
                        portfolio = value
                        seen_links.add(normalized)
                    else:
                        other.append(value)
                        seen_links.add(normalized)
            other.extend(fragment.links.other)

        unique_other: list[str] = []
        for value in dedupe_keep_order([value for value in other if value]):
            normalized = self._normalize_link(value)
            if normalized in seen_links:
                continue
            seen_links.add(normalized)
            unique_other.append(value)
        return (
            Links(linkedin=linkedin, github=github, portfolio=portfolio, other=unique_other),
            self._merge_decision(
                entity="candidate",
                field="links",
                strategy=self._strategy_for_field("links", default="union"),
                competing_values=competing,
                selected_value={"linkedin": linkedin, "github": github, "portfolio": portfolio, "other": unique_other},
                reason_codes=["strong_cross_source_agreement"] if len(competing) > 1 else ["high_source_reliability"],
            ),
        )

    def _merge_skills(self, fragments: list[CandidateFragment]) -> tuple[list[Skill], MergeDecision]:
        merged: OrderedDict[str, Skill] = OrderedDict()
        competing: list[str] = []
        for fragment in fragments:
            for skill in fragment.skills:
                canonical_name = normalize_whitespace(skill.name) or skill.name
                key = canonical_name.lower()
                competing.append(canonical_name)
                if key not in merged:
                    merged[key] = Skill(
                        name=canonical_name,
                        original_names=list(skill.original_names),
                        category=skill.category,
                        parent_category=skill.parent_category,
                        confidence=max(skill.confidence, self._source_reliability(fragment, "skills")),
                        sources=list(skill.sources),
                        evidence_ids=list(skill.evidence_ids),
                    )
                else:
                    merged_skill = merged[key]
                    merged_skill.original_names = dedupe_keep_order(merged_skill.original_names + list(skill.original_names))
                    merged_skill.sources = dedupe_keep_order(merged_skill.sources + list(skill.sources))
                    merged_skill.evidence_ids = dedupe_keep_order(merged_skill.evidence_ids + list(skill.evidence_ids))
                    merged_skill.confidence = max(merged_skill.confidence, skill.confidence, self._source_reliability(fragment, "skills"))
        return list(merged.values()), self._merge_decision(
            entity="candidate",
            field="skills",
            strategy=self._strategy_for_field("skills", default="semantic_union"),
            competing_values=competing,
            selected_value=[skill.name for skill in merged.values()],
            reason_codes=["semantic_alias_match"] if len(merged) else ["missing_evidence"],
        )

    def _merge_experience(self, fragments: list[CandidateFragment]) -> tuple[list[Experience], MergeDecision]:
        merged: list[Experience] = []
        competing: list[str] = []
        for fragment in fragments:
            for experience in fragment.experience:
                company_key = experience.company_canonical or experience.company
                title_key = experience.title_canonical or experience.title
                competing.append(f"{company_key}|{title_key}|{experience.start}|{experience.end}")
                matched = next((item for item in merged if self._experiences_match(item, experience)), None)
                if matched is None:
                    merged.append(
                        Experience(
                            company=self._preferred_experience_company(None, experience),
                            company_canonical=experience.company_canonical,
                            title=self._preferred_experience_title(None, experience),
                            title_canonical=experience.title_canonical,
                            start=experience.start,
                            end=experience.end,
                            summary=experience.summary,
                            location=experience.location,
                            confidence=max(experience.confidence, self._source_reliability(fragment, "experience")),
                            evidence_ids=list(experience.evidence_ids),
                        )
                    )
                    continue
                matched.company = self._preferred_experience_company(matched, experience)
                matched.company_canonical = matched.company_canonical or experience.company_canonical
                matched.title = self._preferred_experience_title(matched, experience)
                matched.title_canonical = matched.title_canonical or experience.title_canonical
                matched.start = self._earliest_date(matched.start, experience.start)
                matched.end = self._latest_date(matched.end, experience.end)
                matched.summary = self._merge_text(matched.summary, experience.summary)
                matched.location = self._merge_experience_location(matched.location, experience.location)
                matched.evidence_ids = dedupe_keep_order(matched.evidence_ids + list(experience.evidence_ids))
                matched.confidence = max(matched.confidence, experience.confidence, self._source_reliability(fragment, "experience"))

        sorted_experience = sorted(
            merged,
            key=lambda item: (item.start is None, item.start or item.end or datetime.max.date()),
        )
        return sorted_experience, self._merge_decision(
            entity="candidate",
            field="experience",
            strategy=self._strategy_for_field("experience", default="chronological_merge"),
            competing_values=competing,
            selected_value=[experience.model_dump() for experience in sorted_experience],
            reason_codes=["strong_cross_source_agreement"] if len(sorted_experience) > 1 else ["high_source_reliability"],
        )

    def _merge_education(self, fragments: list[CandidateFragment]) -> tuple[list[Education], MergeDecision]:
        merged: list[Education] = []
        competing: list[str] = []
        for fragment in fragments:
            for education in fragment.education:
                competing.append("|".join(str(part) for part in (
                    education.institution,
                    education.degree_canonical or education.degree,
                    education.field,
                    education.start_year,
                    education.end_year,
                )))
                matched = next((item for item in merged if self._educations_match(item, education)), None)
                if matched is None:
                    merged.append(
                        Education(
                            institution=education.institution,
                            degree=education.degree,
                            degree_canonical=education.degree_canonical,
                            field=education.field,
                            start_year=education.start_year,
                            end_year=education.end_year,
                            confidence=max(education.confidence, self._source_reliability(fragment, "education")),
                            evidence_ids=list(education.evidence_ids),
                        )
                    )
                    continue
                matched.institution = self._preferred_education_institution(matched, education)
                matched.degree = self._preferred_education_degree(matched, education)
                matched.degree_canonical = matched.degree_canonical or education.degree_canonical
                matched.field = matched.field or education.field
                matched.start_year = self._earliest_year(matched.start_year, education.start_year)
                matched.end_year = self._latest_year(matched.end_year, education.end_year)
                matched.evidence_ids = dedupe_keep_order(matched.evidence_ids + list(education.evidence_ids))
                matched.confidence = max(matched.confidence, education.confidence, self._source_reliability(fragment, "education"))

        sorted_education = sorted(
            merged,
            key=lambda item: (
                item.end_year is None,
                -(item.end_year or item.start_year or 0),
                item.institution.lower(),
                item.degree.lower(),
            ),
        )
        return sorted_education, self._merge_decision(
            entity="candidate",
            field="education",
            strategy=self._strategy_for_field("education", default="merge"),
            competing_values=competing,
            selected_value=[education.model_dump() for education in sorted_education],
            reason_codes=["strong_cross_source_agreement"] if len(sorted_education) > 1 else ["high_source_reliability"],
        )

    def _merge_location(self, fragments: list[CandidateFragment]) -> tuple[Location | None, MergeDecision]:
        best_location: Location | None = None
        best_score = -1
        best_source_score = -1.0
        competing: list[str] = []
        for index, fragment in enumerate(fragments):
            location = fragment.location
            if not location:
                continue
            competing.append(location.raw or self._location_string(location))
            score = self._location_completeness(location)
            source_score = self._source_reliability(fragment, "location")
            if score > best_score or (score == best_score and source_score > best_source_score):
                best_score = score
                best_source_score = source_score
                best_location = Location(
                    raw=location.raw,
                    city=location.city,
                    region=location.region,
                    country=location.country,
                    country_code=self._normalize_country_code(location.country_code),
                    confidence=max(location.confidence, source_score),
                    evidence_ids=list(location.evidence_ids),
                )
        return best_location, self._merge_decision(
            entity="candidate",
            field="location",
            strategy=self._strategy_for_field("location", default="most_complete"),
            competing_values=competing,
            selected_value=best_location.model_dump() if best_location else None,
            reason_codes=["strong_cross_source_agreement"] if len(competing) > 1 else ["high_source_reliability"],
        )

    def _merge_years_experience(self, fragments: list[CandidateFragment]) -> tuple[float | None, MergeDecision]:
        competing: list[float] = []
        best_value: float | None = None
        best_source = -1.0
        for fragment in fragments:
            if fragment.years_experience is None:
                continue
            competing.append(fragment.years_experience)
            source_score = self._source_reliability(fragment, "years_experience")
            if best_value is None or fragment.years_experience > best_value or (
                fragment.years_experience == best_value and source_score > best_source
            ):
                best_value = fragment.years_experience
                best_source = source_score
        return best_value, self._merge_decision(
            entity="candidate",
            field="years_experience",
            strategy=self._strategy_for_field("years_experience", default="maximum_verified"),
            competing_values=competing,
            selected_value=best_value,
            reason_codes=["strong_cross_source_agreement"] if len(competing) > 1 else ["high_source_reliability"],
        )

    def _merge_headline(self, fragments: list[CandidateFragment]) -> tuple[str | None, MergeDecision]:
        candidates: list[tuple[float, int, str]] = []
        competing: list[str] = []
        for index, fragment in enumerate(fragments):
            if fragment.headline:
                source_score = self._source_reliability(fragment, "headline")
                candidates.append((source_score, -index, fragment.headline))
                competing.append(fragment.headline)
        if not candidates:
            return None, self._merge_decision(
                entity="candidate",
                field="headline",
                strategy=self._strategy_for_field("headline", default="highest_confidence"),
                competing_values=competing,
                selected_value=None,
                reason_codes=["missing_evidence"],
            )
        candidates.sort(reverse=True)
        selected = normalize_whitespace(candidates[0][2])
        return selected, self._merge_decision(
            entity="candidate",
            field="headline",
            strategy=self._strategy_for_field("headline", default="highest_confidence"),
            competing_values=competing,
            selected_value=selected,
            reason_codes=["high_source_reliability"],
        )

    def _merge_decision(
        self,
        *,
        entity: str,
        field: str,
        strategy: str,
        competing_values: list[Any],
        selected_value: Any,
        reason_codes: list[str],
    ) -> MergeDecision:
        if isinstance(selected_value, list):
            rejected_values = [value for value in competing_values if value not in selected_value]
        elif isinstance(selected_value, dict):
            selected_values = list(selected_value.values())
            rejected_values = [value for value in competing_values if value not in selected_values]
        else:
            rejected_values = [value for value in competing_values if value != selected_value]
        return MergeDecision(
            decision_id=new_uuid_hex(),
            entity=entity,
            field=field,
            strategy=strategy,
            competing_values=competing_values,
            selected_value=selected_value,
            rejected_values=rejected_values,
            reason_codes=reason_codes,
            confidence=1.0 if selected_value is not None else 0.0,
            timestamp_utc=datetime.now(UTC),
        )

    def _strategy_for_field(self, field: str, default: str) -> str:
        value = self.merge_policies.get(field)
        if isinstance(value, str) and value:
            return value
        return default

    def _source_reliability(self, fragment: CandidateFragment, field_name: str | None = None) -> float:
        source_name = self._source_name(fragment)
        base = float(self.source_reliability.get(source_name, 0.5))
        if not field_name:
            return base
        override = self.field_overrides.get(source_name, {}).get(field_name)
        if override is not None:
            return float(override)
        return base

    def _source_name(self, fragment: CandidateFragment) -> str:
        if fragment.source_metadata and fragment.source_metadata.source_name:
            source = fragment.source_metadata.source_name
            return source.value if hasattr(source, "value") else str(source)
        return "unknown"

    def _merge_text(self, left: str | None, right: str | None) -> str | None:
        if left and right:
            left_parts = [part for part in (normalize_whitespace(piece) for piece in left.split(" | ")) if part]
            right_parts = [part for part in (normalize_whitespace(piece) for piece in right.split(" | ")) if part]
            merged = dedupe_keep_order([*left_parts, *right_parts])
            if not merged:
                return None
            if len(merged) == 1:
                return merged[0]
            return " | ".join(merged)
        return left or right

    def _preferred_experience_company(self, current: Experience | None, incoming: Experience) -> str:
        incoming_value = incoming.company_canonical or incoming.company
        if incoming.company_canonical:
            return normalize_whitespace(incoming_value) or ""
        current_value = current.company if current else None
        if current and current.company_canonical:
            return normalize_whitespace(current.company_canonical) or current_value or ""
        return self._prefer_text_value(current_value, incoming_value)

    def _preferred_experience_title(self, current: Experience | None, incoming: Experience) -> str:
        incoming_value = incoming.title_canonical or incoming.title
        if incoming.title_canonical:
            return normalize_whitespace(incoming_value) or ""
        current_value = current.title if current else None
        if current and current.title_canonical:
            return normalize_whitespace(current.title_canonical) or current_value or ""
        return self._prefer_text_value(current_value, incoming_value)

    def _preferred_education_institution(self, current: Education | None, incoming: Education) -> str:
        current_value = current.institution if current else None
        return self._prefer_text_value(current_value, incoming.institution)

    def _preferred_education_degree(self, current: Education | None, incoming: Education) -> str:
        incoming_value = incoming.degree_canonical or incoming.degree
        if incoming.degree_canonical:
            return normalize_whitespace(incoming.degree_canonical) or ""
        current_value = current.degree if current else None
        if current and current.degree_canonical:
            return normalize_whitespace(current.degree_canonical) or current_value or ""
        return self._prefer_text_value(current_value, incoming_value)

    def _prefer_text_value(self, current: str | None, incoming: str | None) -> str:
        current_text = normalize_whitespace(current) if current else None
        incoming_text = normalize_whitespace(incoming) if incoming else None
        if not current_text:
            return incoming_text or ""
        if not incoming_text:
            return current_text
        if len(incoming_text) > len(current_text):
            return incoming_text
        return current_text

    def _merge_experience_location(self, current: Location | None, incoming: Location | None) -> Location | None:
        if current is None:
            return incoming
        if incoming is None:
            return current
        return Location(
            raw=current.raw or incoming.raw,
            city=current.city or incoming.city,
            region=current.region or incoming.region,
            country=current.country or incoming.country,
            country_code=current.country_code or incoming.country_code,
            confidence=max(current.confidence, incoming.confidence),
            evidence_ids=dedupe_keep_order([*current.evidence_ids, *incoming.evidence_ids]),
        )

    def _experiences_match(self, left: Experience, right: Experience) -> bool:
        left_company = self._experience_key_value(left.company_canonical or left.company)
        right_company = self._experience_key_value(right.company_canonical or right.company)
        left_title = self._experience_key_value(left.title_canonical or left.title)
        right_title = self._experience_key_value(right.title_canonical or right.title)
        company_match = bool(left_company and right_company and left_company == right_company)
        title_match = bool(left_title and right_title and left_title == right_title)
        date_overlap = self._date_ranges_overlap(left.start, left.end, right.start, right.end)
        summary_similarity = self._text_similarity(left.summary, right.summary)
        location_match = self._locations_match(left.location, right.location)
        return (
            company_match and (title_match or date_overlap or summary_similarity >= 0.82)
        ) or (
            title_match and date_overlap and (summary_similarity >= 0.70 or location_match)
        )

    def _educations_match(self, left: Education, right: Education) -> bool:
        left_institution = self._experience_key_value(left.institution)
        right_institution = self._experience_key_value(right.institution)
        institution_match = bool(left_institution and right_institution and left_institution == right_institution)
        left_degree = self._experience_key_value(left.degree_canonical or left.degree)
        right_degree = self._experience_key_value(right.degree_canonical or right.degree)
        degree_match = bool(left_degree and right_degree and left_degree == right_degree)
        field_match = bool(
            left.field
            and right.field
            and self._experience_key_value(left.field) == self._experience_key_value(right.field)
        )
        period_match = self._education_period_match(left.start_year, left.end_year, right.start_year, right.end_year)
        return institution_match and (degree_match or field_match or period_match)

    def _experience_key_value(self, value: str | None) -> str | None:
        normalized = normalize_whitespace(value)
        return normalized.lower() if normalized else None

    def _date_ranges_overlap(self, left_start, left_end, right_start, right_end) -> bool:
        left_begin = left_start or left_end
        left_finish = left_end
        right_begin = right_start or right_end
        right_finish = right_end
        if left_begin and right_finish and left_begin > right_finish:
            return False
        if right_begin and left_finish and right_begin > left_finish:
            return False
        return True

    def _education_period_match(self, left_start: int | None, left_end: int | None, right_start: int | None, right_end: int | None) -> bool:
        if left_start is None and left_end is None:
            return True
        if right_start is None and right_end is None:
            return True
        start_match = left_start is None or right_start is None or left_start == right_start
        end_match = left_end is None or right_end is None or left_end == right_end
        return start_match and end_match

    def _text_similarity(self, left: str | None, right: str | None) -> float:
        left_text = normalize_whitespace(left) if left else None
        right_text = normalize_whitespace(right) if right else None
        if not left_text or not right_text:
            return 0.0
        return SequenceMatcher(None, left_text.lower(), right_text.lower()).ratio()

    def _locations_match(self, left: Location | None, right: Location | None) -> bool:
        if not left or not right:
            return False
        left_key = self._location_string(left).lower()
        right_key = self._location_string(right).lower()
        return bool(left_key and right_key and left_key == right_key)

    def _earliest_date(self, left, right):
        if left is None:
            return right
        if right is None:
            return left
        return min(left, right)

    def _latest_date(self, left, right):
        if left is None:
            return right
        if right is None:
            return left
        return max(left, right)

    def _earliest_year(self, left: int | None, right: int | None) -> int | None:
        if left is None:
            return right
        if right is None:
            return left
        return min(left, right)

    def _latest_year(self, left: int | None, right: int | None) -> int | None:
        if left is None:
            return right
        if right is None:
            return left
        return max(left, right)

    def _normalize_country_code(self, value: str | None) -> str | None:
        if not value:
            return None
        text = normalize_whitespace(value)
        if not text:
            return None
        if len(text) in {2, 3} and text.isalpha():
            return text.upper()
        return None

    def _location_completeness(self, location: Location) -> int:
        return sum(
            1
            for value in (location.city, location.region, location.country or location.country_code)
            if value and str(value).strip()
        )

    def _location_string(self, location: Location) -> str:
        parts = [location.city, location.region, location.country or location.country_code]
        return ", ".join(part for part in parts if part)

    def _normalize_link(self, value: str) -> str:
        text = value.strip()
        if not text:
            return text
        if not text.startswith(("http://", "https://")):
            text = f"https://{text.lstrip('/')}"
        from urllib.parse import urlsplit, urlunsplit

        split = urlsplit(text)
        netloc = split.netloc.lower().removeprefix("www.")
        path = split.path.rstrip("/")
        normalized = urlunsplit((split.scheme.lower(), netloc, path, split.query, split.fragment))
        return normalized.lower()
