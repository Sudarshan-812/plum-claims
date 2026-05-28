"""Policy engine — reads policy_terms.json and enforces every rule."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PolicyEngine:
    """
    Single source of truth for all policy rules.

    Loads policy_terms.json once at startup and exposes typed methods
    for every rule check needed by the processing agents.  Nothing is
    hard-coded — all thresholds, limits and lists come from the JSON.
    """

    def __init__(self, policy_path: str | Path) -> None:
        """Load and cache the policy file from *policy_path*."""
        self._path = Path(policy_path)
        self._policy: dict[str, Any] = self._load()
        logger.info("PolicyEngine loaded from %s (policy_id=%s)", self._path, self.policy_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        """Read and parse the policy JSON file."""
        if not self._path.exists():
            raise FileNotFoundError(f"Policy file not found: {self._path}")
        with open(self._path, encoding="utf-8") as fh:
            return json.load(fh)

    @property
    def policy_id(self) -> str:
        """Return the policy identifier from the loaded JSON."""
        return self._policy.get("policy_id", "unknown")

    @property
    def insurer(self) -> str:
        """Return the insurer name from the loaded JSON."""
        return self._policy.get("insurer", "unknown")

    @property
    def product_name(self) -> str:
        """Return the product name from the loaded JSON."""
        return self._policy.get("product_name", "unknown")

    def _members(self) -> list[dict]:
        return self._policy.get("members", [])

    def _coverage(self) -> dict:
        return self._policy.get("coverage", {})

    def _exclusions(self) -> dict:
        return self._policy.get("exclusions", {})

    def _fraud(self) -> dict:
        return self._policy.get("fraud_detection", {})

    def _waiting_periods(self) -> dict:
        return self._policy.get("waiting_periods", {})

    def _parse_date(self, date_str: str) -> date:
        """Parse a YYYY-MM-DD string into a date object."""
        return datetime.strptime(date_str, "%Y-%m-%d").date()

    # ------------------------------------------------------------------
    # Member methods
    # ------------------------------------------------------------------

    def get_member(self, member_id: str) -> dict | None:
        """Return the member record for *member_id*, or None if not found."""
        for member in self._members():
            if member.get("member_id") == member_id:
                return member
        return None

    def is_member_active(self, member_id: str) -> bool:
        """Return True if *member_id* exists in the policy members list."""
        return self.get_member(member_id) is not None

    # ------------------------------------------------------------------
    # Document requirements
    # ------------------------------------------------------------------

    def get_required_documents(self, claim_type: str) -> dict:
        """
        Return the document requirements for a given claim type.

        Returns a dict ``{required: [...], optional: [...]}`` where each
        entry is a document type string.  Falls back to empty lists when
        the claim type is not configured.
        """
        doc_reqs: dict = self._policy.get("document_requirements", {})
        claim_docs = doc_reqs.get(claim_type.upper(), {})
        return {
            "required": claim_docs.get("required", []),
            "optional": claim_docs.get("optional", []),
        }

    # ------------------------------------------------------------------
    # Waiting periods
    # ------------------------------------------------------------------

    def check_waiting_period(
        self,
        member_id: str,
        claim_date: str,
        diagnosis: list[str],
    ) -> dict:
        """
        Evaluate all waiting-period rules for a member and claim date.

        Checks (in order):
        1. Initial waiting period (e.g. 30 days after joining).
        2. Pre-existing condition waiting period if any diagnosis matches
           the member's pre_existing_conditions list.
        3. Specific condition waiting periods configured in the policy.

        Returns::

            {
                passed: bool,
                waiting_period_days: int,   # longest applicable period
                days_since_joining: int,
                days_remaining: int,        # 0 if passed
                reason: str
            }
        """
        wp = self._waiting_periods()
        initial_days: int = wp.get("initial_waiting_period_days", 30)
        pre_existing_days: int = wp.get("pre_existing_condition_days", 365)
        specific: dict = wp.get("specific_conditions", {})

        member = self.get_member(member_id)
        if not member:
            return {
                "passed": False,
                "waiting_period_days": 0,
                "days_since_joining": 0,
                "days_remaining": 0,
                "reason": f"Member {member_id} not found in policy",
            }

        joining_date = self._parse_date(member["date_of_joining"])
        claim_dt = self._parse_date(claim_date)
        days_since_joining = (claim_dt - joining_date).days

        # Determine the longest applicable waiting period
        applicable_days = initial_days
        reason = f"Initial waiting period of {initial_days} days"

        # Check pre-existing conditions
        pre_existing: list[str] = [c.lower() for c in member.get("pre_existing_conditions", [])]
        diagnosis_lower = [d.lower() for d in diagnosis]

        for diag in diagnosis_lower:
            for pre_cond in pre_existing:
                if pre_cond in diag or diag in pre_cond:
                    if pre_existing_days > applicable_days:
                        applicable_days = pre_existing_days
                        reason = (
                            f"Pre-existing condition '{pre_cond}' requires "
                            f"{pre_existing_days}-day waiting period"
                        )
                    break

        # Check specific condition waiting periods
        for diag in diagnosis_lower:
            for condition_key, condition_days in specific.items():
                if condition_key.lower() in diag or diag in condition_key.lower():
                    if condition_days > applicable_days:
                        applicable_days = condition_days
                        reason = (
                            f"Condition '{condition_key}' requires "
                            f"{condition_days}-day waiting period"
                        )

        days_remaining = max(0, applicable_days - days_since_joining)
        passed = days_since_joining >= applicable_days

        return {
            "passed": passed,
            "waiting_period_days": applicable_days,
            "days_since_joining": days_since_joining,
            "days_remaining": days_remaining,
            "reason": reason if not passed else "Waiting period cleared",
        }

    # ------------------------------------------------------------------
    # Exclusions
    # ------------------------------------------------------------------

    def check_exclusions(
        self,
        claim_type: str,
        diagnosis: list[str],
        treatment_items: list[str],
    ) -> dict:
        """
        Check whether any exclusion applies to this claim.

        Checks permanent exclusions (procedures, diagnoses) and any
        claim-type-specific exclusions configured in the policy.

        Returns::

            {
                excluded: bool,
                exclusion_reason: str | None,
                excluded_items: list[str]
            }
        """
        excl = self._exclusions()
        excluded_procedures: list[str] = [p.lower() for p in excl.get("procedures", [])]
        excluded_diagnoses: list[str] = [d.lower() for d in excl.get("diagnoses", [])]
        type_exclusions: list[str] = [
            e.lower()
            for e in excl.get("claim_type_exclusions", {}).get(claim_type.upper(), [])
        ]

        all_items_lower = [i.lower() for i in treatment_items]
        all_diagnosis_lower = [d.lower() for d in diagnosis]
        excluded_found: list[str] = []

        for item in all_items_lower:
            for excl_proc in excluded_procedures:
                if excl_proc in item or item in excl_proc:
                    excluded_found.append(item)
            for te in type_exclusions:
                if te in item or item in te:
                    excluded_found.append(item)

        for diag in all_diagnosis_lower:
            for excl_diag in excluded_diagnoses:
                if excl_diag in diag or diag in excl_diag:
                    excluded_found.append(diag)

        excluded_found = list(set(excluded_found))
        excluded = len(excluded_found) > 0

        return {
            "excluded": excluded,
            "exclusion_reason": (
                f"The following are excluded from coverage: {', '.join(excluded_found)}"
                if excluded
                else None
            ),
            "excluded_items": excluded_found,
        }

    # ------------------------------------------------------------------
    # Eligible amount calculation
    # ------------------------------------------------------------------

    def calculate_eligible_amount(
        self,
        member_id: str,
        claim_type: str,
        claimed_amount: float,
        is_network_hospital: bool,
        items: list[dict],
    ) -> dict:
        """
        Calculate the amount eligible for reimbursement after applying all rules.

        Applies (in order):
        1. Sum insured cap check.
        2. Sub-limit for the claim type.
        3. Non-network discount (if applicable).
        4. Co-pay deduction.

        *items* is a list of ``{description: str, amount: float}`` dicts.

        Returns::

            {
                eligible_amount: float,
                copay_amount: float,
                sub_limit: float,
                sub_limit_applied: bool,
                network_discount_applied: bool,
                calculation_breakdown: list[str]
            }
        """
        member = self.get_member(member_id)
        coverage = self._coverage()
        breakdown: list[str] = []

        sum_insured: float = member["sum_insured"] if member else float("inf")
        breakdown.append(f"Sum insured: ₹{sum_insured:,.2f}")
        breakdown.append(f"Claimed amount: ₹{claimed_amount:,.2f}")

        # Sub-limits per claim type
        sub_limits: dict = coverage.get("sub_limits", {})
        sub_limit: float = sub_limits.get(claim_type.upper(), float("inf"))
        sub_limit_applied = False

        eligible = min(claimed_amount, sum_insured)

        if sub_limit < eligible:
            eligible = sub_limit
            sub_limit_applied = True
            breakdown.append(f"Sub-limit applied for {claim_type}: ₹{sub_limit:,.2f}")
        else:
            breakdown.append(f"No sub-limit applied (limit ₹{sub_limit:,.2f} not exceeded)")

        # Non-network hospital penalty
        non_network_discount = coverage.get("non_network_penalty_percent", 0)
        network_discount_applied = False

        if not is_network_hospital and non_network_discount > 0:
            penalty = eligible * (non_network_discount / 100)
            eligible -= penalty
            network_discount_applied = True
            breakdown.append(
                f"Non-network hospital penalty {non_network_discount}%: -₹{penalty:,.2f}"
            )

        # Co-pay
        copay_percent: float = coverage.get("copay_percent", 0)
        copay_amount = 0.0

        if copay_percent > 0:
            copay_amount = eligible * (copay_percent / 100)
            eligible -= copay_amount
            breakdown.append(
                f"Co-pay {copay_percent}%: -₹{copay_amount:,.2f}"
            )

        eligible = round(max(0.0, eligible), 2)
        copay_amount = round(copay_amount, 2)

        breakdown.append(f"Final eligible amount: ₹{eligible:,.2f}")

        return {
            "eligible_amount": eligible,
            "copay_amount": copay_amount,
            "sub_limit": sub_limit if sub_limit != float("inf") else 0.0,
            "sub_limit_applied": sub_limit_applied,
            "network_discount_applied": network_discount_applied,
            "calculation_breakdown": breakdown,
        }

    # ------------------------------------------------------------------
    # Pre-authorisation
    # ------------------------------------------------------------------

    def requires_pre_authorization(
        self,
        claim_type: str,
        claimed_amount: float,
        treatment_items: list[str],
    ) -> dict:
        """
        Determine whether pre-authorisation is required for this claim.

        Pre-auth is required when:
        - The amount exceeds the configured threshold, OR
        - The claim type is in the pre-auth-required list, OR
        - Any treatment item matches the pre-auth procedures list.

        Returns ``{required: bool, reason: str}``.
        """
        pre_auth: dict = self._policy.get("pre_authorization", {})
        amount_threshold: float = pre_auth.get("amount_threshold", float("inf"))
        required_types: list[str] = [t.upper() for t in pre_auth.get("required_for_types", [])]
        required_procedures: list[str] = [p.lower() for p in pre_auth.get("required_procedures", [])]

        if claimed_amount >= amount_threshold:
            return {
                "required": True,
                "reason": (
                    f"Claimed amount ₹{claimed_amount:,.2f} exceeds pre-auth "
                    f"threshold of ₹{amount_threshold:,.2f}"
                ),
            }

        if claim_type.upper() in required_types:
            return {
                "required": True,
                "reason": f"Pre-authorisation is mandatory for {claim_type} claims",
            }

        items_lower = [i.lower() for i in treatment_items]
        for item in items_lower:
            for proc in required_procedures:
                if proc in item or item in proc:
                    return {
                        "required": True,
                        "reason": f"Treatment '{item}' requires pre-authorisation",
                    }

        return {"required": False, "reason": "Pre-authorisation not required"}

    # ------------------------------------------------------------------
    # Network hospital check
    # ------------------------------------------------------------------

    def is_network_hospital(self, hospital_name: str) -> bool:
        """
        Return True if *hospital_name* matches any network hospital.

        Uses case-insensitive partial matching so abbreviations and
        slightly different spellings still resolve correctly.
        """
        network: list[str] = self._policy.get("network_hospitals", [])
        hospital_lower = hospital_name.lower()
        return any(n.lower() in hospital_lower or hospital_lower in n.lower() for n in network)

    # ------------------------------------------------------------------
    # Fraud detection thresholds
    # ------------------------------------------------------------------

    def check_fraud_thresholds(
        self,
        claimed_amount: float,
        same_day_claim_count: int,
        monthly_claim_count: int,
    ) -> dict:
        """
        Score a claim against fraud-detection thresholds from the policy.

        Returns::

            {
                auto_manual_review: bool,
                fraud_flags: list[str],
                fraud_score: float          # 0.0 – 1.0
            }

        The fraud score is the fraction of checks that triggered, so a
        score of 1.0 means every threshold was breached.
        """
        fraud = self._fraud()
        thresholds: dict = fraud.get("thresholds", {})

        high_value_threshold: float = thresholds.get("high_value_claim", float("inf"))
        max_same_day: int = thresholds.get("max_same_day_claims", 999)
        max_monthly: int = thresholds.get("max_monthly_claims", 999)

        flags: list[str] = []

        if claimed_amount >= high_value_threshold:
            flags.append(
                f"High-value claim: ₹{claimed_amount:,.2f} exceeds threshold "
                f"₹{high_value_threshold:,.2f}"
            )
        if same_day_claim_count >= max_same_day:
            flags.append(
                f"Unusual same-day claim frequency: {same_day_claim_count} "
                f"(max {max_same_day})"
            )
        if monthly_claim_count >= max_monthly:
            flags.append(
                f"Unusual monthly claim frequency: {monthly_claim_count} "
                f"(max {max_monthly})"
            )

        total_checks = 3
        fraud_score = round(len(flags) / total_checks, 4)
        auto_manual_review = len(flags) > 0

        return {
            "auto_manual_review": auto_manual_review,
            "fraud_flags": flags,
            "fraud_score": fraud_score,
        }
