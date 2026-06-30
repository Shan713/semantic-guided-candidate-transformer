from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src.core.constants import CONFIG_DIR
from src.models.domain_models import ProjectionConfig, ProjectionRule
from src.models.enums import MissingValueStrategy, ProjectionMode


def load_projection_config(config_source: str | Path | dict[str, Any] | None = None) -> ProjectionConfig:
    raw = _load_raw_config(config_source)
    if "fields" in raw and not raw.get("rules"):
        rules = _rules_from_fields(raw.get("fields") or [])
        mode = ProjectionMode.CUSTOM
    else:
        rules = [_rule_from_mapping(rule) for rule in raw.get("rules", []) if isinstance(rule, dict)]
        mode_value = str(raw.get("mode", ProjectionMode.DEFAULT.value))
        mode = ProjectionMode(mode_value)

    missing_value_strategy = _missing_strategy(raw)
    return ProjectionConfig(
        mode=mode,
        output_schema_name=str(raw.get("output_schema_name", "assignment_default" if mode == ProjectionMode.DEFAULT else "custom_projection")),
        output_schema_version=str(raw.get("output_schema_version", raw.get("version", "1.0"))),
        rules=rules,
        include_provenance=bool(raw.get("include_provenance", True)),
        include_confidence=bool(raw.get("include_confidence", True)),
        missing_value_strategy=missing_value_strategy,
        strict_unmapped_target_fields=bool(raw.get("strict_unmapped_target_fields", True)),
        freeze_canonical_input=bool(raw.get("freeze_canonical_input", True)),
        emit_validation_errors=bool(raw.get("emit_validation_errors", True)),
    )


def _load_raw_config(config_source: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    if config_source is None:
        return _load_file(CONFIG_DIR / "projection.yml")
    if isinstance(config_source, dict):
        return dict(config_source)
    path = Path(config_source)
    if not path.is_absolute():
        candidate = CONFIG_DIR / path
        if candidate.exists():
            path = candidate
    return _load_file(path)


def _load_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        if path.suffix.lower() == ".json":
            data = json.load(handle)
        else:
            data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Projection config must be a mapping: {path}")
    return data


def _rules_from_fields(fields: list[Any]) -> list[ProjectionRule]:
    rules: list[ProjectionRule] = []
    for index, field in enumerate(fields):
        if isinstance(field, str):
            rules.append(
                ProjectionRule(
                    rule_id=f"field_{index}_{field}",
                    source_path=field,
                    target_path=field,
                    operation="select",
                    required=False,
                    enabled=True,
                )
            )
            continue
        if not isinstance(field, dict):
            continue
        target_path = str(field.get("path") or field.get("target_path") or field.get("name") or f"field_{index}")
        source_path = str(field.get("from") or field.get("source_path") or target_path)
        transform_hint = field.get("normalize")
        rules.append(
            ProjectionRule(
                rule_id=str(field.get("rule_id") or f"field_{index}_{target_path}"),
                source_path=source_path,
                target_path=target_path,
                operation=str(field.get("operation") or ("rename" if source_path != target_path else "select")),
                default_value=field.get("default_value"),
                transform_hint=str(transform_hint) if transform_hint is not None else None,
                required=bool(field.get("required", False)),
                enabled=bool(field.get("enabled", True)),
            )
        )
    return rules


def _rule_from_mapping(rule: dict[str, Any]) -> ProjectionRule:
    return ProjectionRule(
        rule_id=str(rule.get("rule_id", rule.get("target_path", rule.get("source_path", "rule")))),
        source_path=str(rule.get("source_path", rule.get("target_path", ""))),
        target_path=str(rule.get("target_path", rule.get("source_path", ""))),
        operation=str(rule.get("operation", "select")),
        default_value=rule.get("default_value"),
        transform_hint=rule.get("transform_hint"),
        required=bool(rule.get("required", False)),
        enabled=bool(rule.get("enabled", True)),
    )


def _missing_strategy(raw: dict[str, Any]) -> MissingValueStrategy:
    value = raw.get("missing_value_strategy") or raw.get("on_missing") or MissingValueStrategy.NULL.value
    return MissingValueStrategy(str(value))
