"""Pydantic models for audit traces."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AgentStep(BaseModel):
    """One agent's execution record within a claim trace."""

    agent_name: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    status: Literal["SUCCESS", "FAILED", "SKIPPED"]
    input_summary: str
    output_summary: str
    full_input: dict
    full_output: dict
    error_message: Optional[str] = None


class ClaimTrace(BaseModel):
    """Complete audit trail for a single claim's processing pipeline."""

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim_id: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    steps: list[AgentStep] = []
    final_decision: Optional[str] = None
    final_confidence: Optional[float] = None
