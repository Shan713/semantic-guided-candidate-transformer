"""SGCT UI routes — presentation layer only.

Every route delegates to the existing PipelineOrchestrator.  No business logic
is duplicated or re-implemented here.

The orchestrator and adapters are imported exactly as the CLI does in main.py,
preserving the same deterministic behaviour.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from src.adapters.ats_json_adapter import ATSJSONAdapter
from src.adapters.csv_adapter import CSVAdapter
from src.adapters.resume_docx_adapter import ResumeDOCXAdapter
from src.adapters.resume_pdf_adapter import ResumePDFAdapter
from src.core.pipeline import PipelineOrchestrator
from src.projection import load_projection_config

_UI_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = _UI_DIR / "templates"

router = APIRouter()
_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


def _render(template_name: str, context: dict[str, Any]) -> HTMLResponse:
    """Render a Jinja2 template to an HTMLResponse."""
    template = _jinja_env.get_template(template_name)
    html = template.render(**context)
    return HTMLResponse(content=html)

# ---------------------------------------------------------------------------
# Jinja2 custom filters
# ---------------------------------------------------------------------------


def pretty_json(value: Any) -> str:
    """Render a value as pretty-printed JSON."""
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def percent(value: float | None) -> str:
    """Format a 0-1 float as a whole-number percentage string."""
    if value is None:
        return "—"
    return f"{round(value * 100)}%"


def confidence_color(value: float | None) -> str:
    """Return a Bootstrap colour class for a confidence score."""
    if value is None:
        return "secondary"
    pct = value * 100
    if pct >= 80:
        return "success"
    if pct >= 60:
        return "warning"
    return "danger"


def truncate(value: Any, length: int = 80) -> str:
    """Truncate a string representation for display."""
    text = str(value) if value is not None else ""
    if len(text) <= length:
        return text
    return text[:length] + "…"


_jinja_env.filters["pretty_json"] = pretty_json
_jinja_env.filters["percent"] = percent
_jinja_env.filters["confidence_color"] = confidence_color
_jinja_env.filters["truncate"] = truncate

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Landing page with upload form."""
    return _render("index.html", {"request": request})


@router.post("/run", response_class=HTMLResponse)
async def run_pipeline(
    request: Request,
    resume: UploadFile | None = File(None),
    ats: UploadFile | None = File(None),
    csv: UploadFile | None = File(None),
    config: UploadFile | None = File(None),
) -> HTMLResponse:
    """Accept uploaded source files, run the SGCT pipeline, and render results.

    Accepts any combination of resume (PDF/DOCX), ATS JSON, and recruiter CSV.
    The optional projection config overrides the default projection.
    """
    t_start = time.monotonic()
    execution_id = f"sgct-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    logs: list[dict[str, Any]] = []
    errors: list[str] = []

    def _log(stage: str, detail: str = "") -> None:
        logs.append(
            {
                "stage": stage,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3],
            }
        )

    # ------------------------------------------------------------------
    # 1. Load source files into fragments (same adapters as CLI)
    # ------------------------------------------------------------------
    fragments = []
    csv_adapter = CSVAdapter()
    ats_adapter = ATSJSONAdapter()
    pdf_adapter = ResumePDFAdapter()
    docx_adapter = ResumeDOCXAdapter()

    if resume and resume.filename:
        _log("Loading Resume", resume.filename)
        try:
            content = await resume.read()
            suffix = Path(resume.filename).suffix.lower()
            if suffix == ".pdf":
                with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(content)
                    tmp.flush()
                    fragments.append(pdf_adapter.adapt(tmp.name, None))
                Path(tmp.name).unlink(missing_ok=True)
            elif suffix == ".docx":
                with NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                    tmp.write(content)
                    tmp.flush()
                    fragments.append(docx_adapter.adapt(tmp.name, None))
                Path(tmp.name).unlink(missing_ok=True)
            else:
                errors.append(f"Unsupported resume type: {resume.filename}")
        except Exception as exc:
            errors.append(f"Failed to process resume '{resume.filename}': {exc}")

    if ats and ats.filename:
        _log("Loading ATS JSON", ats.filename)
        try:
            raw = await ats.read()
            data = json.loads(raw.decode("utf-8"))
            fragments.append(ats_adapter.adapt(data, None))
        except Exception as exc:
            errors.append(f"Failed to process ATS JSON '{ats.filename}': {exc}")

    if csv and csv.filename:
        _log("Loading Recruiter CSV", csv.filename)
        try:
            raw = await csv.read()
            fragments.append(csv_adapter.adapt(raw.decode("utf-8"), None))
        except Exception as exc:
            errors.append(f"Failed to process CSV '{csv.filename}': {exc}")

    if not fragments and not errors:
        errors.append("At least one source file (resume, ATS, or CSV) must be provided.")

    # ------------------------------------------------------------------
    # 2. Load optional projection config
    # ------------------------------------------------------------------
    projection_config = None
    if config and config.filename:
        _log("Loading Projection Config", config.filename)
        try:
            raw = await config.read()
            content_str = raw.decode("utf-8")
            config_path = Path(config.filename)
            if config_path.suffix.lower() == ".json":
                config_data = json.loads(content_str)
            else:
                import yaml
                config_data = yaml.safe_load(content_str) or {}
            projection_config = load_projection_config(config_data)
        except Exception as exc:
            errors.append(f"Failed to process projection config: {exc}")

    # ------------------------------------------------------------------
    # 3. If there are errors at this stage, render them
    # ------------------------------------------------------------------
    if errors and not fragments:
        _log("Pipeline Aborted", "; ".join(errors))
        elapsed = time.monotonic() - t_start
        return _render(
            "index.html",
            {
                "request": request,
                "errors": errors,
            },
        )

    # ------------------------------------------------------------------
    # 4. Run the pipeline (exact same call as CLI)
    # ------------------------------------------------------------------
    orchestrator = PipelineOrchestrator.build()

    try:
        _log("Pipeline Start", f"{len(fragments)} fragment(s)")
        semantic_fragments, canonical_candidates, projected, validation_results = (
            orchestrator.execute_end_to_end(fragments, projection_config)
        )
        _log("Pipeline Complete")
    except Exception as exc:
        _log("Pipeline Error", str(exc))
        errors.append(f"Pipeline execution failed: {exc}")
        elapsed = time.monotonic() - t_start
        return _render(
            "index.html",
            {
                "request": request,
                "errors": errors,
            },
        )

    # ------------------------------------------------------------------
    # 5. Prepare serializable data for templates
    # ------------------------------------------------------------------
    serialized_candidates = [
        c.model_dump(mode="json") for c in canonical_candidates
    ]

    serialized_projected = projected

    serialized_validation = [
        {
            "is_valid": v.is_valid,
            "errors": [e.model_dump() for e in v.errors],
            "warnings": [w.model_dump() for w in v.warnings],
        }
        for v in validation_results
    ]

    # Confidence summary
    field_confidences = _build_field_confidence_table(canonical_candidates)
    all_field_confidences = _build_all_field_confidences(canonical_candidates)

    # Compute summary stats
    total_fragments = len(fragments)
    identity_groups = len(canonical_candidates)
    avg_confidence = (
        sum(c.overall_confidence_internal for c in canonical_candidates)
        / len(canonical_candidates)
        if canonical_candidates
        else 0.0
    )
    total_errors = sum(len(v.errors) for v in validation_results)
    total_warnings = sum(len(v.warnings) for v in validation_results)
    elapsed = time.monotonic() - t_start

    # Passed checks
    passed_checks = _build_passed_checks(validation_results)

    # Provenance
    provenance_data = _build_provenance_data(canonical_candidates)

    # Stage status for pipeline visual
    stages = [
        {"name": "Adapters", "done": True},
        {"name": "Fragments", "done": True},
        {"name": "Semantic Resolution", "done": True},
        {"name": "Identity Resolution", "done": True},
        {"name": "Fusion", "done": True},
        {"name": "Confidence + Provenance", "done": True},
        {"name": "Projection", "done": True},
        {"name": "Validation", "done": True},
        {"name": "Output", "done": True},
    ]

    _log("Rendering Results")

    return _render(
        "results.html",
        {
            "request": request,
            "execution_id": execution_id,
            # Summary cards
            "total_fragments": total_fragments,
            "identity_groups": identity_groups,
            "canonical_count": len(canonical_candidates),
            "avg_confidence": avg_confidence,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "elapsed": f"{elapsed:.2f}s",
            # Main data
            "candidates": serialized_candidates,
            "projected": serialized_projected,
            "validation": serialized_validation,
            "field_confidences": field_confidences,
            "all_field_confidences": all_field_confidences,
            "provenance_data": provenance_data,
            "passed_checks": passed_checks,
            "logs": logs,
            "stages": stages,
            "errors": errors,
            # Confidence breakdown
            "confidence_breakdown": _build_confidence_breakdown(canonical_candidates),
        },
    )


# ---------------------------------------------------------------------------
# Serialization helpers (presentation-layer formatting only)
# ---------------------------------------------------------------------------


def _build_field_confidence_table(
    candidates: list[Any],
) -> list[dict[str, Any]]:
    """Build a field-level confidence table for display.

    Uses the OverallConfidence.field_confidences when available; falls back to
    per-candidate confidence_records averaged across candidates.
    """
    if not candidates:
        return []

    # Collect per-candidate confidences
    all_fields: dict[str, list[float]] = {}
    for c in candidates:
        for record in getattr(c, "confidence_records", []):
            field = record.field
            all_fields.setdefault(field, []).append(record.score)

    table = []
    for field, scores in sorted(all_fields.items()):
        avg = sum(scores) / len(scores) if scores else 0.0
        table.append(
            {
                "field": field.replace("_", " ").title(),
                "score": avg,
                "scores": scores,
                "source_count": len(scores),
            }
        )
    return table


def _build_all_field_confidences(
    candidates: list[Any],
) -> list[dict[str, Any]]:
    """Create the full field confidence breakdown including sub-components."""
    if not candidates:
        return []

    result = []
    c = candidates[0]  # Use first candidate
    for record in getattr(c, "confidence_records", []):
        bd = record.breakdown
        result.append(
            {
                "field": record.field.replace("_", " ").title(),
                "score": record.score,
                "source_reliability": bd.source_reliability if hasattr(bd, "source_reliability") else None,
                "cross_source_agreement": bd.cross_source_agreement if hasattr(bd, "cross_source_agreement") else None,
                "extraction_quality": bd.extraction_quality if hasattr(bd, "extraction_quality") else None,
                "semantic_certainty": bd.semantic_certainty if hasattr(bd, "semantic_certainty") else None,
                "conflict_penalty": bd.conflict_penalty if hasattr(bd, "conflict_penalty") else None,
            }
        )
    return result


def _build_confidence_breakdown(
    candidates: list[Any],
) -> dict[str, Any]:
    """Build the aggregate confidence breakdown for display."""
    if not candidates:
        return {}

    c = candidates[0]
    all_breakdowns: dict[str, list[float]] = {}
    for record in getattr(c, "confidence_records", []):
        bd = record.breakdown
        for key in ("source_reliability", "cross_source_agreement", "extraction_quality", "semantic_certainty", "conflict_penalty"):
            val = getattr(bd, key, None)
            if val is not None:
                all_breakdowns.setdefault(key, []).append(val)

    result = {}
    for key, values in all_breakdowns.items():
        result[key] = sum(values) / len(values) if values else 0.0
    return result


def _build_provenance_data(
    candidates: list[Any],
) -> list[dict[str, Any]]:
    """Build provenance table data from canonical candidates."""
    rows = []
    if not candidates:
        return rows

    c = candidates[0]
    for record in getattr(c, "provenance", []):
        rows.append(
            {
                "field": record.field if hasattr(record, "field") else "",
                "canonical_value": _safe_str(getattr(record, "canonical_value", None)),
                "original_value": _safe_str(getattr(record, "original_value", None)),
                "source": record.source if hasattr(record, "source") else "",
                "method": record.method if hasattr(record, "method") else "",
                "confidence": getattr(record, "confidence", None),
                "transformation": record.transformation_rule if hasattr(record, "transformation_rule") else "",
            }
        )

    # Add transformation history rows (the step-by-step chain)
    for record in getattr(c, "transformation_history", []):
        rows.append(
            {
                "field": record.field if hasattr(record, "field") else "",
                "canonical_value": _safe_str(getattr(record, "canonical_value", None)),
                "original_value": _safe_str(getattr(record, "original_value", None)),
                "source": record.ontology_domain if hasattr(record, "ontology_domain") else "",
                "method": record.resolution_stage.value if hasattr(record, "resolution_stage") else "",
                "confidence": getattr(record, "semantic_confidence", None),
                "transformation": record.rule_name if hasattr(record, "rule_name") else "",
            }
        )
    return rows


def _build_passed_checks(
    validation_results: list[Any],
) -> list[dict[str, str]]:
    """Build a list of passed validation checks."""
    checks = []
    for v in validation_results:
        if v.is_valid:
            checks.append({"message": "Schema validation passed", "icon": "check-circle"})
        else:
            checks.append({"message": "Schema validation: issues found", "icon": "exclamation-triangle"})
    if not validation_results:
        checks.append({"message": "No validation rules applied", "icon": "info-circle"})
    return checks


def _safe_str(value: Any) -> str:
    """Safely convert any value to a display string."""
    if value is None:
        return "—"
    if isinstance(value, list):
        return ", ".join(_safe_str(v) for v in value[:5])
    return str(value)[:200]
