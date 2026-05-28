"""Claims processing orchestrator — wires agents into a pipeline."""

from __future__ import annotations

import logging

from agents.audit import AuditAgent
from agents.decision import DecisionAgent
from agents.fraud import FraudDetectionAgent
from agents.parsing import DocumentParsingAgent
from agents.policy_eval import PolicyEvaluationAgent
from agents.verification import DocumentVerificationAgent
from models.claim import ClaimRecord, ClaimStatus, UploadedDocument
from models.trace import ClaimTrace
from services.policy_engine import PolicyEngine

logger = logging.getLogger(__name__)


class ClaimsOrchestrator:
    """
    Runs the full Day 1 pipeline for a claim.

    Pipeline order:
    1. DocumentVerificationAgent  — correct docs present?
    2. DocumentParsingAgent       — extract data from docs (stub Day 1)
    3. FraudDetectionAgent        — any fraud signals?
    4. PolicyEvaluationAgent      — policy checks + eligible amount
    5. DecisionAgent              — final decision
    6. AuditAgent                 — emit ClaimTrace throughout

    Each step is wrapped in an audit context-manager so any failure is
    recorded and the pipeline continues (graceful degradation).
    """

    def __init__(self, policy_engine: PolicyEngine) -> None:
        """Initialise all agents with the shared policy engine."""
        self.policy_engine = policy_engine
        self.verification_agent = DocumentVerificationAgent(policy_engine)
        self.parsing_agent = DocumentParsingAgent()
        self.fraud_agent = FraudDetectionAgent(policy_engine)
        self.policy_agent = PolicyEvaluationAgent(policy_engine)
        self.decision_agent = DecisionAgent()

    def process(
        self,
        claim: ClaimRecord,
        documents: list[UploadedDocument],
        hospital_name: str = "",
        same_day_count: int = 0,
        monthly_count: int = 0,
    ) -> tuple[ClaimRecord, ClaimTrace]:
        """
        Run the full pipeline for *claim* and return the updated record + trace.

        The claim record is mutated in-place (status, decision, approved_amount,
        decision_reason, confidence_score, trace_id) and returned alongside the
        completed ClaimTrace.

        *hospital_name* is used for the network-hospital discount check.
        *same_day_count* and *monthly_count* feed into fraud detection.
        """
        logger.info(
            "Orchestrator.process started: claim_id=%s member=%s type=%s",
            claim.claim_id,
            claim.member_id,
            claim.claim_type,
        )
        audit = AuditAgent(claim.claim_id)
        claim.status = ClaimStatus.PROCESSING
        failed_components: list[str] = []

        # ── Step 1: Document verification ────────────────────────────────
        verification_result = None
        with audit.step(
            "DocumentVerificationAgent",
            {"claim_type": claim.claim_type, "doc_count": len(documents)},
        ) as rec:
            verification_result = self.verification_agent.verify(
                claim_type=claim.claim_type,
                uploaded_documents=documents,
            )
            rec["output"] = {
                "status": verification_result.status,
                "missing_required": verification_result.missing_required,
                "error_message": verification_result.error_message,
            }

        if verification_result.status == "FAIL":
            claim.status = ClaimStatus.REJECTED
            claim.decision_reason = verification_result.error_message
            claim.confidence_score = 1.0
            trace = audit.complete("REJECTED", 1.0)
            claim.trace_id = trace.trace_id
            logger.info("Orchestrator.process ended: REJECTED (verification fail)")
            return claim, trace

        # ── Step 2: Document parsing (stub Day 1) ─────────────────────────
        parsed_data: dict = {}
        try:
            with audit.step("DocumentParsingAgent", {"doc_count": len(documents)}) as rec:
                parsed_data = self.parsing_agent.parse(documents)
                rec["output"] = parsed_data
        except Exception as exc:
            logger.warning("DocumentParsingAgent failed (continuing): %s", exc)
            failed_components.append("DocumentParsingAgent")

        # ── Step 3: Fraud detection ───────────────────────────────────────
        fraud_result: dict = {"auto_manual_review": False, "fraud_flags": [], "fraud_score": 0.0}
        try:
            with audit.step(
                "FraudDetectionAgent",
                {"claimed_amount": claim.claimed_amount, "same_day": same_day_count},
            ) as rec:
                fraud_result = self.fraud_agent.check(
                    claimed_amount=claim.claimed_amount,
                    same_day_count=same_day_count,
                    monthly_count=monthly_count,
                )
                rec["output"] = fraud_result
        except Exception as exc:
            logger.warning("FraudDetectionAgent failed (continuing): %s", exc)
            failed_components.append("FraudDetectionAgent")

        # ── Step 4: Policy evaluation ─────────────────────────────────────
        policy_result: dict = {}
        try:
            with audit.step(
                "PolicyEvaluationAgent",
                {
                    "member_id": claim.member_id,
                    "claim_type": claim.claim_type,
                    "claimed_amount": claim.claimed_amount,
                },
            ) as rec:
                effective_hospital = hospital_name or parsed_data.get("hospital_name", "")
                policy_result = self.policy_agent.evaluate(
                    member_id=claim.member_id,
                    claim_type=claim.claim_type,
                    claimed_amount=claim.claimed_amount,
                    claim_date=claim.treatment_date,
                    diagnosis=parsed_data.get("diagnosis", []),
                    treatment_items=parsed_data.get("treatment_items", []),
                    hospital_name=effective_hospital,
                    line_items=parsed_data.get("line_items"),
                )
                rec["output"] = policy_result
        except Exception as exc:
            logger.warning("PolicyEvaluationAgent failed (continuing): %s", exc)
            failed_components.append("PolicyEvaluationAgent")
            # Provide a safe fallback so DecisionAgent can still run
            policy_result = {
                "waiting_period": {"passed": True, "reason": "skipped"},
                "exclusions": {"excluded": False},
                "eligible_amount": {
                    "eligible_amount": claim.claimed_amount,
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

        # ── Step 5: Final decision ────────────────────────────────────────
        decision_result: dict = {}
        with audit.step(
            "DecisionAgent",
            {
                "verification_passed": True,
                "fraud_score": fraud_result.get("fraud_score", 0),
                "failed_components": failed_components,
            },
        ) as rec:
            decision_result = self.decision_agent.decide(
                verification_passed=True,
                policy_evaluation=policy_result,
                fraud_result=fraud_result,
            )
            # Reduce confidence when components failed
            if failed_components:
                penalty = 0.15 * len(failed_components)
                decision_result["confidence_score"] = round(
                    max(0.0, decision_result["confidence_score"] - penalty), 4
                )
                decision_result["decision_reason"] += (
                    f" [NOTE: {len(failed_components)} component(s) failed and were "
                    f"skipped ({', '.join(failed_components)}). "
                    "Manual review is recommended.]"
                )
            rec["output"] = decision_result

        # ── Update claim record ───────────────────────────────────────────
        claim.decision = decision_result["decision"]
        claim.approved_amount = decision_result["approved_amount"]
        claim.decision_reason = decision_result["decision_reason"]
        claim.confidence_score = decision_result["confidence_score"]
        claim.status = ClaimStatus(decision_result["decision"].value)

        trace = audit.complete(
            decision=decision_result["decision"].value,
            confidence=decision_result["confidence_score"],
        )
        claim.trace_id = trace.trace_id

        logger.info(
            "Orchestrator.process completed: claim_id=%s decision=%s amount=%.2f",
            claim.claim_id,
            claim.decision,
            claim.approved_amount or 0.0,
        )
        return claim, trace
