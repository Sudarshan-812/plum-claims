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

# In-memory stores
claims_store: dict[str, ClaimRecord] = {}
traces_store: dict[str, ClaimTrace] = {}


def _get_orchestrator(request: Request) -> ClaimsOrchestrator:
    return request.app.state.orchestrator


def _detect_doc_type(filename: str) -> DocumentType:
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
    """Accept a new insurance claim (multipart/form-data)."""
    try:
        submission = ClaimSubmission(**json.loads(claim_data))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid claim_data: {exc}") from exc

    orchestrator = _get_orchestrator(request)

    documents: list[UploadedDocument] = []
    file_bytes: list[bytes] = []

    for uploaded_file in files:
        content = await uploaded_file.read()
        doc_type = _detect_doc_type(uploaded_file.filename or "unknown")
        documents.append(
            UploadedDocument(
                filename=uploaded_file.filename or "unknown",
                document_type=doc_type,
                file_size_bytes=len(content),
                upload_timestamp=datetime.utcnow(),
            )
        )
        file_bytes.append(content)

    # Merge documents declared in claim_data (non-multipart clients)
    if submission.documents:
        declared_types = {d.document_type for d in documents}
        for doc in submission.documents:
            if doc.document_type not in declared_types:
                documents.append(doc)
                file_bytes.append(b"")

    # Fast synchronous verification before queuing
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

    claim = ClaimRecord(
        member_id=submission.member_id,
        claim_type=submission.claim_type,
        claimed_amount=submission.claimed_amount,
        treatment_date=submission.treatment_date,
        status=ClaimStatus.PENDING,
    )
    claims_store[claim.claim_id] = claim

    background_tasks.add_task(
        _process_claim_background,
        claim.claim_id,
        documents,
        file_bytes,
        orchestrator,
        submission.hospital_name or "",
    )

    logger.info("Claim %s submitted, background processing queued", claim.claim_id)
    return {
        "claim_id": claim.claim_id,
        "status": claim.status.value,
        "message": "Claim received. Processing has started.",
    }


async def _process_claim_background(
    claim_id: str,
    documents: list[UploadedDocument],
    document_bytes: list[bytes],
    orchestrator: ClaimsOrchestrator,
    hospital_name: str = "",
) -> None:
    claim = claims_store.get(claim_id)
    if not claim:
        logger.error("Background task: claim %s not found in store", claim_id)
        return
    try:
        updated_claim, trace = await orchestrator.process_async(
            claim,
            documents,
            document_bytes=document_bytes,
            hospital_name=hospital_name,
        )
        updated_claim.updated_at = datetime.utcnow()
        claims_store[claim_id] = updated_claim
        traces_store[trace.trace_id] = trace
        logger.info(
            "Background processing complete: claim=%s decision=%s",
            claim_id, updated_claim.decision,
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
    sorted_claims = sorted(claims_store.values(), key=lambda c: c.created_at, reverse=True)
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

    return {"claim": claim.model_dump(mode="json"), "trace": trace}


# ------------------------------------------------------------------
# GET /api/claims/{claim_id}/trace
# ------------------------------------------------------------------

@router.get("/claims/{claim_id}/trace")
async def get_claim_trace(claim_id: str) -> dict:
    """Return the full audit trace for a claim."""
    claim = claims_store.get(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    if not claim.trace_id or claim.trace_id not in traces_store:
        raise HTTPException(status_code=404, detail="Trace not yet available (claim may still be processing)")

    return traces_store[claim.trace_id].model_dump(mode="json")


# ------------------------------------------------------------------
# GET /api/claims/{claim_id}/replay
# ------------------------------------------------------------------

@router.get("/claims/{claim_id}/replay")
async def replay_claim(claim_id: str) -> dict:
    """Return a step-by-step replay of the claim's processing pipeline."""
    claim = claims_store.get(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    if not claim.trace_id or claim.trace_id not in traces_store:
        raise HTTPException(status_code=404, detail="Trace not yet available")

    trace = traces_store[claim.trace_id]
    steps = []
    for i, step in enumerate(trace.steps, start=1):
        steps.append({
            "step_number": i,
            "agent_name": step.agent_name,
            "title": _step_title(step.agent_name),
            "description": _step_description(step.agent_name),
            "input_summary": step.input_summary,
            "output_summary": step.output_summary,
            "status": step.status,
            "duration_ms": step.duration_ms,
            "full_data": {
                "input": step.full_input,
                "output": step.full_output,
                "error": step.error_message,
            },
        })

    return {
        "claim_id": claim_id,
        "final_decision": trace.final_decision,
        "final_confidence": trace.final_confidence,
        "total_steps": len(steps),
        "steps": steps,
    }


def _step_title(agent_name: str) -> str:
    return {
        "DocumentVerificationAgent": "Document Verification",
        "DocumentParsingAgent": "Document Parsing",
        "FraudDetectionAgent": "Fraud Detection",
        "PolicyEvaluationAgent": "Policy Evaluation",
        "DecisionAgent": "Final Decision",
        "AuditAgent": "Audit & Save",
    }.get(agent_name, agent_name)


def _step_description(agent_name: str) -> str:
    return {
        "DocumentVerificationAgent": "Checks that required document types are present",
        "DocumentParsingAgent": "Extracts structured data from uploaded documents",
        "FraudDetectionAgent": "Checks for unusual claim patterns",
        "PolicyEvaluationAgent": "Applies policy rules: waiting period, exclusions, limits",
        "DecisionAgent": "Synthesises all checks into a final coverage decision",
        "AuditAgent": "Records the complete audit trail",
    }.get(agent_name, "")


# ------------------------------------------------------------------
# POST /api/claims/{claim_id}/reprocess
# ------------------------------------------------------------------

@router.post("/claims/{claim_id}/reprocess")
async def reprocess_claim(
    claim_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """Re-run the processing pipeline for an existing claim."""
    claim = claims_store.get(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    orchestrator = _get_orchestrator(request)

    # Reset claim state
    claim.status = ClaimStatus.PENDING
    claim.decision = None
    claim.approved_amount = None
    claim.decision_reason = None
    claim.confidence_score = None
    claim.trace_id = None
    claim.updated_at = datetime.utcnow()
    claims_store[claim_id] = claim

    # Rebuild a minimal document list from the claim record
    docs = [
        UploadedDocument(
            filename="reprocess_placeholder.jpg",
            document_type=DocumentType.UNKNOWN,
            file_size_bytes=0,
            upload_timestamp=datetime.utcnow(),
        )
    ]

    background_tasks.add_task(
        _process_claim_background,
        claim_id,
        docs,
        [],
        orchestrator,
        "",
    )

    return {
        "claim_id": claim_id,
        "status": "PROCESSING",
        "message": "Claim queued for reprocessing.",
    }
