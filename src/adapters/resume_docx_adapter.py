"""Resume DOCX adapter: extracts raw text and performs token extraction deterministically."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from docx import Document

from src.adapters.enrichment_helpers import build_text_fragment
from src.interfaces.base_adapter import BaseAdapter
from src.models.domain_models import CandidateFragment, SourceMetadata
from src.utils.hashing import sha256_text

logger = logging.getLogger("sgct.adapters.resume_docx")


class ResumeDOCXAdapter(BaseAdapter):
    def adapt(self, raw_input: str | bytes, context) -> CandidateFragment:
        text = ""
        try:
            if isinstance(raw_input, (bytes, bytearray)):
                # python-docx does not support loading from bytes directly; expect a path in practice
                logger.warning("DOCX adapter received bytes; expecting file path. Returning empty text.")
                text = ""
            else:
                doc = Document(raw_input)
                paragraphs = [p.text for p in doc.paragraphs]
                text = "\n".join(paragraphs)
        except Exception as e:
            logger.warning("Failed to open DOCX: %s", e)
            text = ""

        src_meta = SourceMetadata(
            source_name="resume_docx",
            source_record_id=sha256_text(str(raw_input))[:12],
            source_file=str(raw_input) if isinstance(raw_input, str) else "bytes",
            ingested_at_utc=datetime.now(UTC),
            extractor_name="resume_docx_adapter",
            extractor_version="1.0",
            extraction_quality=0.8,
            raw_reference_hash=sha256_text(text),
        )

        return build_text_fragment(text, src_meta, "docx")
