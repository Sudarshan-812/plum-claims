"""Policy evaluation agent — applies all policy rules to a parsed claim."""

from __future__ import annotations

import logging

from services.policy_engine import PolicyEngine

logger = logging.getLogger(__name__)


class PolicyEvaluationAgent:
    """
    Runs the full suite of policy checks against extracted claim data and
    returns a combined evaluation result for the DecisionAgent.
    """

    def __init__(self, policy_engine: PolicyEngine) -> None:
        """Initialise with a loaded PolicyEngine instance."""
        self.policy_engine = policy_engine

    def evaluate(
        self,
        member_id: str,
        claim_type: str,
        claimed_amount: float,
        claim_date: str,
        diagnosis: list[str],
        treatment_items: list[str],
        hospital_name: str,
        line_items: list[dict] | None = None,
    ) -> dict:
        """
        Run all policy checks and return a combined evaluation result.

        *line_items* is an optional list of ``{description: str, amount: float}``
        dicts extracted from the bill.  When provided, item-level exclusion
        filtering is applied (enabling partial approvals).

        Returns a dict with keys:
        - waiting_period
        - exclusions
        - eligible_amount
        - pre_auth
        - is_network_hospital
        - passed
        """
        logger.info(
            "PolicyEvaluationAgent.evaluate started: member=%s type=%s amount=%.2f",
            member_id,
            claim_type,
            claimed_amount,
        )

        is_network = self.policy_engine.is_network_hospital(hospital_name)

        waiting = self.policy_engine.check_waiting_period(
            member_id, claim_date, diagnosis
        )
        exclusions = self.policy_engine.check_exclusions(
            claim_type, diagnosis, treatment_items
        )

        items = line_items or []
        eligible = self.policy_engine.calculate_eligible_amount(
            member_id=member_id,
            claim_type=claim_type,
            claimed_amount=claimed_amount,
            is_network_hospital=is_network,
            items=items,
        )
        pre_auth = self.policy_engine.requires_pre_authorization(
            claim_type, claimed_amount, treatment_items
        )

        passed = (
            waiting["passed"]
            and not pre_auth["required"]
            and not eligible.get("per_claim_exceeded")
        )

        result = {
            "waiting_period": waiting,
            "exclusions": exclusions,
            "eligible_amount": eligible,
            "pre_auth": pre_auth,
            "is_network_hospital": is_network,
            "passed": passed,
        }

        logger.info(
            "PolicyEvaluationAgent.evaluate completed: passed=%s eligible=%.2f",
            passed,
            eligible["eligible_amount"],
        )
        return result
