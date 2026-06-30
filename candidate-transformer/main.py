from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.adapters.ats_json_adapter import ATSJSONAdapter
from src.adapters.csv_adapter import CSVAdapter
from src.adapters.resume_docx_adapter import ResumeDOCXAdapter
from src.adapters.resume_pdf_adapter import ResumePDFAdapter
from src.core.logging import configure_logging, get_logger
from src.core.pipeline import PipelineOrchestrator
from src.projection import load_projection_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SGCT candidate transformation CLI")
    parser.add_argument("--csv", action="append", default=[], help="CSV source file path")
    parser.add_argument("--ats", action="append", default=[], help="ATS JSON source file path")
    parser.add_argument("--resume", action="append", default=[], help="Resume PDF or DOCX source file path")
    parser.add_argument("--config", "--projection", help="Projection config file path", default=None)
    parser.add_argument("--output", help="Output JSON file path", required=True)
    args = parser.parse_args(argv)

    execution_id = configure_logging()
    logger = get_logger("sgct.cli")

    if not args.csv and not args.ats and not args.resume:
        parser.error("At least one source file must be provided")

    orchestrator = PipelineOrchestrator.build()
    projection_config = load_projection_config(args.config) if args.config else None
    fragments = _load_fragments(args.csv, args.ats, args.resume)
    semantic_fragments, canonical_candidates, projected, validation_results = orchestrator.execute_end_to_end(
        fragments,
        projection_config,
    )

    output_payload: Any = projected[0] if len(projected) == 1 else projected
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    validation_errors = sum(len(result.errors) for result in validation_results)
    validation_warnings = sum(len(result.warnings) for result in validation_results)
    average_confidence = (
        sum(candidate.overall_confidence_internal for candidate in canonical_candidates) / len(canonical_candidates)
        if canonical_candidates
        else 0.0
    )

    print(f"Fragments processed: {len(fragments)}")
    print(f"Identity groups: {len(canonical_candidates)}")
    print(f"Canonical candidates: {len(canonical_candidates)}")
    print(f"Confidence score: {average_confidence:.3f}")
    print(f"Validation errors: {validation_errors}")
    print(f"Validation warnings: {validation_warnings}")
    print(f"Output written: {output_path}")
    logger.info(
        "Pipeline completed",
        extra={"execution_id": execution_id, "fragments": len(fragments), "outputs": len(projected)},
    )
    return 0


def _load_fragments(csv_paths: list[str], ats_paths: list[str], resume_paths: list[str]):
    fragments = []
    csv_adapter = CSVAdapter()
    ats_adapter = ATSJSONAdapter()
    pdf_adapter = ResumePDFAdapter()
    docx_adapter = ResumeDOCXAdapter()

    for path_text in csv_paths:
        path = Path(path_text)
        fragments.append(csv_adapter.adapt(path.read_text(encoding="utf-8"), None))

    for path_text in ats_paths:
        path = Path(path_text)
        fragments.append(ats_adapter.adapt(json.loads(path.read_text(encoding="utf-8")), None))

    for path_text in resume_paths:
        path = Path(path_text)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            fragments.append(pdf_adapter.adapt(str(path), None))
        elif suffix == ".docx":
            fragments.append(docx_adapter.adapt(str(path), None))
        else:
            raise ValueError(f"Unsupported resume type: {path}")

    return fragments


if __name__ == "__main__":
    raise SystemExit(main())
