"""Tests for DecisionAgent — covers all 12 test case scenarios."""

from __future__ import annotations

import pytest

from agents.decision import DecisionAgent
from models.claim import ClaimDecision


@pytest.fixture
def agent():
    return DecisionAgent()


def _policy(
    *,
    waiting_passed: bool = True,
    waiting_reason: str = "Waiting period cleared",
    eligible_from: str = "2024-01-01",
    excluded: bool = False,
    exclusion_reason: str | None = None,
    eligible_amount: float = 5000.0,
    copay_amount: float = 0.0,
    sub_limit_applied: bool = False,
    per_claim_exceeded: bool = False,
    approved_items: list | None = None,
    rejected_items: list | None = None,
    pre_auth_required: bool = False,
    pre_auth_reason: str = "Not required",
) -> dict:
    return {
        "waiting_period": {
            "passed": waiting_passed,
            "reason": waiting_reason,
            "eligible_from": eligible_from,
        },
        "exclusions": {
            "excluded": excluded,
            "exclusion_reason": exclusion_reason,
        },
        "eligible_amount": {
            "eligible_amount": eligible_amount,
            "copay_amount": copay_amount,
            "sub_limit_applied": sub_limit_applied,
            "per_claim_exceeded": per_claim_exceeded,
            "approved_items": approved_items or [],
            "rejected_items": rejected_items or [],
            "calculation_breakdown": ["Final eligible amount: ₹{:.2f}".format(eligible_amount)],
        },
        "pre_auth": {"required": pre_auth_required, "reason": pre_auth_reason},
        "is_network_hospital": False,
        "passed": waiting_passed and not pre_auth_required and not per_claim_exceeded,
    }


def _fraud(*, flagged: bool = False, score: float = 0.0, flags: list | None = None) -> dict:
    return {
        "auto_manual_review": flagged,
        "fraud_flags": flags or (["High-value claim"] if flagged else []),
        "fraud_score": score,
    }


class TestDecisionAgent:
    def test_tc004_approved_clean_consultation(self, agent):
        """TC004: clean consultation → APPROVED."""
        result = agent.decide(True, _policy(eligible_amount=1350.0, copay_amount=150.0), _fraud())
        assert result["decision"] == ClaimDecision.APPROVED
        assert result["approved_amount"] == pytest.approx(1350.0)
        assert result["confidence_score"] > 0.85

    def test_tc005_rejected_waiting_period(self, agent):
        """TC005: diabetes waiting period → REJECTED (WAITING_PERIOD)."""
        result = agent.decide(
            True,
            _policy(waiting_passed=False, waiting_reason="Condition 'diabetes' has 90-day wait", eligible_from="2024-11-30"),
            _fraud(),
        )
        assert result["decision"] == ClaimDecision.REJECTED
        assert "WAITING_PERIOD" in result["rejection_reasons"]
        # Must include the eligible-from date
        assert "2024-11-30" in result["decision_reason"]

    def test_tc006_partial_dental_exclusion(self, agent):
        """TC006: root canal approved, teeth whitening excluded → PARTIAL."""
        result = agent.decide(
            True,
            _policy(
                eligible_amount=8000.0,
                approved_items=[{"description": "Root Canal Treatment", "amount": 8000}],
                rejected_items=[{"description": "Teeth Whitening", "amount": 4000, "reason": "Excluded"}],
            ),
            _fraud(),
        )
        assert result["decision"] == ClaimDecision.PARTIAL
        assert result["approved_amount"] == pytest.approx(8000.0)
        assert len(result["rejected_items"]) == 1

    def test_tc007_rejected_pre_auth_missing(self, agent):
        """TC007: MRI without pre-auth → REJECTED (PRE_AUTH_MISSING)."""
        result = agent.decide(
            True,
            _policy(pre_auth_required=True, pre_auth_reason="MRI requires pre-auth above 10000"),
            _fraud(),
        )
        assert result["decision"] == ClaimDecision.REJECTED
        assert "PRE_AUTH_MISSING" in result["rejection_reasons"]
        assert "pre" in result["decision_reason"].lower()

    def test_tc008_rejected_per_claim_exceeded(self, agent):
        """TC008: 7500 > per_claim_limit 5000 → REJECTED (PER_CLAIM_EXCEEDED)."""
        result = agent.decide(
            True,
            _policy(
                per_claim_exceeded=True,
                eligible_amount=0.0,
                rejected_items=[{"description": "All items", "amount": 7500,
                                  "reason": "Claimed 7500 exceeds per-claim limit 5000"}],
            ),
            _fraud(),
        )
        assert result["decision"] == ClaimDecision.REJECTED
        assert "PER_CLAIM_EXCEEDED" in result["rejection_reasons"]

    def test_tc009_manual_review_fraud_flags(self, agent):
        """TC009: 4 same-day claims → MANUAL_REVIEW."""
        result = agent.decide(
            True,
            _policy(eligible_amount=4800.0),
            _fraud(
                flagged=True,
                score=0.33,
                flags=["Unusual same-day claim frequency: 4 claims today (limit 2)"],
            ),
        )
        assert result["decision"] == ClaimDecision.MANUAL_REVIEW
        assert "same-day" in result["decision_reason"].lower() or "unusual" in result["decision_reason"].lower()

    def test_tc010_approved_with_network_discount(self, agent):
        """TC010: Apollo (network) → approved 3240 after 20% discount + 10% copay."""
        result = agent.decide(
            True,
            _policy(eligible_amount=3240.0, copay_amount=360.0),
            _fraud(),
        )
        assert result["decision"] == ClaimDecision.APPROVED
        assert result["approved_amount"] == pytest.approx(3240.0)

    def test_tc012_rejected_excluded_condition(self, agent):
        """TC012: bariatric/obesity treatment → REJECTED (EXCLUDED_CONDITION)."""
        result = agent.decide(
            True,
            _policy(
                excluded=True,
                exclusion_reason="Bariatric surgery and obesity programs are excluded",
                eligible_amount=0.0,
            ),
            _fraud(),
        )
        assert result["decision"] == ClaimDecision.REJECTED
        assert "EXCLUDED_CONDITION" in result["rejection_reasons"]
        assert result["confidence_score"] >= 0.90

    def test_verification_failed_overrides_all(self, agent):
        """Verification failure must reject regardless of other checks."""
        result = agent.decide(False, _policy(), _fraud())
        assert result["decision"] == ClaimDecision.REJECTED
        assert result["approved_amount"] == 0.0

    def test_fraud_takes_priority_over_policy_pass(self, agent):
        """Fraud flag routes to manual review even when policy checks pass."""
        result = agent.decide(True, _policy(), _fraud(flagged=True, score=0.33))
        assert result["decision"] == ClaimDecision.MANUAL_REVIEW

    def test_exclusion_takes_priority_over_waiting_period(self, agent):
        """Permanent exclusion is checked before waiting period (TC012 vs TC005)."""
        result = agent.decide(
            True,
            _policy(
                waiting_passed=False,
                excluded=True,
                exclusion_reason="Bariatric surgery excluded",
                eligible_amount=0.0,
            ),
            _fraud(),
        )
        # Exclusion fires before waiting period
        assert result["decision"] == ClaimDecision.REJECTED
        assert "EXCLUDED_CONDITION" in result["rejection_reasons"]

    def test_confidence_score_in_range(self, agent):
        result = agent.decide(True, _policy(), _fraud())
        assert 0.0 <= result["confidence_score"] <= 1.0

    def test_decision_reason_always_populated(self, agent):
        result = agent.decide(True, _policy(), _fraud())
        assert result["decision_reason"]
        assert len(result["decision_reason"]) > 5
