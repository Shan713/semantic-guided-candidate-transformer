from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    path: str
    code: str
    message: str
    expected: str | None = None
    actual: str | None = None


class ValidationResult(BaseModel):
    is_valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
