"""Fraud detection agent — flags suspicious claim patterns."""

from __future__ import annotations

import logging

from services.policy_engine import PolicyEngine

logger = logging.getLogger(__name__)


class FraudDetectionAgent:
    """
    Evaluates a claim against fraud-detection thresholds (Day 2 full implementation).

    Day 1: delegates entirely to PolicyEngine.check_fraud_thresholds().
    """

    def __init__(self, policy_engine: PolicyEngine) -> None:
        """Initialise with a loaded PolicyEngine instance."""
        self.policy_engine = policy_engine

    def check(
        self,
        claimed_amount: float,
        same_day_count: int = 0,
        monthly_count: int = 0,
    ) -> dict:
        """Run fraud threshold checks and return the result dict."""
        logger.info(
            "FraudDetectionAgent.check started: amount=%.2f same_day=%d monthly=%d",
            claimed_amount,
            same_day_count,
            monthly_count,
        )
        result = self.policy_engine.check_fraud_thresholds(
            claimed_amount=claimed_amount,
            same_day_claim_count=same_day_count,
            monthly_claim_count=monthly_count,
        )
        logger.info(
            "FraudDetectionAgent.check completed: flags=%s score=%.4f",
            result["fraud_flags"],
            result["fraud_score"],
        )
        return result
