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

    Real policy structure (PLUM_GHI_2024):
    - coverage.sum_insured_per_employee — applies to all members
    - coverage.per_claim_limit — max per single consultation claim
    - opd_categories.<type> — sub_limit, copay_percent, network_discount_percent
    - fraud_thresholds — same_day_claims_limit / monthly_claims_limit / high_value_claim_threshold
    - members[].join_date — member onboarding date
    """

    def __init__(self, policy_path: str | Path) -> None:
        """Load and cache the policy file from *policy_path*."""
        self._path = Path(policy_path)
        self._policy: dict[str, Any] = self._load()
        logger.info(
            "PolicyEngine loaded from %s (policy_id=%s)", self._path, self.policy_id
        )

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
        return self._policy.get("policy_id", "unknown")

    @property
    def insurer(self) -> str:
        return self._policy.get("insurer", "unknown")

    @property
    def product_name(self) -> str:
        return self._policy.get("policy_name", self._policy.get("product_name", "unknown"))

    def _members(self) -> list[dict]:
        return self._policy.get("members", [])

    def _coverage(self) -> dict:
        return self._policy.get("coverage", {})

    def _opd_category(self, claim_type: str) -> dict:
        """Return the OPD category config for *claim_type* (case-insensitive lookup)."""
        return self._policy.get("opd_categories", {}).get(claim_type.lower(), {})

    def _exclusions(self) -> dict:
        return self._policy.get("exclusions", {})

    def _fraud(self) -> dict:
        # Real policy uses "fraud_thresholds" at top level
        return self._policy.get("fraud_thresholds", self._policy.get("fraud_detection", {}).get("thresholds", {}))

    def _waiting_periods(self) -> dict:
        return self._policy.get("waiting_periods", {})

    def _parse_date(self, date_str: str) -> date:
        return datetime.strptime(date_str, "%Y-%m-%d").date()

    # Generic medical/procedure words that alone cannot trigger an exclusion match.
    # These must not cause false positives when shared between covered and excluded items.
    _GENERIC_WORDS = frozenset({
        "treatment", "procedure", "procedures", "surgery", "therapy", "therapies",
        "program", "programs", "care", "service", "services", "consultation",
        "examination", "session", "sessions", "medicine", "medication", "medications",
    })

    def _matches_exclusion(self, text: str, exclusion: str) -> bool:
        """
        Case-insensitive keyword match between *text* and *exclusion*.

        Returns True when the exclusion phrase is found in the text (or vice-versa),
        OR when a *distinctive* word from the exclusion (not a generic term like
        'treatment' or 'surgery') appears in the text.

        Generic medical words are intentionally blocked so that "Root Canal Treatment"
        does not false-match "Orthodontic Treatment (Braces)" via the shared word
        "treatment".
        """
        import re as _re
        t = text.lower().strip()
        # Strip parenthetical notes from exclusion for cleaner matching
        e = _re.sub(r"\([^)]*\)", "", exclusion.lower()).strip()
        if e in t or t in e:
            return True
        # Word-level: only use distinctive words (not generic medical terms)
        words = [
            w for w in e.split()
            if len(w) >= 4 and w not in self._GENERIC_WORDS
        ]
        return bool(words) and any(w in t for w in words)

    # ------------------------------------------------------------------
    # Member methods
    # ------------------------------------------------------------------

    def get_member(self, member_id: str) -> dict | None:
        """Return the member record for *member_id*, or None if not found."""
        for m in self._members():
            if m.get("member_id") == member_id:
                return m
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

        Returns ``{required: [...], optional: [...]}`` where each entry is a
        DocumentType string.  Falls back to empty lists when the claim type is
        not configured.
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
        1. Initial waiting period (30 days after joining).
        2. Specific condition waiting periods — matched by keywords in *diagnosis*
           (e.g. "diabetes" triggers the 90-day diabetes waiting period).

        Returns::

            {
                passed: bool,
                waiting_period_days: int,   # longest applicable period
                days_since_joining: int,
                days_remaining: int,        # 0 if passed
                eligible_from: str,         # YYYY-MM-DD when member becomes eligible
                reason: str
            }
        """
        wp = self._waiting_periods()
        initial_days: int = wp.get("initial_waiting_period_days", 30)
        specific: dict = wp.get("specific_conditions", {})

        member = self.get_member(member_id)
        if not member:
            return {
                "passed": False,
                "waiting_period_days": 0,
                "days_since_joining": 0,
                "days_remaining": 0,
                "eligible_from": "",
                "reason": f"Member {member_id} not found in policy",
            }

        # Support both join_date (real policy) and date_of_joining (legacy)
        join_str = member.get("join_date") or member.get("date_of_joining", "")
        joining_date = self._parse_date(join_str)
        claim_dt = self._parse_date(claim_date)
        days_since_joining = (claim_dt - joining_date).days

        applicable_days = initial_days
        reason = f"Initial waiting period of {initial_days} days"

        # Check specific condition waiting periods by keyword matching diagnosis
        diagnosis_lower = [d.lower() for d in diagnosis]
        for condition_key, condition_days in specific.items():
            key_lower = condition_key.lower().replace("_", " ")
            for diag in diagnosis_lower:
                if self._matches_exclusion(diag, key_lower):
                    if condition_days > applicable_days:
                        applicable_days = condition_days
                        reason = (
                            f"Condition '{condition_key}' has a {condition_days}-day waiting period"
                        )
                    break

        days_remaining = max(0, applicable_days - days_since_joining)
        passed = days_since_joining >= applicable_days

        from datetime import timedelta
        eligible_date = joining_date + timedelta(days=applicable_days)

        return {
            "passed": passed,
            "waiting_period_days": applicable_days,
            "days_since_joining": days_since_joining,
            "days_remaining": days_remaining,
            "eligible_from": eligible_date.strftime("%Y-%m-%d"),
            "reason": "Waiting period cleared" if passed else reason,
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
        Check whether any permanent exclusion applies to this claim.

        Checks:
        1. ``exclusions.conditions`` — general permanent exclusions (e.g. bariatric surgery)
        2. ``exclusions.dental_exclusions`` / ``exclusions.vision_exclusions`` for those categories
        3. ``opd_categories.<type>.excluded_procedures/excluded_items``

        Returns::

            {
                excluded: bool,
                exclusion_reason: str | None,
                excluded_items: list[str]
            }
        """
        excl = self._exclusions()
        general_conditions: list[str] = excl.get("conditions", [])

        # Build category-specific exclusion list
        category_exclusions: list[str] = []
        ct = claim_type.upper()
        if ct == "DENTAL":
            category_exclusions.extend(excl.get("dental_exclusions", []))
            category_exclusions.extend(self._opd_category("dental").get("excluded_procedures", []))
        elif ct == "VISION":
            category_exclusions.extend(excl.get("vision_exclusions", []))
            category_exclusions.extend(self._opd_category("vision").get("excluded_items", []))

        all_exclusions = general_conditions + category_exclusions
        all_text = list(diagnosis) + list(treatment_items)
        excluded_found: list[str] = []

        for text in all_text:
            for excl_entry in all_exclusions:
                if self._matches_exclusion(text, excl_entry):
                    excluded_found.append(text)
                    break

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

        Financial rules applied in order:
        1. Per-claim limit check (for CONSULTATION — rejects immediately if exceeded).
        2. Item-level exclusion filtering (dental/vision category exclusions).
        3. Sub-limit cap (non-consultation categories only).
        4. Network discount (applied FIRST before co-pay).
        5. Co-pay deduction (applied AFTER network discount).

        *items* is a list of ``{description: str, amount: float}`` dicts.
        When *items* is empty, the full *claimed_amount* is used as the base.

        Returns::

            {
                eligible_amount: float,
                copay_amount: float,
                sub_limit: float,
                sub_limit_applied: bool,
                per_claim_exceeded: bool,
                network_discount_applied: bool,
                approved_items: list[dict],   # [{description, amount}]
                rejected_items: list[dict],   # [{description, amount, reason}]
                calculation_breakdown: list[str],
            }
        """
        coverage = self._coverage()
        opd_cat = self._opd_category(claim_type)
        breakdown: list[str] = []

        sum_insured: float = coverage.get("sum_insured_per_employee", float("inf"))
        per_claim_limit: float = coverage.get("per_claim_limit", float("inf"))
        ct = claim_type.upper()

        breakdown.append(f"Sum insured (per employee): ₹{sum_insured:,.2f}")
        breakdown.append(f"Claimed amount: ₹{claimed_amount:,.2f}")

        # ── Step 1: Per-claim limit (CONSULTATION only) ──────────────────
        if ct == "CONSULTATION" and claimed_amount > per_claim_limit:
            breakdown.append(
                f"Per-claim limit exceeded: ₹{claimed_amount:,.2f} > ₹{per_claim_limit:,.2f}"
            )
            return {
                "eligible_amount": 0.0,
                "copay_amount": 0.0,
                "sub_limit": per_claim_limit,
                "sub_limit_applied": False,
                "per_claim_exceeded": True,
                "network_discount_applied": False,
                "approved_items": [],
                "rejected_items": [
                    {
                        "description": "All items",
                        "amount": claimed_amount,
                        "reason": (
                            f"Claimed amount ₹{claimed_amount:,.2f} exceeds the "
                            f"per-claim limit of ₹{per_claim_limit:,.2f}"
                        ),
                    }
                ],
                "calculation_breakdown": breakdown,
            }

        # ── Step 2: Item-level exclusion filtering ───────────────────────
        excl = self._exclusions()
        category_excl: list[str] = []
        if ct == "DENTAL":
            category_excl.extend(excl.get("dental_exclusions", []))
            category_excl.extend(opd_cat.get("excluded_procedures", []))
        elif ct == "VISION":
            category_excl.extend(excl.get("vision_exclusions", []))
            category_excl.extend(opd_cat.get("excluded_items", []))

        approved_items: list[dict] = []
        rejected_items: list[dict] = []

        if items:
            for item in items:
                desc = item.get("description", "")
                amount = float(item.get("amount", 0))
                matched_excl = next(
                    (e for e in category_excl if self._matches_exclusion(desc, e)), None
                )
                if matched_excl:
                    rejected_items.append(
                        {
                            "description": desc,
                            "amount": amount,
                            "reason": (
                                f"Excluded: '{matched_excl}' is not covered "
                                f"under {ct} benefits"
                            ),
                        }
                    )
                else:
                    approved_items.append({"description": desc, "amount": amount})

            approved_base = sum(i["amount"] for i in approved_items)
            if rejected_items:
                rejected_total = sum(i["amount"] for i in rejected_items)
                breakdown.append(
                    f"Excluded line items: ₹{rejected_total:,.2f} "
                    f"({', '.join(i['description'] for i in rejected_items)})"
                )
                breakdown.append(f"Base eligible after exclusions: ₹{approved_base:,.2f}")
        else:
            approved_base = claimed_amount

        # ── Step 3: Sub-limit cap (non-consultation categories) ──────────
        sub_limit: float = opd_cat.get("sub_limit", float("inf"))
        sub_limit_applied = False
        eligible = min(approved_base, sum_insured)

        # For CONSULTATION the per-claim limit already serves as the cap.
        # For all other categories apply their own sub_limit.
        if ct != "CONSULTATION" and sub_limit < eligible:
            eligible = sub_limit
            sub_limit_applied = True
            breakdown.append(f"Sub-limit applied for {ct}: ₹{sub_limit:,.2f}")
        else:
            sub_limit_label = f"₹{sub_limit:,.2f}" if sub_limit != float("inf") else "none"
            breakdown.append(f"Sub-limit ({sub_limit_label}) not breached")

        # ── Step 4: Network discount (applied FIRST) ─────────────────────
        network_discount_pct: float = opd_cat.get("network_discount_percent", 0)
        network_discount_applied = False

        if is_network_hospital and network_discount_pct > 0:
            discount = eligible * (network_discount_pct / 100)
            eligible -= discount
            network_discount_applied = True
            breakdown.append(
                f"Network discount {network_discount_pct}%: "
                f"-₹{discount:,.2f} → ₹{eligible:,.2f}"
            )

        # ── Step 5: Co-pay (applied AFTER discount) ───────────────────────
        copay_pct: float = opd_cat.get("copay_percent", 0)
        copay_amount = 0.0

        if copay_pct > 0:
            copay_amount = eligible * (copay_pct / 100)
            eligible -= copay_amount
            breakdown.append(
                f"Co-pay {copay_pct}%: -₹{copay_amount:,.2f} → ₹{eligible:,.2f}"
            )

        eligible = round(max(0.0, eligible), 2)
        copay_amount = round(copay_amount, 2)
        breakdown.append(f"Final eligible amount: ₹{eligible:,.2f}")

        return {
            "eligible_amount": eligible,
            "copay_amount": copay_amount,
            "sub_limit": sub_limit if sub_limit != float("inf") else 0.0,
            "sub_limit_applied": sub_limit_applied,
            "per_claim_exceeded": False,
            "network_discount_applied": network_discount_applied,
            "approved_items": approved_items,
            "rejected_items": rejected_items,
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

        For DIAGNOSTIC claims: pre-auth is required when the test is in
        ``opd_categories.diagnostic.high_value_tests_requiring_pre_auth``
        AND the amount exceeds ``opd_categories.diagnostic.pre_auth_threshold``.
        The general ``pre_authorization.required_for`` list is NOT applied to
        DIAGNOSTIC claims because it contains the same test names with implicit
        amount conditions and would fire regardless of amount.

        For other categories: checks ``pre_authorization.required_for`` list
        by keyword matching against treatment items.

        Returns ``{required: bool, reason: str}``.
        """
        ct = claim_type.upper()
        diag_cat = self._opd_category("diagnostic")

        if ct == "DIAGNOSTIC":
            pre_auth_threshold: float = diag_cat.get("pre_auth_threshold", float("inf"))
            high_value_tests: list[str] = diag_cat.get("high_value_tests_requiring_pre_auth", [])
            for item in treatment_items:
                for hvt in high_value_tests:
                    if self._matches_exclusion(item, hvt):
                        if claimed_amount > pre_auth_threshold:
                            return {
                                "required": True,
                                "reason": (
                                    f"{hvt} requires pre-authorisation when the amount exceeds "
                                    f"₹{pre_auth_threshold:,.0f}. "
                                    "Please obtain pre-auth before undergoing the procedure "
                                    "and resubmit with the pre-auth reference number."
                                ),
                            }
            # DIAGNOSTIC claim checked via structured threshold — do not fall through
            # to the general list (which contains the same test names without amounts).
            return {"required": False, "reason": "Pre-authorisation not required"}

        # Non-DIAGNOSTIC: check general pre-auth list
        pre_auth: dict = self._policy.get("pre_authorization", {})
        required_for: list[str] = pre_auth.get("required_for", [])
        for item in treatment_items:
            for req in required_for:
                if self._matches_exclusion(item, req):
                    return {
                        "required": True,
                        "reason": (
                            f"Treatment '{item}' requires pre-authorisation. "
                            "Please obtain pre-auth before proceeding."
                        ),
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
        if not hospital_name:
            return False
        network: list[str] = self._policy.get("network_hospitals", [])
        h = hospital_name.lower()
        return any(n.lower() in h or h in n.lower() for n in network)

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

        Real policy uses ``fraud_thresholds`` with keys:
        - same_day_claims_limit
        - monthly_claims_limit
        - high_value_claim_threshold

        Returns::

            {
                auto_manual_review: bool,
                fraud_flags: list[str],
                fraud_score: float          # 0.0 – 1.0
            }
        """
        fraud = self._fraud()

        high_value: float = fraud.get(
            "high_value_claim_threshold",
            fraud.get("high_value_claim", float("inf")),
        )
        max_same_day: int = fraud.get(
            "same_day_claims_limit",
            fraud.get("max_same_day_claims", 999),
        )
        max_monthly: int = fraud.get(
            "monthly_claims_limit",
            fraud.get("max_monthly_claims", 999),
        )

        flags: list[str] = []

        if claimed_amount >= high_value:
            flags.append(
                f"High-value claim: ₹{claimed_amount:,.2f} meets or exceeds "
                f"threshold ₹{high_value:,.2f}"
            )
        if same_day_claim_count >= max_same_day:
            flags.append(
                f"Unusual same-day claim frequency: {same_day_claim_count + 1} claims "
                f"today (limit {max_same_day})"
            )
        if monthly_claim_count >= max_monthly:
            flags.append(
                f"Unusual monthly claim frequency: {monthly_claim_count + 1} claims "
                f"this month (limit {max_monthly})"
            )

        fraud_score = round(len(flags) / 3, 4)
        auto_manual_review = len(flags) > 0

        return {
            "auto_manual_review": auto_manual_review,
            "fraud_flags": flags,
            "fraud_score": fraud_score,
        }
