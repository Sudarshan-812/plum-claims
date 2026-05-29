"""LangGraph-based claims processing orchestrator."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import Annotated, Optional
import operator

from langgraph.graph import StateGraph, END
from typing import TypedDict

from agents.audit import AuditAgent
from agents.decision import DecisionAgent
from agents.fraud import FraudDetectionAgent
from agents.parsing import DocumentParsingAgent
from agents.policy_eval import PolicyEvaluationAgent
from agents.verification import DocumentVerificationAgent
from models.claim import (
    ClaimDecision,
    ClaimRecord,
    ClaimStatus,
    DocumentParsingResult,
    DocumentType,
    UploadedDocument,
)
from models.trace import AgentStep, ClaimTrace
from services.policy_engine import PolicyEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LangGraph State
# ---------------------------------------------------------------------------

class ClaimState(TypedDict):
    # Input
    claim_id: str
    member_id: str
    claim_type: str
    claimed_amount: float
    treatment_date: str
    uploaded_documents: list           # list of UploadedDocument objects
    document_bytes: list               # list of bytes (one per document)
    hospital_name: str
    same_day_count: int
    monthly_count: int

    # Pre-built parsing results (used by integration tests / replays)
    prebuilt_parsing_results: Optional[list]  # list of DocumentParsingResult

    # Agent outputs — built up as the pipeline runs
    verification_result: Optional[dict]
    parsing_results: list              # list of DocumentParsingResult dicts
    fraud_result: Optional[dict]
    policy_result: Optional[dict]
    decision_result: Optional[dict]

    # Quality issue raised by parsing (e.g. unreadable doc, name mismatch)
    parsing_quality_issue: Optional[str]

    # Trace — steps accumulated via reducer
    trace_steps: Annotated[list, operator.add]
    trace_id: str

    # Control flow
    pipeline_status: str               # RUNNING | COMPLETED | STOPPED_EARLY
    stop_reason: Optional[str]
    errors: Annotated[list, operator.add]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.utcnow()


def _step_dict(
    agent_name: str,
    started: datetime,
    full_input: dict,
    full_output: dict,
    status: str = "SUCCESS",
    error_message: Optional[str] = None,
) -> dict:
    """Build a serialisable AgentStep dict for the trace_steps accumulator."""
    completed = _now()
    duration_ms = max(0, int((completed - started).total_seconds() * 1000))
    import json

    def _summarise(d: dict) -> str:
        try:
            text = json.dumps(d, default=str)
        except Exception:
            text = str(d)
        return text[:200] + ("..." if len(text) > 200 else "")

    return {
        "agent_name": agent_name,
        "started_at": started,
        "completed_at": completed,
        "duration_ms": duration_ms,
        "status": status,
        "input_summary": _summarise(full_input),
        "output_summary": _summarise(full_output),
        "full_input": full_input,
        "full_output": full_output,
        "error_message": error_message,
    }


def _build_trace(state: ClaimState) -> ClaimTrace:
    """Assemble a ClaimTrace from the final graph state."""
    steps: list[AgentStep] = []
    for sd in state.get("trace_steps", []):
        try:
            steps.append(AgentStep(**sd))
        except Exception:
            pass

    decision_result = state.get("decision_result") or {}
    decision_val = decision_result.get("decision")
    final_decision: Optional[str] = None
    if decision_val is not None:
        final_decision = decision_val.value if isinstance(decision_val, ClaimDecision) else str(decision_val)
    elif state.get("stop_reason"):
        final_decision = "REJECTED"

    return ClaimTrace(
        trace_id=state["trace_id"],
        claim_id=state["claim_id"],
        started_at=steps[0].started_at if steps else _now(),
        completed_at=_now(),
        steps=steps,
        final_decision=final_decision,
        final_confidence=decision_result.get("confidence_score"),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class ClaimsOrchestrator:
    """
    Runs the full claims pipeline via a LangGraph state machine.

    Pipeline: verify → parse → fraud → policy → decide → audit
    """

    def __init__(
        self,
        policy_engine: PolicyEngine,
        anthropic_client=None,
    ) -> None:
        self.policy_engine = policy_engine
        self.verification_agent = DocumentVerificationAgent(policy_engine)
        self.parsing_agent = DocumentParsingAgent(anthropic_client)
        self.fraud_agent = FraudDetectionAgent(policy_engine)
        self.policy_agent = PolicyEvaluationAgent(policy_engine)
        self.decision_agent = DecisionAgent()
        self.graph = self._build_graph()

    def _build_graph(self):
        """Define LangGraph nodes as closures over self, then compile."""

        # ── Node 1: Document verification ──────────────────────────────────
        async def verify_documents(state: ClaimState) -> dict:
            started = _now()
            agent_input = {
                "claim_type": state["claim_type"],
                "doc_count": len(state["uploaded_documents"]),
            }
            try:
                docs = [
                    UploadedDocument(**d) if isinstance(d, dict) else d
                    for d in state["uploaded_documents"]
                ]
                result = self.verification_agent.verify(
                    claim_type=state["claim_type"],
                    uploaded_documents=docs,
                )
                agent_output = {
                    "status": result.status,
                    "missing_required": result.missing_required,
                    "error_message": result.error_message,
                }
                step = _step_dict("DocumentVerificationAgent", started, agent_input, agent_output)

                if result.status == "FAIL":
                    return {
                        "verification_result": agent_output,
                        "pipeline_status": "STOPPED_EARLY",
                        "stop_reason": result.error_message,
                        "trace_steps": [step],
                        "errors": [],
                    }
                return {
                    "verification_result": agent_output,
                    "pipeline_status": "RUNNING",
                    "trace_steps": [step],
                    "errors": [],
                }
            except Exception as exc:
                logger.exception("verify_documents node failed")
                step = _step_dict(
                    "DocumentVerificationAgent", started, agent_input, {},
                    status="FAILED", error_message=str(exc),
                )
                return {
                    "pipeline_status": "STOPPED_EARLY",
                    "stop_reason": f"Verification error: {exc}",
                    "trace_steps": [step],
                    "errors": [str(exc)],
                }

        # ── Node 2: Document parsing ────────────────────────────────────────
        async def parse_documents(state: ClaimState) -> dict:
            started = _now()
            agent_input = {"doc_count": len(state["uploaded_documents"])}

            # Use pre-built results if provided (integration tests / replays)
            prebuilt = state.get("prebuilt_parsing_results")
            if prebuilt:
                results: list[DocumentParsingResult] = [
                    DocumentParsingResult(**r) if isinstance(r, dict) else r
                    for r in prebuilt
                ]
            else:
                results = await _parse_all_documents(state, self.parsing_agent)

            result_dicts = [r.model_dump() for r in results]

            # Quality checks on parsed results
            quality_issue: Optional[str] = None

            failed_docs = [r for r in results if r.parsing_status == "FAILED"]
            if failed_docs:
                reasons = "; ".join(
                    f"{r.document_type.value}: {r.error_message or 'unreadable'}"
                    for r in failed_docs
                )
                quality_issue = (
                    f"One or more documents could not be read — please re-upload a "
                    f"clearer image. Affected: {reasons}"
                )

            if quality_issue is None:
                # Check for patient name mismatches across documents
                names = [
                    (r.document_type.value, r.patient_name)
                    for r in results
                    if r.patient_name
                ]
                unique_names = list({n.lower().strip() for _, n in names})
                if len(unique_names) > 1:
                    detail = ", ".join(
                        f"{dt}: '{nm}'" for dt, nm in names
                    )
                    quality_issue = (
                        f"Documents appear to belong to different patients: {detail}. "
                        "Please upload documents for the same patient."
                    )

            step = _step_dict(
                "DocumentParsingAgent", started, agent_input,
                {"parsed": len(result_dicts), "quality_issue": quality_issue},
            )
            return {
                "parsing_results": result_dicts,
                "parsing_quality_issue": quality_issue,
                "trace_steps": [step],
                "errors": [],
            }

        # ── Node 3: Fraud detection ─────────────────────────────────────────
        async def detect_fraud(state: ClaimState) -> dict:
            started = _now()
            agent_input = {
                "claimed_amount": state["claimed_amount"],
                "same_day_count": state["same_day_count"],
                "monthly_count": state["monthly_count"],
            }
            try:
                result = self.fraud_agent.check(
                    claimed_amount=state["claimed_amount"],
                    same_day_count=state["same_day_count"],
                    monthly_count=state["monthly_count"],
                )
                step = _step_dict("FraudDetectionAgent", started, agent_input, result)
                return {"fraud_result": result, "trace_steps": [step], "errors": []}
            except Exception as exc:
                logger.warning("detect_fraud failed (continuing): %s", exc)
                fallback = {"auto_manual_review": False, "fraud_flags": [], "fraud_score": 0.0}
                step = _step_dict(
                    "FraudDetectionAgent", started, agent_input, fallback,
                    status="FAILED", error_message=str(exc),
                )
                return {
                    "fraud_result": fallback,
                    "trace_steps": [step],
                    "errors": [f"FraudDetectionAgent failed: {exc}"],
                }

        # ── Node 4: Policy evaluation ───────────────────────────────────────
        async def evaluate_policy(state: ClaimState) -> dict:
            started = _now()
            agent_input = {
                "member_id": state["member_id"],
                "claim_type": state["claim_type"],
                "claimed_amount": state["claimed_amount"],
            }
            try:
                # Aggregate data from all parsed documents
                all_diagnosis: list[str] = []
                all_treatment_items: list[str] = []
                all_line_items: list[dict] = []
                parsed_hospital = ""

                for r in state.get("parsing_results", []):
                    rd = r if isinstance(r, dict) else r.model_dump()
                    all_diagnosis.extend(rd.get("diagnosis", []))
                    all_treatment_items.extend(rd.get("treatment_items", []))
                    for li in rd.get("line_items", []):
                        if isinstance(li, dict):
                            all_line_items.append(
                                {"description": li.get("description", ""), "amount": float(li.get("amount", 0))}
                            )
                    if not parsed_hospital and rd.get("hospital_name"):
                        parsed_hospital = rd["hospital_name"]

                effective_hospital = state.get("hospital_name") or parsed_hospital

                result = self.policy_agent.evaluate(
                    member_id=state["member_id"],
                    claim_type=state["claim_type"],
                    claimed_amount=state["claimed_amount"],
                    claim_date=state["treatment_date"],
                    diagnosis=all_diagnosis,
                    treatment_items=all_treatment_items,
                    hospital_name=effective_hospital,
                    line_items=all_line_items if all_line_items else None,
                )
                step = _step_dict("PolicyEvaluationAgent", started, agent_input, result)
                return {"policy_result": result, "trace_steps": [step], "errors": []}

            except Exception as exc:
                logger.warning("evaluate_policy failed (continuing): %s", exc)
                fallback = {
                    "waiting_period": {"passed": True, "reason": "skipped (component failed)"},
                    "exclusions": {"excluded": False},
                    "eligible_amount": {
                        "eligible_amount": state["claimed_amount"],
                        "copay_amount": 0.0,
                        "sub_limit_applied": False,
                        "per_claim_exceeded": False,
                        "approved_items": [],
                        "rejected_items": [],
                        "calculation_breakdown": ["Policy evaluation failed — using claimed amount"],
                    },
                    "pre_auth": {"required": False, "reason": "skipped"},
                    "is_network_hospital": False,
                    "passed": True,
                }
                step = _step_dict(
                    "PolicyEvaluationAgent", started, agent_input, fallback,
                    status="FAILED", error_message=str(exc),
                )
                return {
                    "policy_result": fallback,
                    "trace_steps": [step],
                    "errors": [f"PolicyEvaluationAgent failed: {exc}"],
                }

        # ── Node 5: Final decision ──────────────────────────────────────────
        async def make_decision(state: ClaimState) -> dict:
            started = _now()
            fraud_result = state.get("fraud_result") or {"auto_manual_review": False, "fraud_flags": [], "fraud_score": 0.0}
            policy_result = state.get("policy_result") or {}
            errors = list(state.get("errors", []))
            agent_input = {
                "fraud_score": fraud_result.get("fraud_score", 0),
                "parsing_quality_issue": state.get("parsing_quality_issue"),
                "failed_components": len(errors),
            }

            # Quality issue → MANUAL_REVIEW without calling DecisionAgent
            quality_issue = state.get("parsing_quality_issue")
            if quality_issue:
                result = {
                    "decision": ClaimDecision.MANUAL_REVIEW,
                    "approved_amount": 0.0,
                    "approved_items": [],
                    "rejected_items": [],
                    "rejection_reasons": ["DOCUMENT_QUALITY"],
                    "decision_reason": quality_issue,
                    "confidence_score": 0.50,
                }
            else:
                result = self.decision_agent.decide(
                    verification_passed=True,
                    policy_evaluation=policy_result,
                    fraud_result=fraud_result,
                )

            # Reduce confidence for any failed components
            if errors and not quality_issue:
                penalty = 0.15 * len(errors)
                result["confidence_score"] = round(
                    max(0.0, result["confidence_score"] - penalty), 4
                )
                result["decision_reason"] += (
                    f" [NOTE: {len(errors)} component(s) failed and were skipped. "
                    "Manual review is recommended.]"
                )

            step = _step_dict(
                "DecisionAgent", started, agent_input,
                {
                    "decision": result["decision"].value if isinstance(result["decision"], ClaimDecision) else result["decision"],
                    "approved_amount": result.get("approved_amount", 0),
                    "confidence_score": result.get("confidence_score", 0),
                },
            )
            return {
                "decision_result": result,
                "pipeline_status": "COMPLETED",
                "trace_steps": [step],
                "errors": [],
            }

        # ── Node 6: Save audit ──────────────────────────────────────────────
        async def save_audit(state: ClaimState) -> dict:
            started = _now()
            pipeline_status = state.get("pipeline_status", "UNKNOWN")
            final_decision = None

            if state.get("decision_result"):
                d = state["decision_result"].get("decision")
                final_decision = d.value if isinstance(d, ClaimDecision) else str(d) if d else None
            elif state.get("stop_reason"):
                final_decision = "REJECTED"

            step = _step_dict(
                "AuditAgent", started,
                {"pipeline_status": pipeline_status},
                {"final_decision": final_decision, "errors": list(state.get("errors", []))},
            )
            return {"trace_steps": [step], "errors": []}

        # ── Conditional edge after verification ────────────────────────────
        def should_continue_after_verification(state: ClaimState) -> str:
            if state.get("pipeline_status") == "STOPPED_EARLY":
                return "save_audit"
            return "parse_documents"

        # ── Assemble graph ──────────────────────────────────────────────────
        graph = StateGraph(ClaimState)
        graph.add_node("verify_documents", verify_documents)
        graph.add_node("parse_documents", parse_documents)
        graph.add_node("detect_fraud", detect_fraud)
        graph.add_node("evaluate_policy", evaluate_policy)
        graph.add_node("make_decision", make_decision)
        graph.add_node("save_audit", save_audit)

        graph.set_entry_point("verify_documents")
        graph.add_conditional_edges(
            "verify_documents",
            should_continue_after_verification,
            {"save_audit": "save_audit", "parse_documents": "parse_documents"},
        )
        graph.add_edge("parse_documents", "detect_fraud")
        graph.add_edge("detect_fraud", "evaluate_policy")
        graph.add_edge("evaluate_policy", "make_decision")
        graph.add_edge("make_decision", "save_audit")
        graph.add_edge("save_audit", END)

        return graph.compile()

    # ------------------------------------------------------------------
    # Public: async processing
    # ------------------------------------------------------------------

    async def process_async(
        self,
        claim: ClaimRecord,
        documents: list[UploadedDocument],
        document_bytes: Optional[list[bytes]] = None,
        hospital_name: str = "",
        same_day_count: int = 0,
        monthly_count: int = 0,
        prebuilt_parsing_results: Optional[list] = None,
    ) -> tuple[ClaimRecord, ClaimTrace]:
        """Run the full LangGraph pipeline and return updated claim + trace."""
        logger.info(
            "process_async started: claim_id=%s member=%s type=%s amount=%.2f",
            claim.claim_id, claim.member_id, claim.claim_type, claim.claimed_amount,
        )
        claim.status = ClaimStatus.PROCESSING

        initial_state: ClaimState = {
            "claim_id": claim.claim_id,
            "member_id": claim.member_id,
            "claim_type": claim.claim_type.value if hasattr(claim.claim_type, "value") else claim.claim_type,
            "claimed_amount": claim.claimed_amount,
            "treatment_date": claim.treatment_date,
            "uploaded_documents": [d.model_dump() for d in documents],
            "document_bytes": document_bytes or [],
            "hospital_name": hospital_name,
            "same_day_count": same_day_count,
            "monthly_count": monthly_count,
            "prebuilt_parsing_results": prebuilt_parsing_results,
            "verification_result": None,
            "parsing_results": [],
            "fraud_result": None,
            "policy_result": None,
            "decision_result": None,
            "parsing_quality_issue": None,
            "trace_steps": [],
            "trace_id": str(uuid.uuid4()),
            "pipeline_status": "RUNNING",
            "stop_reason": None,
            "errors": [],
        }

        final_state: ClaimState = await self.graph.ainvoke(initial_state)

        # Update claim record from final state
        if final_state.get("pipeline_status") == "STOPPED_EARLY":
            claim.decision = ClaimDecision.REJECTED
            claim.approved_amount = 0.0
            claim.decision_reason = final_state.get("stop_reason") or "Pipeline stopped early"
            claim.confidence_score = 1.0
            claim.status = ClaimStatus.REJECTED
        else:
            dr = final_state.get("decision_result") or {}
            decision = dr.get("decision")
            claim.decision = decision if isinstance(decision, ClaimDecision) else ClaimDecision(decision) if decision else None
            claim.approved_amount = dr.get("approved_amount", 0.0)
            claim.decision_reason = dr.get("decision_reason", "")
            claim.confidence_score = dr.get("confidence_score", 0.0)
            if claim.decision:
                claim.status = ClaimStatus(claim.decision.value)
            else:
                claim.status = ClaimStatus.ERROR

        trace = _build_trace(final_state)
        claim.trace_id = trace.trace_id

        logger.info(
            "process_async completed: claim_id=%s decision=%s amount=%.2f",
            claim.claim_id, claim.decision, claim.approved_amount or 0.0,
        )
        return claim, trace

    # ------------------------------------------------------------------
    # Public: sync wrapper (kept for backward compat)
    # ------------------------------------------------------------------

    def process(
        self,
        claim: ClaimRecord,
        documents: list[UploadedDocument],
        hospital_name: str = "",
        same_day_count: int = 0,
        monthly_count: int = 0,
    ) -> tuple[ClaimRecord, ClaimTrace]:
        """Sync wrapper around process_async. Safe to call from non-async contexts."""
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.process_async(
                    claim,
                    documents,
                    hospital_name=hospital_name,
                    same_day_count=same_day_count,
                    monthly_count=monthly_count,
                )
            )
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# Internal: parallel document parsing
# ---------------------------------------------------------------------------

async def _parse_all_documents(
    state: ClaimState,
    parsing_agent: DocumentParsingAgent,
) -> list[DocumentParsingResult]:
    """Parse each uploaded document, matching bytes by index."""
    import asyncio

    docs = state["uploaded_documents"]
    bytes_list = state.get("document_bytes") or []

    async def _parse_one(doc_raw, doc_bytes: bytes) -> DocumentParsingResult:
        doc = UploadedDocument(**doc_raw) if isinstance(doc_raw, dict) else doc_raw
        if doc_bytes:
            return await parsing_agent.parse(doc_bytes, doc.document_type, doc.filename)
        return parsing_agent.parse_mock(document_type=doc.document_type)

    tasks = [
        _parse_one(doc_raw, bytes_list[idx] if idx < len(bytes_list) else b"")
        for idx, doc_raw in enumerate(docs)
    ]
    return list(await asyncio.gather(*tasks))
