"""Claims API endpoints."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from models.claim import (
    ClaimRecord,
    ClaimStatus,
    ClaimSubmission,
    DocumentType,
    UploadedDocument,
)
from models.trace import ClaimTrace
from services.orchestrator import ClaimsOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory stores for Day 1 (replaced by Supabase on Day 2)
claims_store: dict[str, ClaimRecord] = {}
traces_store: dict[str, ClaimTrace] = {}


def _get_orchestrator(request: Request) -> ClaimsOrchestrator:
    """Retrieve the shared ClaimsOrchestrator from app state."""
    return request.app.state.orchestrator


def _detect_doc_type(filename: str) -> DocumentType:
    """
    Infer DocumentType from filename keywords.

    Ordered from most-specific to least-specific to avoid
    e.g. 'pharmacy_bill' matching 'bill' → HOSPITAL_BILL first.
    """
    name = filename.lower().replace("-", "_").replace(" ", "_")
    checks: list[tuple[list[str], DocumentType]] = [
        (["discharge", "summary"], DocumentType.DISCHARGE_SUMMARY),
        (["dental", "tooth", "teeth"], DocumentType.DENTAL_REPORT),
        (["pharmacy", "medicine", "drug", "chemist"], DocumentType.PHARMACY_BILL),
        (["lab", "pathology", "blood", "haemo"], DocumentType.LAB_REPORT),
        (["diagnostic", "xray", "x_ray", "mri", "ct_scan", "ultrasound", "scan"], DocumentType.DIAGNOSTIC_REPORT),
        (["prescription", "rx", "doctor"], DocumentType.PRESCRIPTION),
        (["bill", "invoice", "receipt", "hospital"], DocumentType.HOSPITAL_BILL),
    ]
    for keywords, doc_type in checks:
        if any(kw in name for kw in keywords):
            return doc_type
    return DocumentType.UNKNOWN


# ------------------------------------------------------------------
# POST /api/claims
# ------------------------------------------------------------------

@router.post("/claims", status_code=201)
async def submit_claim(
    request: Request,
    background_tasks: BackgroundTasks,
    claim_data: str = Form(..., description="JSON-encoded ClaimSubmission"),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """
    Accept a new insurance claim submission.

    Body is multipart/form-data:
    - ``claim_data``: JSON string conforming to ClaimSubmission schema.
    - ``files``: one or more document files (PDF, image).

    Returns the new claim_id and initial status on success.
    Returns HTTP 400 with a specific error if document verification fails.
    """
    # Parse claim_data JSON
    try:
        submission = ClaimSubmission(**json.loads(claim_data))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid claim_data: {exc}") from exc

    orchestrator = _get_orchestrator(request)

    # Build UploadedDocument list from the uploaded files
    documents: list[UploadedDocument] = []
    for uploaded_file in files:
        doc_type = _detect_doc_type(uploaded_file.filename or "unknown")
        content = await uploaded_file.read()
        documents.append(
            UploadedDocument(
                filename=uploaded_file.filename or "unknown",
                document_type=doc_type,
                file_size_bytes=len(content),
                upload_timestamp=datetime.utcnow(),
            )
        )

    # Merge documents declared in claim_data (e.g. from non-multipart clients)
    if submission.documents:
        declared_types = {d.document_type for d in documents}
        for doc in submission.documents:
            if doc.document_type not in declared_types:
                documents.append(doc)

    # Run document verification immediately (synchronous; fast)
    from agents.verification import DocumentVerificationAgent

    verification_agent = DocumentVerificationAgent(orchestrator.policy_engine)
    verification_result = verification_agent.verify(
        claim_type=submission.claim_type.value,
        uploaded_documents=documents,
    )

    if verification_result.status == "FAIL":
        return JSONResponse(
            status_code=400,
            content={
                "error": "document_verification_failed",
                "message": verification_result.error_message,
                "missing_required": verification_result.missing_required,
            },
        )

    # Create ClaimRecord
    claim = ClaimRecord(
        member_id=submission.member_id,
        claim_type=submission.claim_type,
        claimed_amount=submission.claimed_amount,
        treatment_date=submission.treatment_date,
        status=ClaimStatus.PENDING,
    )
    claims_store[claim.claim_id] = claim

    # Process in background
    background_tasks.add_task(
        _process_claim_background,
        claim.claim_id,
        documents,
        orchestrator,
    )

    logger.info("Claim %s submitted, background processing queued", claim.claim_id)
    return {
        "claim_id": claim.claim_id,
        "status": claim.status.value,
        "message": "Claim submitted successfully. Processing has started.",
    }


async def _process_claim_background(
    claim_id: str,
    documents: list[UploadedDocument],
    orchestrator: ClaimsOrchestrator,
) -> None:
    """Background task: run full processing pipeline for a claim."""
    claim = claims_store.get(claim_id)
    if not claim:
        logger.error("Background task: claim %s not found in store", claim_id)
        return
    try:
        updated_claim, trace = orchestrator.process(claim, documents)
        updated_claim.updated_at = datetime.utcnow()
        claims_store[claim_id] = updated_claim
        traces_store[trace.trace_id] = trace
        logger.info(
            "Background processing complete: claim=%s decision=%s",
            claim_id,
            updated_claim.decision,
        )
    except Exception:
        logger.exception("Background processing failed for claim %s", claim_id)
        if claim_id in claims_store:
            claims_store[claim_id].status = ClaimStatus.ERROR
            claims_store[claim_id].updated_at = datetime.utcnow()


# ------------------------------------------------------------------
# GET /api/claims
# ------------------------------------------------------------------

@router.get("/claims")
async def list_claims() -> list[dict]:
    """Return the last 50 claims, newest first."""
    sorted_claims = sorted(
        claims_store.values(),
        key=lambda c: c.created_at,
        reverse=True,
    )
    return [c.model_dump(mode="json") for c in sorted_claims[:50]]


# ------------------------------------------------------------------
# GET /api/claims/{claim_id}
# ------------------------------------------------------------------

@router.get("/claims/{claim_id}")
async def get_claim(claim_id: str) -> dict:
    """Return a single claim and its audit trace."""
    claim = claims_store.get(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    trace = None
    if claim.trace_id and claim.trace_id in traces_store:
        trace = traces_store[claim.trace_id].model_dump(mode="json")

    return {
        "claim": claim.model_dump(mode="json"),
        "trace": trace,
    }
