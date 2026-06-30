"""Resume PDF adapter: extracts raw text and performs token extraction deterministically."""
from __future__ import annotations

import io
import logging
from datetime import UTC, datetime

import pdfplumber

from src.adapters.enrichment_helpers import build_text_fragment
from src.interfaces.base_adapter import BaseAdapter
from src.models.domain_models import CandidateFragment, SourceMetadata
from src.utils.hashing import sha256_text

logger = logging.getLogger("sgct.adapters.resume_pdf")


class ResumePDFAdapter(BaseAdapter):
    def adapt(self, raw_input: bytes | str, context) -> CandidateFragment:
        # raw_input is path to PDF or raw bytes
        text = ""
        try:
            if isinstance(raw_input, (bytes, bytearray)):
                with pdfplumber.open(io.BytesIO(raw_input)) as pdf:  # type: ignore[name-defined]
                    text = "\n".join((p.extract_text() or "") for p in pdf.pages)
            else:
                with pdfplumber.open(raw_input) as pdf:
                    text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception as e:
            logger.warning("Failed to open PDF: %s", e)
            text = ""

        src_meta = SourceMetadata(
            source_name="resume_pdf",
            source_record_id=sha256_text(str(raw_input))[:12],
            source_file=str(raw_input) if isinstance(raw_input, str) else "bytes",
            ingested_at_utc=datetime.now(UTC),
            extractor_name="resume_pdf_adapter",
            extractor_version="1.0",
            extraction_quality=0.8,
            raw_reference_hash=sha256_text(text),
        )

        return build_text_fragment(text, src_meta, "pdf")
