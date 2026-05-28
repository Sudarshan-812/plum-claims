"""Audit agent — builds and persists the ClaimTrace for a processed claim."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from models.trace import AgentStep, ClaimTrace

logger = logging.getLogger(__name__)


class AuditAgent:
    """
    Records every step of the processing pipeline into a ClaimTrace.

    Usage::

        audit = AuditAgent(claim_id="abc-123")
        with audit.step("DocumentVerificationAgent", inputs) as record:
            result = verification_agent.verify(...)
            record["output"] = result
        trace = audit.get_trace()
    """

    def __init__(self, claim_id: str) -> None:
        """Create a new trace for *claim_id*."""
        self._trace = ClaimTrace(claim_id=claim_id)
        logger.info("AuditAgent initialised: trace_id=%s claim_id=%s", self._trace.trace_id, claim_id)

    @contextmanager
    def step(
        self, agent_name: str, full_input: dict
    ) -> Generator[dict, None, None]:
        """
        Context manager that records one agent step.

        The caller populates ``record["output"]`` (a dict) inside the
        ``with`` block.  If an exception escapes the block the step is
        recorded with status=FAILED and the error message captured.
        """
        started = datetime.utcnow()
        t0 = time.monotonic()
        record: dict = {"output": {}}
        status = "SUCCESS"
        error_msg = None

        try:
            yield record
        except Exception as exc:
            status = "FAILED"
            error_msg = str(exc)
            logger.exception("Agent step failed: %s", agent_name)
            raise
        finally:
            completed = datetime.utcnow()
            duration_ms = int((time.monotonic() - t0) * 1000)
            full_output = record.get("output", {})

            agent_step = AgentStep(
                agent_name=agent_name,
                started_at=started,
                completed_at=completed,
                duration_ms=duration_ms,
                status=status,
                input_summary=_summarise(full_input),
                output_summary=_summarise(full_output),
                full_input=full_input,
                full_output=full_output if isinstance(full_output, dict) else {"result": str(full_output)},
                error_message=error_msg,
            )
            self._trace.steps.append(agent_step)

    def complete(self, decision: str, confidence: float) -> ClaimTrace:
        """Mark the trace as complete and return it."""
        self._trace.completed_at = datetime.utcnow()
        self._trace.final_decision = decision
        self._trace.final_confidence = confidence
        logger.info(
            "AuditAgent.complete: trace_id=%s decision=%s confidence=%.4f",
            self._trace.trace_id,
            decision,
            confidence,
        )
        return self._trace

    def get_trace(self) -> ClaimTrace:
        """Return the current trace (may still be in progress)."""
        return self._trace


def _summarise(data: dict, max_len: int = 200) -> str:
    """Return a short string summary of a dict for the trace output_summary field."""
    try:
        import json
        text = json.dumps(data, default=str)
    except Exception:
        text = str(data)
    return text[:max_len] + ("..." if len(text) > max_len else "")
