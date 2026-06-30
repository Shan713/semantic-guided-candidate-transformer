from __future__ import annotations

from tests.test_projection import _candidate

from src.models.enums import ProjectionMode
from src.projection import ProjectionEngine, load_projection_config
from src.validation import ValidationEngine


def test_validation_accepts_default_projection():
    projection_config = load_projection_config()
    payload = ProjectionEngine().project(_candidate(), projection_config)

    result = ValidationEngine().validate(payload, projection_config)

    assert result.is_valid
    assert not result.errors


def test_validation_reports_invalid_phone_and_country():
    projection_config = load_projection_config(
        {
            "fields": [
                {"path": "phone", "from": "phones[0]", "normalize": "E164", "required": True},
                {"path": "country", "from": "location.country", "normalize": "ISO3166"},
            ],
            "include_confidence": False,
            "include_provenance": False,
            "on_missing": "null",
        }
    )
    payload = {"phone": "415-555-2671", "country": "United States"}

    result = ValidationEngine().validate(payload, projection_config)

    assert not result.is_valid
    assert any(error.code == "invalid_phone_format" for error in result.errors)
    assert any(error.code == "invalid_country_code" for error in result.errors)


def test_validation_detects_missing_required_field():
    projection_config = load_projection_config(
        {
            "fields": [
                {"path": "full_name", "from": "full_name", "required": True},
                {"path": "primary_email", "from": "emails[0]", "required": True},
            ],
            "include_confidence": False,
            "include_provenance": False,
            "on_missing": "null",
        }
    )
    payload = {"full_name": "Jane Smith"}

    result = ValidationEngine().validate(payload, projection_config)

    assert not result.is_valid
    assert any(error.code == "missing_required_field" for error in result.errors)
