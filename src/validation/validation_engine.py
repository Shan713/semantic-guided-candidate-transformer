from __future__ import annotations

import re
from typing import Any

from src.models.domain_models import ProjectionConfig
from src.models.enums import MissingValueStrategy, ProjectionMode
from src.models.validation_models import ValidationIssue, ValidationResult


class ValidationEngine:
    """Validates projected JSON-compatible output without raising on recoverable issues."""

    def validate(self, payload: dict[str, Any], config: ProjectionConfig | None = None) -> ValidationResult:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []

        if not isinstance(payload, dict):
            errors.append(
                ValidationIssue(
                    path="$",
                    code="invalid_payload_type",
                    message="Projected output must be a dictionary.",
                    expected="dict",
                    actual=type(payload).__name__,
                )
            )
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        if config is None or config.mode == ProjectionMode.DEFAULT:
            self._validate_default_schema(payload, config, errors, warnings)
        else:
            self._validate_custom_schema(payload, config, errors, warnings)

        return ValidationResult(is_valid=not errors, errors=errors, warnings=warnings)

    def _validate_default_schema(
        self,
        payload: dict[str, Any],
        config: ProjectionConfig | None,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
    ) -> None:
        required_fields = ["candidate_id", "emails", "phones", "skills"]
        if config and config.include_provenance:
            required_fields.append("provenance")
        if config and config.include_confidence:
            required_fields.append("overall_confidence")

        for field in required_fields:
            if field not in payload or payload[field] in (None, [], {}):
                errors.append(
                    ValidationIssue(
                        path=field,
                        code="missing_required_field",
                        message=f"Required field '{field}' is missing.",
                        expected="present",
                        actual="missing",
                    )
                )

        self._check_list(payload, "emails", str, errors)
        self._check_list(payload, "phones", str, errors)
        self._check_list(payload, "skills", dict, errors)
        self._check_list(payload, "experience", dict, errors)
        self._check_list(payload, "education", dict, errors)
        self._check_list(payload, "provenance", dict, errors)

        location = payload.get("location")
        if location is not None and not isinstance(location, dict):
            errors.append(
                ValidationIssue(
                    path="location",
                    code="invalid_nested_object",
                    message="Location must be a nested object.",
                    expected="dict",
                    actual=type(location).__name__,
                )
            )

        self._check_phone_format(payload, errors)
        self._check_iso_country_code(payload, errors)
        self._check_date_format(payload, errors)

    def _validate_custom_schema(
        self,
        payload: dict[str, Any],
        config: ProjectionConfig,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
    ) -> None:
        for rule in config.rules:
            value = self._get_path(payload, rule.target_path)
            if value in (None, [], {}):
                if rule.required:
                    errors.append(
                        ValidationIssue(
                            path=rule.target_path,
                            code="missing_required_field",
                            message=f"Required field '{rule.target_path}' is missing.",
                            expected=rule.transform_hint or rule.operation,
                            actual="missing",
                        )
                    )
                continue

            if isinstance(value, list) and not value and rule.required:
                errors.append(
                    ValidationIssue(
                        path=rule.target_path,
                        code="missing_required_field",
                        message=f"Required field '{rule.target_path}' is empty.",
                        expected=rule.transform_hint or rule.operation,
                        actual="empty_list",
                    )
                )

            if rule.transform_hint and rule.transform_hint.lower() == "e164":
                self._validate_e164_value(value, rule.target_path, errors)
            if rule.transform_hint and rule.transform_hint.lower() == "iso3166":
                self._validate_iso3166_value(value, rule.target_path, errors)

        if config.include_confidence and "overall_confidence" in payload and not isinstance(payload["overall_confidence"], (int, float)):
            errors.append(
                ValidationIssue(
                    path="overall_confidence",
                    code="invalid_type",
                    message="overall_confidence must be numeric.",
                    expected="number",
                    actual=type(payload["overall_confidence"]).__name__,
                )
            )

    def _check_list(self, payload: dict[str, Any], field: str, item_type: type, errors: list[ValidationIssue]) -> None:
        if field not in payload:
            return
        value = payload[field]
        if value is None:
            return
        if not isinstance(value, list):
            errors.append(
                ValidationIssue(
                    path=field,
                    code="invalid_type",
                    message=f"Field '{field}' must be a list.",
                    expected="list",
                    actual=type(value).__name__,
                )
            )
            return
        for index, item in enumerate(value):
            if not isinstance(item, item_type):
                errors.append(
                    ValidationIssue(
                        path=f"{field}[{index}]",
                        code="invalid_item_type",
                        message=f"Items in '{field}' must be of type {item_type.__name__}.",
                        expected=item_type.__name__,
                        actual=type(item).__name__,
                    )
                )

    def _check_phone_format(self, payload: dict[str, Any], errors: list[ValidationIssue]) -> None:
        phones = payload.get("phones")
        if not isinstance(phones, list):
            return
        pattern = re.compile(r"^\+[1-9]\d{1,14}$")
        for index, phone in enumerate(phones):
            if isinstance(phone, str) and not pattern.match(phone):
                errors.append(
                    ValidationIssue(
                        path=f"phones[{index}]",
                        code="invalid_phone_format",
                        message="Phone must be normalized to E164.",
                        expected="E164",
                        actual=phone,
                    )
                )

    def _check_iso_country_code(self, payload: dict[str, Any], errors: list[ValidationIssue]) -> None:
        location = payload.get("location")
        if not isinstance(location, dict):
            return
        country_code = location.get("country_code")
        if country_code is None:
            return
        if not isinstance(country_code, str) or not re.fullmatch(r"[A-Z]{2}", country_code):
            errors.append(
                ValidationIssue(
                    path="location.country_code",
                    code="invalid_country_code",
                    message="Country code must be ISO-3166 alpha-2.",
                    expected="ISO-3166 alpha-2",
                    actual=str(country_code),
                )
            )

    def _check_date_format(self, payload: dict[str, Any], errors: list[ValidationIssue]) -> None:
        experience = payload.get("experience")
        if not isinstance(experience, list):
            return
        pattern = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
        for exp_index, item in enumerate(experience):
            if not isinstance(item, dict):
                continue
            for field in ("start", "end"):
                value = item.get(field)
                if value is not None and isinstance(value, str) and not pattern.fullmatch(value):
                    errors.append(
                        ValidationIssue(
                            path=f"experience[{exp_index}].{field}",
                            code="invalid_date_format",
                            message="Dates must be ISO-formatted strings.",
                            expected="YYYY or YYYY-MM or YYYY-MM-DD",
                            actual=value,
                        )
                    )

    def _validate_e164_value(self, value: Any, path: str, errors: list[ValidationIssue]) -> None:
        pattern = re.compile(r"^\+[1-9]\d{1,14}$")
        values = value if isinstance(value, list) else [value]
        for index, item in enumerate(values):
            if item is None:
                continue
            if not isinstance(item, str) or not pattern.fullmatch(item):
                errors.append(
                    ValidationIssue(
                        path=f"{path}[{index}]" if isinstance(value, list) else path,
                        code="invalid_phone_format",
                        message="Value must be normalized to E164.",
                        expected="E164",
                        actual=str(item),
                    )
                )

    def _validate_iso3166_value(self, value: Any, path: str, errors: list[ValidationIssue]) -> None:
        values = value if isinstance(value, list) else [value]
        for index, item in enumerate(values):
            if item is None:
                continue
            if not isinstance(item, str) or not re.fullmatch(r"[A-Z]{2}", item):
                errors.append(
                    ValidationIssue(
                        path=f"{path}[{index}]" if isinstance(value, list) else path,
                        code="invalid_country_code",
                        message="Value must be ISO-3166 alpha-2.",
                        expected="ISO-3166 alpha-2",
                        actual=str(item),
                    )
                )

    def _get_path(self, payload: dict[str, Any], path: str) -> Any:
        current: Any = payload
        for token in path.split("."):
            if current is None:
                return None
            name, selector = self._parse_token(token)
            current = current.get(name) if isinstance(current, dict) else None
            if selector is None:
                continue
            if not isinstance(current, list):
                return None
            if selector == "all":
                return current
            if selector < 0 or selector >= len(current):
                return None
            current = current[selector]
        return current

    def _parse_token(self, token: str) -> tuple[str, int | str | None]:
        if token.endswith("[]"):
            return token[:-2], "all"
        if "[" in token and token.endswith("]"):
            name, index_text = token[:-1].split("[", 1)
            return name, int(index_text)
        return token, None
