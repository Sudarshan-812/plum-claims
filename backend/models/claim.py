"""Pydantic models for insurance claims."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    CONSULTATION = "CONSULTATION"
    DIAGNOSTIC = "DIAGNOSTIC"
    PHARMACY = "PHARMACY"
    DENTAL = "DENTAL"
    VISION = "VISION"
    ALTERNATIVE_MEDICINE = "ALTERNATIVE_MEDICINE"


class DocumentType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    LAB_REPORT = "LAB_REPORT"
    PHARMACY_BILL = "PHARMACY_BILL"
    DENTAL_REPORT = "DENTAL_REPORT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    UNKNOWN = "UNKNOWN"


class ClaimStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    ERROR = "ERROR"


class ClaimDecision(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class UploadedDocument(BaseModel):
    """Represents a single document uploaded with a claim."""

    filename: str
    document_type: DocumentType
    file_size_bytes: int
    upload_timestamp: datetime


class ClaimSubmission(BaseModel):
    """Incoming claim request from the member."""

    member_id: str
    claim_type: ClaimType
    claimed_amount: float = Field(..., gt=0, description="Claimed amount in INR")
    treatment_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    documents: list[UploadedDocument]
    notes: Optional[str] = None


class ClaimRecord(BaseModel):
    """Full claim record as stored in the database."""

    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    member_id: str
    claim_type: ClaimType
    claimed_amount: float
    treatment_date: str
    status: ClaimStatus = ClaimStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    decision: Optional[ClaimDecision] = None
    approved_amount: Optional[float] = None
    decision_reason: Optional[str] = None
    confidence_score: Optional[float] = None
    trace_id: Optional[str] = None
