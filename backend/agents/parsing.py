"""Document parsing agent — uses Claude Vision to extract data from documents."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DocumentParsingAgent:
    """
    Parses uploaded claim documents with Claude Vision (Day 2 implementation).

    Placeholder on Day 1 — returns empty extraction results so the pipeline
    can run end-to-end without a real Anthropic API call.
    """

    def parse(self, documents: list) -> dict:
        """Return a stub extraction result for Day 1."""
        logger.info("DocumentParsingAgent.parse started (stub): doc_count=%d", len(documents))
        result: dict = {
            "diagnosis": [],
            "treatment_items": [],
            "hospital_name": "",
            "doctor_name": "",
            "treatment_date": "",
        }
        logger.info("DocumentParsingAgent.parse completed (stub)")
        return result
