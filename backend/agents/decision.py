"""Decision agent — synthesises all agent outputs into a final claim decision."""

from __future__ import annotations

import logging

from models.claim import ClaimDecision

logger = logging.getLogger(__name__)


class DecisionAgent:
    """
    Combines outputs from all pipeline agents into a single claim decision.

    Day 1: rule-based logic.  Day 2: enhanced with Claude reasoning.
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
                decision_reason: str,
                confidence_score: float   # 0.0 – 1.0
            }
        """
        logger.info("DecisionAgent.decide started")

        if not verification_passed:
            result = {
                "decision": ClaimDecision.REJECTED,
                "approved_amount": 0.0,
                "decision_reason": "Document verification failed",
                "confidence_score": 0.95,
            }
            logger.info("DecisionAgent.decide completed: REJECTED (verification failed)")
            return result

        if fraud_result.get("auto_manual_review"):
            result = {
                "decision": ClaimDecision.MANUAL_REVIEW,
                "approved_amount": 0.0,
                "decision_reason": (
                    "Fraud flags detected: " + "; ".join(fraud_result.get("fraud_flags", []))
                ),
                "confidence_score": 1.0 - fraud_result.get("fraud_score", 0.0),
            }
            logger.info("DecisionAgent.decide completed: MANUAL_REVIEW (fraud flags)")
            return result

        waiting = policy_evaluation.get("waiting_period", {})
        if not waiting.get("passed", True):
            result = {
                "decision": ClaimDecision.REJECTED,
                "approved_amount": 0.0,
                "decision_reason": waiting.get("reason", "Waiting period not cleared"),
                "confidence_score": 0.95,
            }
            logger.info("DecisionAgent.decide completed: REJECTED (waiting period)")
            return result

        exclusions = policy_evaluation.get("exclusions", {})
        if exclusions.get("excluded"):
            result = {
                "decision": ClaimDecision.REJECTED,
                "approved_amount": 0.0,
                "decision_reason": exclusions.get("exclusion_reason", "Claim excluded by policy"),
                "confidence_score": 0.90,
            }
            logger.info("DecisionAgent.decide completed: REJECTED (exclusion)")
            return result

        eligible_info = policy_evaluation.get("eligible_amount", {})
        eligible_amount: float = eligible_info.get("eligible_amount", 0.0)

        # Partial approval when sub-limit was applied
        if eligible_info.get("sub_limit_applied"):
            result = {
                "decision": ClaimDecision.PARTIAL,
                "approved_amount": eligible_amount,
                "decision_reason": (
                    "Claim approved partially due to sub-limit. "
                    + " | ".join(eligible_info.get("calculation_breakdown", []))
                ),
                "confidence_score": 0.85,
            }
            logger.info("DecisionAgent.decide completed: PARTIAL (sub-limit applied)")
            return result

        result = {
            "decision": ClaimDecision.APPROVED,
            "approved_amount": eligible_amount,
            "decision_reason": (
                "Claim approved. "
                + " | ".join(eligible_info.get("calculation_breakdown", []))
            ),
            "confidence_score": 0.90,
        }
        logger.info("DecisionAgent.decide completed: APPROVED amount=%.2f", eligible_amount)
        return result
