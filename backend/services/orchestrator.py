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
    ) -> tuple[ClaimRecord, ClaimTrace]:
        """
        Run the full pipeline for *claim* and return the updated record + trace.

        The claim record is mutated in-place (status, decision, approved_amount,
        decision_reason, confidence_score, trace_id) and returned alongside the
        completed ClaimTrace.
        """
        logger.info(
            "Orchestrator.process started: claim_id=%s member=%s type=%s",
            claim.claim_id,
            claim.member_id,
            claim.claim_type,
        )
        audit = AuditAgent(claim.claim_id)
        claim.status = ClaimStatus.PROCESSING

        # Step 1 — document verification
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

        # Step 2 — document parsing (stub Day 1)
        parsed_data: dict = {}
        with audit.step("DocumentParsingAgent", {"doc_count": len(documents)}) as rec:
            parsed_data = self.parsing_agent.parse(documents)
            rec["output"] = parsed_data

        # Step 3 — fraud detection
        fraud_result: dict = {}
        with audit.step(
            "FraudDetectionAgent",
            {"claimed_amount": claim.claimed_amount},
        ) as rec:
            fraud_result = self.fraud_agent.check(
                claimed_amount=claim.claimed_amount,
                same_day_count=0,
                monthly_count=0,
            )
            rec["output"] = fraud_result

        # Step 4 — policy evaluation
        policy_result: dict = {}
        with audit.step(
            "PolicyEvaluationAgent",
            {
                "member_id": claim.member_id,
                "claim_type": claim.claim_type,
                "claimed_amount": claim.claimed_amount,
            },
        ) as rec:
            policy_result = self.policy_agent.evaluate(
                member_id=claim.member_id,
                claim_type=claim.claim_type,
                claimed_amount=claim.claimed_amount,
                claim_date=claim.treatment_date,
                diagnosis=parsed_data.get("diagnosis", []),
                treatment_items=parsed_data.get("treatment_items", []),
                hospital_name=parsed_data.get("hospital_name", ""),
            )
            rec["output"] = policy_result

        # Step 5 — final decision
        decision_result: dict = {}
        with audit.step(
            "DecisionAgent",
            {
                "verification_passed": True,
                "fraud_score": fraud_result.get("fraud_score", 0),
            },
        ) as rec:
            decision_result = self.decision_agent.decide(
                verification_passed=True,
                policy_evaluation=policy_result,
                fraud_result=fraud_result,
            )
            rec["output"] = decision_result

        # Update claim record
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
