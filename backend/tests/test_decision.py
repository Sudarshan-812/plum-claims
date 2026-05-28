"""Tests for DecisionAgent — decision synthesis logic."""

from __future__ import annotations

import pytest

from agents.decision import DecisionAgent
from models.claim import ClaimDecision


@pytest.fixture
def agent():
    return DecisionAgent()


def _policy_result(
    *,
    waiting_passed: bool = True,
    excluded: bool = False,
    sub_limit_applied: bool = False,
    eligible_amount: float = 5000.0,
) -> dict:
    """Build a minimal policy_evaluation dict."""
    return {
        "waiting_period": {
            "passed": waiting_passed,
            "reason": "Waiting period cleared" if waiting_passed else "Not cleared",
        },
        "exclusions": {
            "excluded": excluded,
            "exclusion_reason": "Excluded" if excluded else None,
        },
        "eligible_amount": {
            "eligible_amount": eligible_amount,
            "sub_limit_applied": sub_limit_applied,
            "calculation_breakdown": ["Sum insured: ₹500,000.00", f"Final eligible amount: ₹{eligible_amount:,.2f}"],
        },
        "pre_auth": {"required": False, "reason": "Not required"},
        "is_network_hospital": True,
        "passed": waiting_passed and not excluded,
    }


def _fraud(*, flagged: bool = False, score: float = 0.0) -> dict:
    return {
        "auto_manual_review": flagged,
        "fraud_flags": ["High-value claim"] if flagged else [],
        "fraud_score": score,
    }


class TestDecisionAgent:
    def test_approved_when_all_checks_pass(self, agent):
        result = agent.decide(True, _policy_result(), _fraud())
        assert result["decision"] == ClaimDecision.APPROVED
        assert result["approved_amount"] == pytest.approx(5000.0)
        assert result["confidence_score"] > 0

    def test_rejected_when_verification_failed(self, agent):
        result = agent.decide(False, _policy_result(), _fraud())
        assert result["decision"] == ClaimDecision.REJECTED
        assert result["approved_amount"] == 0.0

    def test_manual_review_when_fraud_flagged(self, agent):
        result = agent.decide(True, _policy_result(), _fraud(flagged=True, score=0.33))
        assert result["decision"] == ClaimDecision.MANUAL_REVIEW

    def test_rejected_when_waiting_period_not_cleared(self, agent):
        result = agent.decide(True, _policy_result(waiting_passed=False), _fraud())
        assert result["decision"] == ClaimDecision.REJECTED

    def test_rejected_when_excluded(self, agent):
        result = agent.decide(True, _policy_result(excluded=True), _fraud())
        assert result["decision"] == ClaimDecision.REJECTED

    def test_partial_when_sub_limit_applied(self, agent):
        result = agent.decide(True, _policy_result(sub_limit_applied=True, eligible_amount=18000.0), _fraud())
        assert result["decision"] == ClaimDecision.PARTIAL
        assert result["approved_amount"] == pytest.approx(18000.0)

    def test_decision_reason_is_populated(self, agent):
        result = agent.decide(True, _policy_result(), _fraud())
        assert result["decision_reason"]
        assert len(result["decision_reason"]) > 5

    def test_confidence_score_between_0_and_1(self, agent):
        result = agent.decide(True, _policy_result(), _fraud())
        assert 0.0 <= result["confidence_score"] <= 1.0
