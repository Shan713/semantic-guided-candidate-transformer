from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from datetime import date, datetime
from typing import Any

from src.models.domain_models import (
    CanonicalCandidate,
    OutputCandidate,
    OutputEducation,
    OutputExperience,
    OutputLinks,
    OutputLocation,
    OutputProvenance,
    OutputSkill,
    ProjectionConfig,
    ProjectionRule,
)
from src.models.enums import MissingValueStrategy, ProjectionMode
from src.projection.config_loader import load_projection_config
from src.utils.normalizers import dedupe_keep_order, normalize_email, normalize_phone, normalize_whitespace


class ProjectionEngine:
    """Projection layer that converts CanonicalCandidate into assignment-facing output."""

    def project(
        self,
        candidate: CanonicalCandidate,
        config: ProjectionConfig | dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        projection_config = config if isinstance(config, ProjectionConfig) else load_projection_config(config)
        if projection_config.mode == ProjectionMode.DEFAULT:
            projected = self._project_default(candidate, projection_config)
        else:
            projected = self._project_custom(candidate, projection_config)
        return projected

    def _project_default(self, candidate: CanonicalCandidate, config: ProjectionConfig) -> dict[str, Any]:
        output = OutputCandidate(
            candidate_id=candidate.candidate_id,
            full_name=candidate.full_name,
            emails=[self._email_string(email) for email in candidate.emails if self._email_string(email)],
            phones=[self._phone_string(phone) for phone in candidate.phones if self._phone_string(phone)],
            location=OutputLocation(
                city=candidate.location.city if candidate.location else None,
                region=candidate.location.region if candidate.location else None,
                country=candidate.location.country if candidate.location else None,
            ),
            links=OutputLinks(
                linkedin=candidate.links.linkedin if candidate.links else None,
                github=candidate.links.github if candidate.links else None,
                portfolio=candidate.links.portfolio if candidate.links else None,
                other=list(candidate.links.other) if candidate.links else [],
            ),
            headline=candidate.headline,
            years_experience=candidate.years_experience,
            skills=[OutputSkill(name=skill.name, confidence=skill.confidence, sources=list(skill.sources)) for skill in candidate.skills],
            experience=[
                OutputExperience(
                    company=experience.company_canonical or experience.company,
                    title=experience.title_canonical or experience.title,
                    start=self._serialize_date(experience.start),
                    end=self._serialize_date(experience.end),
                    summary=experience.summary,
                )
                for experience in candidate.experience
            ],
            education=[
                OutputEducation(
                    institution=education.institution,
                    degree=education.degree_canonical or education.degree,
                    field=education.field,
                    end_year=education.end_year,
                )
                for education in candidate.education
            ],
            provenance=[
                OutputProvenance(field=record.field, source=record.source, method=record.method)
                for record in candidate.provenance
            ],
            overall_confidence=candidate.overall_confidence_internal if config.include_confidence else None,
        )
        payload = output.model_dump(mode="json", exclude_none=True)
        if not config.include_provenance:
            payload.pop("provenance", None)
        if not config.include_confidence:
            payload.pop("overall_confidence", None)
        return payload

    def _project_custom(self, candidate: CanonicalCandidate, config: ProjectionConfig) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for rule in config.rules:
            if not rule.enabled:
                continue
            value = self._extract_value(candidate, rule.source_path)
            if value is None or value == []:
                value = self._apply_missing_policy(rule, config.missing_value_strategy)
            if value is None and config.missing_value_strategy == MissingValueStrategy.OMIT and not rule.required:
                continue
            normalized = self._normalize_value(value, rule.transform_hint)
            self._set_path(payload, rule.target_path, normalized)

        if config.include_provenance and "provenance" not in payload:
            payload["provenance"] = [
                OutputProvenance(field=record.field, source=record.source, method=record.method).model_dump(mode="json")
                for record in candidate.provenance
            ]
        if config.include_confidence and "overall_confidence" not in payload:
            payload["overall_confidence"] = candidate.overall_confidence_internal
        return self._prune_nulls(payload, config.missing_value_strategy)

    def _extract_value(self, candidate: CanonicalCandidate, source_path: str) -> Any:
        tokens = source_path.split(".") if source_path else []
        return self._walk_value(candidate, tokens)

    def _walk_value(self, current: Any, tokens: list[str]) -> Any:
        if not tokens:
            return current
        token = tokens[0]
        name, selector = self._parse_token(token)
        current = self._get_attr(current, name)
        if current is None:
            return None
        if selector == "all":
            if not isinstance(current, Sequence) or isinstance(current, (str, bytes)):
                return []
            return [self._walk_value(item, tokens[1:]) for item in current]
        if selector is not None:
            if not isinstance(current, Sequence) or isinstance(current, (str, bytes)):
                return None
            if selector < 0 or selector >= len(current):
                return None
            current = current[selector]
        return self._walk_value(current, tokens[1:])

    def _parse_token(self, token: str) -> tuple[str, int | None | str]:
        if token.endswith("[]"):
            return token[:-2], "all"
        if "[" in token and token.endswith("]"):
            name, index_text = token[:-1].split("[", 1)
            return name, int(index_text)
        return token, None

    def _get_attr(self, value: Any, name: str) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return value.get(name)
        return getattr(value, name, None)

    def _normalize_value(self, value: Any, directive: str | None) -> Any:
        if directive is None:
            if isinstance(value, list):
                return self._json_safe([self._coerce_scalar(item) for item in value])
            return self._json_safe(self._coerce_scalar(value))
        normalized_directive = directive.strip().lower()
        if isinstance(value, list):
            normalized_items = [self._normalize_scalar(item, normalized_directive) for item in value]
            return self._json_safe(dedupe_keep_order([item for item in normalized_items if item is not None]))
        return self._json_safe(self._normalize_scalar(value, normalized_directive))

    def _coerce_scalar(self, value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "normalized") and getattr(value, "normalized"):
            return normalize_email(getattr(value, "normalized"))
        if hasattr(value, "normalized_e164") and getattr(value, "normalized_e164"):
            return normalize_phone(getattr(value, "normalized_e164"), None)
        if hasattr(value, "value") and getattr(value, "value"):
            return normalize_whitespace(str(getattr(value, "value")))
        if hasattr(value, "raw") and getattr(value, "raw"):
            return normalize_whitespace(str(getattr(value, "raw")))
        if hasattr(value, "name") and getattr(value, "name"):
            return normalize_whitespace(str(getattr(value, "name")))
        return value

    def _normalize_scalar(self, value: Any, directive: str) -> Any:
        if value is None:
            return None
        if directive == "e164":
            return self._normalize_phone_value(value)
        if directive == "canonical":
            if hasattr(value, "name"):
                return normalize_whitespace(getattr(value, "name"))
            if isinstance(value, dict) and "name" in value:
                return normalize_whitespace(value.get("name"))
            return normalize_whitespace(str(value))
        if directive == "iso3166":
            return self._normalize_iso3166(value)
        return self._json_safe(value)

    def _normalize_phone_value(self, value: Any) -> str | None:
        if hasattr(value, "normalized_e164") and getattr(value, "normalized_e164"):
            return normalize_phone(getattr(value, "normalized_e164"), None)
        if hasattr(value, "raw") and getattr(value, "raw"):
            return normalize_phone(getattr(value, "raw"), None)
        return normalize_phone(str(value), None)

    def _normalize_iso3166(self, value: Any) -> str | None:
        if hasattr(value, "country_code") and getattr(value, "country_code"):
            return normalize_whitespace(str(getattr(value, "country_code"))).upper()
        if isinstance(value, dict) and value.get("country_code"):
            return normalize_whitespace(str(value.get("country_code"))).upper()
        text = normalize_whitespace(str(value)) if value is not None else None
        if not text:
            return None
        country_map = {
            "united states": "US",
            "usa": "US",
            "us": "US",
            "india": "IN",
            "germany": "DE",
            "united kingdom": "GB",
            "uk": "GB",
            "canada": "CA",
        }
        return country_map.get(text.lower(), text.upper())

    def _apply_missing_policy(self, rule: ProjectionRule, strategy: MissingValueStrategy) -> Any:
        if strategy == MissingValueStrategy.NULL:
            return None
        if strategy == MissingValueStrategy.OMIT:
            return None
        raise ValueError(f"Missing projected field: {rule.target_path}")

    def _set_path(self, payload: dict[str, Any], path: str, value: Any) -> None:
        if "." not in path:
            payload[path] = value
            return
        current = payload
        parts = path.split(".")
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value

    def _prune_nulls(self, value: Any, strategy: MissingValueStrategy) -> Any:
        if strategy != MissingValueStrategy.OMIT:
            return value
        if isinstance(value, dict):
            return {k: self._prune_nulls(v, strategy) for k, v in value.items() if v is not None}
        if isinstance(value, list):
            return [self._prune_nulls(item, strategy) for item in value if item is not None]
        return value

    def _json_safe(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {key: self._json_safe(item) for key, item in value.items()}
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json", exclude_none=True)
        if hasattr(value, "__dict__"):
            return {key: self._json_safe(item) for key, item in vars(value).items() if not key.startswith("_")}
        return str(value)

    def _email_string(self, value: Any) -> str | None:
        if hasattr(value, "normalized") and getattr(value, "normalized"):
            return normalize_email(getattr(value, "normalized"))
        if hasattr(value, "value") and getattr(value, "value"):
            return normalize_email(getattr(value, "value"))
        return normalize_email(str(value))

    def _phone_string(self, value: Any) -> str | None:
        if hasattr(value, "normalized_e164") and getattr(value, "normalized_e164"):
            return normalize_phone(getattr(value, "normalized_e164"), None)
        if hasattr(value, "raw") and getattr(value, "raw"):
            return normalize_phone(getattr(value, "raw"), None)
        return normalize_phone(str(value), None)

    def _serialize_date(self, value: date | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()
