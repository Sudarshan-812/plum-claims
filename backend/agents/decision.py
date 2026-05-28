"""Decision agent — synthesises all agent outputs into a final claim decision."""

from __future__ import annotations

import logging

from models.claim import ClaimDecision

logger = logging.getLogger(__name__)


class DecisionAgent:
    """
    Combines outputs from all pipeline agents into a single claim decision.

    Priority order for rejection/routing:
    1. Verification failed → REJECTED
    2. Fraud signals → MANUAL_REVIEW
    3. All items excluded (eligible=0 and items rejected) → REJECTED (EXCLUDED_CONDITION)
    4. Waiting period not cleared → REJECTED (WAITING_PERIOD)
    5. Pre-auth required → REJECTED (PRE_AUTH_MISSING)
    6. Per-claim limit exceeded → REJECTED (PER_CLAIM_EXCEEDED)
    7. Partial item exclusions (some items rejected) → PARTIAL
    8. Sub-limit applied → PARTIAL
    9. Clean → APPROVED
    """

    def decide(
        self,
        verification_passed: bool,
        policy_evaluation: dict,
        fraud_result: dict,
    ) -> dict:
        """
        Produce a final decision dict.

        Returns::

            {
                decision: ClaimDecision,
                approved_amount: float,
                approved_items: list[dict],
                rejected_items: list[dict],
                rejection_reasons: list[str],
                decision_reason: str,
                confidence_score: float   # 0.0 – 1.0
            }
        """
        logger.info("DecisionAgent.decide started")

        base = {
            "approved_items": [],
            "rejected_items": [],
            "rejection_reasons": [],
        }

        # ── 1. Verification failed ───────────────────────────────────────
        if not verification_passed:
            result = {
                **base,
                "decision": ClaimDecision.REJECTED,
                "approved_amount": 0.0,
                "rejection_reasons": ["VERIFICATION_FAILED"],
                "decision_reason": "Document verification failed",
                "confidence_score": 0.95,
            }
            logger.info("DecisionAgent.decide completed: REJECTED (verification failed)")
            return result

        # ── 2. Fraud signals ─────────────────────────────────────────────
        if fraud_result.get("auto_manual_review"):
            flags = fraud_result.get("fraud_flags", [])
            result = {
                **base,
                "decision": ClaimDecision.MANUAL_REVIEW,
                "approved_amount": 0.0,
                "rejection_reasons": ["FRAUD_SIGNAL"],
                "decision_reason": (
                    "Claim flagged for manual review due to unusual patterns. "
                    "Signals: " + "; ".join(flags)
                ),
                "confidence_score": round(
                    max(0.0, 1.0 - fraud_result.get("fraud_score", 0.0)), 4
                ),
            }
            logger.info("DecisionAgent.decide completed: MANUAL_REVIEW (fraud flags)")
            return result

        eligible_info = policy_evaluation.get("eligible_amount", {})
        eligible_amount: float = eligible_info.get("eligible_amount", 0.0)
        rejected_items: list[dict] = eligible_info.get("rejected_items", [])
        approved_items: list[dict] = eligible_info.get("approved_items", [])

        # ── 3. All items excluded ────────────────────────────────────────
        exclusions = policy_evaluation.get("exclusions", {})
        if exclusions.get("excluded") and eligible_amount == 0.0:
            result = {
                **base,
                "decision": ClaimDecision.REJECTED,
                "approved_amount": 0.0,
                "rejected_items": rejected_items,
                "rejection_reasons": ["EXCLUDED_CONDITION"],
                "decision_reason": (
                    exclusions.get("exclusion_reason")
                    or "Claim excluded by policy"
                ),
                "confidence_score": 0.92,
            }
            logger.info("DecisionAgent.decide completed: REJECTED (excluded condition)")
            return result

        # ── 4. Waiting period not cleared ────────────────────────────────
        waiting = policy_evaluation.get("waiting_period", {})
        if not waiting.get("passed", True):
            eligible_from = waiting.get("eligible_from", "")
            suffix = f" You will be eligible from {eligible_from}." if eligible_from else ""
            result = {
                **base,
                "decision": ClaimDecision.REJECTED,
                "approved_amount": 0.0,
                "rejection_reasons": ["WAITING_PERIOD"],
                "decision_reason": waiting.get("reason", "Waiting period not cleared") + suffix,
                "confidence_score": 0.95,
            }
            logger.info("DecisionAgent.decide completed: REJECTED (waiting period)")
            return result

        # ── 5. Pre-auth required ─────────────────────────────────────────
        pre_auth = policy_evaluation.get("pre_auth", {})
        if pre_auth.get("required"):
            result = {
                **base,
                "decision": ClaimDecision.REJECTED,
                "approved_amount": 0.0,
                "rejection_reasons": ["PRE_AUTH_MISSING"],
                "decision_reason": pre_auth.get("reason", "Pre-authorisation was required"),
                "confidence_score": 0.95,
            }
            logger.info("DecisionAgent.decide completed: REJECTED (pre-auth missing)")
            return result

        # ── 6. Per-claim limit exceeded ──────────────────────────────────
        if eligible_info.get("per_claim_exceeded"):
            reason_items = eligible_info.get("rejected_items", [])
            reason = (
                reason_items[0]["reason"]
                if reason_items
                else "Per-claim limit exceeded"
            )
            result = {
                **base,
                "decision": ClaimDecision.REJECTED,
                "approved_amount": 0.0,
                "rejection_reasons": ["PER_CLAIM_EXCEEDED"],
                "decision_reason": reason,
                "confidence_score": 0.97,
            }
            logger.info("DecisionAgent.decide completed: REJECTED (per-claim exceeded)")
            return result

        # ── 7 & 8. Partial approval (some items excluded or sub-limit) ───
        has_rejected_items = len(rejected_items) > 0
        sub_limit_applied = eligible_info.get("sub_limit_applied", False)

        if has_rejected_items or (sub_limit_applied and eligible_amount > 0):
            breakdown = " | ".join(eligible_info.get("calculation_breakdown", []))
            result = {
                **base,
                "decision": ClaimDecision.PARTIAL,
                "approved_amount": eligible_amount,
                "approved_items": approved_items,
                "rejected_items": rejected_items,
                "rejection_reasons": [],
                "decision_reason": (
                    "Claim partially approved. "
                    + ("Some items were excluded from coverage. " if has_rejected_items else "")
                    + ("Sub-limit applied. " if sub_limit_applied else "")
                    + breakdown
                ),
                "confidence_score": 0.88,
            }
            logger.info(
                "DecisionAgent.decide completed: PARTIAL amount=%.2f", eligible_amount
            )
            return result

        # ── 9. Full approval ─────────────────────────────────────────────
        breakdown = " | ".join(eligible_info.get("calculation_breakdown", []))
        result = {
            **base,
            "decision": ClaimDecision.APPROVED,
            "approved_amount": eligible_amount,
            "approved_items": approved_items,
            "rejected_items": [],
            "rejection_reasons": [],
            "decision_reason": "Claim approved. " + breakdown,
            "confidence_score": 0.90,
        }
        logger.info(
            "DecisionAgent.decide completed: APPROVED amount=%.2f", eligible_amount
        )
        return result
