"""Pydantic models for insurance claims."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

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
    hospital_name: Optional[str] = None
    notes: Optional[str] = None


class ExtractedLineItem(BaseModel):
    description: str
    amount: float
    quantity: Optional[int] = None
    unit_price: Optional[float] = None


class DocumentParsingResult(BaseModel):
    document_type: DocumentType
    filename: str

    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None

    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    doctor_specialization: Optional[str] = None

    hospital_name: Optional[str] = None
    hospital_address: Optional[str] = None

    diagnosis: list[str] = []
    treatment_items: list[str] = []
    medicines: list[str] = []

    total_amount: Optional[float] = None
    line_items: list[ExtractedLineItem] = []

    treatment_date: Optional[str] = None
    bill_date: Optional[str] = None

    overall_confidence: float = 0.0
    low_confidence_fields: list[str] = []
    parsing_notes: list[str] = []
    extraction_warnings: list[str] = []

    parsing_status: Literal["SUCCESS", "PARTIAL", "FAILED"] = "SUCCESS"
    error_message: Optional[str] = None


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
