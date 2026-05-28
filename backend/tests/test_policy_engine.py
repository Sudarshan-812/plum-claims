"""Comprehensive tests for PolicyEngine."""

from __future__ import annotations

import pytest


# ------------------------------------------------------------------
# Member lookup
# ------------------------------------------------------------------

class TestMemberLookup:
    def test_existing_member_returned(self, engine):
        member = engine.get_member("MEM001")
        assert member is not None
        assert member["name"] == "Alice Sharma"

    def test_missing_member_returns_none(self, engine):
        assert engine.get_member("NONEXISTENT") is None

    def test_is_member_active_true(self, engine):
        assert engine.is_member_active("MEM001") is True

    def test_is_member_active_false(self, engine):
        assert engine.is_member_active("GHOST") is False


# ------------------------------------------------------------------
# Waiting periods
# ------------------------------------------------------------------

class TestWaitingPeriods:
    def test_initial_waiting_period_not_cleared(self, engine):
        # MEM002 joined 2026-05-15; day 15 = 2026-05-30 → 15 days in
        result = engine.check_waiting_period("MEM002", "2026-05-30", [])
        assert result["passed"] is False
        assert result["days_remaining"] > 0

    def test_initial_waiting_period_cleared(self, engine):
        # MEM001 joined 2024-01-01; 2026-05-28 → well past 30 days
        result = engine.check_waiting_period("MEM001", "2026-05-28", [])
        assert result["passed"] is True
        assert result["days_remaining"] == 0

    def test_exactly_on_waiting_period_boundary(self, engine):
        # MEM002 joined 2026-05-15; exactly 30 days later = 2026-06-14 (day 30 inclusive)
        result = engine.check_waiting_period("MEM002", "2026-06-14", [])
        assert result["passed"] is True

    def test_pre_existing_condition_waiting_period(self, engine):
        # MEM001 has hypertension; claim date is 100 days after joining (< 365)
        result = engine.check_waiting_period("MEM001", "2024-04-11", ["hypertension"])
        assert result["passed"] is False
        assert result["waiting_period_days"] == 365

    def test_pre_existing_condition_cleared_after_365_days(self, engine):
        # MEM001 joined 2024-01-01 + 400 days = 2025-02-05
        result = engine.check_waiting_period("MEM001", "2025-02-05", ["hypertension"])
        assert result["passed"] is True

    def test_specific_condition_diabetes(self, engine):
        # MEM001; 60 days in < 90 day diabetes waiting period
        result = engine.check_waiting_period("MEM001", "2024-03-01", ["type 2 diabetes"])
        assert result["passed"] is False
        assert result["waiting_period_days"] == 90

    def test_unknown_member_returns_fail(self, engine):
        result = engine.check_waiting_period("GHOST", "2026-01-01", [])
        assert result["passed"] is False
        assert "not found" in result["reason"].lower()


# ------------------------------------------------------------------
# Exclusions
# ------------------------------------------------------------------

class TestExclusions:
    def test_lasik_is_excluded(self, engine):
        result = engine.check_exclusions("VISION", [], ["LASIK eye surgery"])
        assert result["excluded"] is True
        assert len(result["excluded_items"]) > 0

    def test_teeth_whitening_is_excluded(self, engine):
        result = engine.check_exclusions("DENTAL", [], ["teeth whitening procedure"])
        assert result["excluded"] is True

    def test_normal_consultation_not_excluded(self, engine):
        result = engine.check_exclusions("CONSULTATION", ["fever"], ["paracetamol"])
        assert result["excluded"] is False
        assert result["exclusion_reason"] is None

    def test_self_inflicted_diagnosis_excluded(self, engine):
        result = engine.check_exclusions("CONSULTATION", ["self-inflicted injury"], [])
        assert result["excluded"] is True

    def test_dental_type_exclusion(self, engine):
        result = engine.check_exclusions("DENTAL", [], ["orthodontic retainer"])
        assert result["excluded"] is True


# ------------------------------------------------------------------
# Eligible amount calculation
# ------------------------------------------------------------------

class TestEligibleAmount:
    def test_sub_limit_applied_for_dental(self, engine):
        # Dental sub-limit is ₹20,000; claim ₹30,000
        result = engine.calculate_eligible_amount(
            member_id="MEM001",
            claim_type="DENTAL",
            claimed_amount=30000.0,
            is_network_hospital=True,
            items=[],
        )
        assert result["sub_limit_applied"] is True
        # After copay 10% on 20,000 → 18,000
        assert result["eligible_amount"] == pytest.approx(18000.0, abs=1)

    def test_no_sub_limit_for_consultation(self, engine):
        result = engine.calculate_eligible_amount(
            member_id="MEM001",
            claim_type="CONSULTATION",
            claimed_amount=5000.0,
            is_network_hospital=True,
            items=[],
        )
        assert result["sub_limit_applied"] is False

    def test_network_hospital_no_penalty(self, engine):
        result = engine.calculate_eligible_amount(
            member_id="MEM001",
            claim_type="CONSULTATION",
            claimed_amount=10000.0,
            is_network_hospital=True,
            items=[],
        )
        assert result["network_discount_applied"] is False
        # Only copay 10% deducted → 9000
        assert result["eligible_amount"] == pytest.approx(9000.0, abs=1)

    def test_non_network_hospital_penalty(self, engine):
        result = engine.calculate_eligible_amount(
            member_id="MEM001",
            claim_type="CONSULTATION",
            claimed_amount=10000.0,
            is_network_hospital=False,
            items=[],
        )
        assert result["network_discount_applied"] is True
        # 20% penalty on 10000 → 8000, then 10% copay → 7200
        assert result["eligible_amount"] == pytest.approx(7200.0, abs=1)

    def test_copay_deducted(self, engine):
        result = engine.calculate_eligible_amount(
            member_id="MEM001",
            claim_type="CONSULTATION",
            claimed_amount=20000.0,
            is_network_hospital=True,
            items=[],
        )
        # copay_percent=10 → copay_amount=2000
        assert result["copay_amount"] == pytest.approx(2000.0, abs=1)

    def test_sum_insured_cap(self, engine):
        # MEM002 sum_insured=300,000; claim=400,000
        result = engine.calculate_eligible_amount(
            member_id="MEM002",
            claim_type="CONSULTATION",
            claimed_amount=400000.0,
            is_network_hospital=True,
            items=[],
        )
        # Capped at 300,000 then 10% copay → 270,000
        assert result["eligible_amount"] == pytest.approx(270000.0, abs=1)

    def test_breakdown_is_populated(self, engine):
        result = engine.calculate_eligible_amount(
            member_id="MEM001",
            claim_type="CONSULTATION",
            claimed_amount=5000.0,
            is_network_hospital=True,
            items=[],
        )
        assert len(result["calculation_breakdown"]) >= 3


# ------------------------------------------------------------------
# Network hospital
# ------------------------------------------------------------------

class TestNetworkHospital:
    def test_known_network_hospital(self, engine):
        assert engine.is_network_hospital("Apollo Hospitals Bangalore") is True

    def test_partial_match_network(self, engine):
        assert engine.is_network_hospital("fortis") is True

    def test_non_network_hospital(self, engine):
        assert engine.is_network_hospital("Unknown Clinic") is False

    def test_case_insensitive(self, engine):
        assert engine.is_network_hospital("MANIPAL HOSPITAL") is True


# ------------------------------------------------------------------
# Pre-authorisation
# ------------------------------------------------------------------

class TestPreAuthorisation:
    def test_high_amount_requires_pre_auth(self, engine):
        result = engine.requires_pre_authorization("CONSULTATION", 150000.0, [])
        assert result["required"] is True

    def test_low_amount_no_pre_auth(self, engine):
        result = engine.requires_pre_authorization("CONSULTATION", 5000.0, [])
        assert result["required"] is False

    def test_bypass_surgery_requires_pre_auth(self, engine):
        result = engine.requires_pre_authorization("CONSULTATION", 5000.0, ["bypass surgery"])
        assert result["required"] is True


# ------------------------------------------------------------------
# Fraud thresholds
# ------------------------------------------------------------------

class TestFraudThresholds:
    def test_no_flags_for_normal_claim(self, engine):
        result = engine.check_fraud_thresholds(5000.0, 0, 1)
        assert result["auto_manual_review"] is False
        assert result["fraud_flags"] == []
        assert result["fraud_score"] == 0.0

    def test_high_value_claim_flagged(self, engine):
        result = engine.check_fraud_thresholds(250000.0, 0, 1)
        assert result["auto_manual_review"] is True
        assert any("High-value" in f for f in result["fraud_flags"])

    def test_same_day_frequency_flagged(self, engine):
        result = engine.check_fraud_thresholds(5000.0, 3, 1)
        assert result["auto_manual_review"] is True

    def test_monthly_frequency_flagged(self, engine):
        result = engine.check_fraud_thresholds(5000.0, 0, 5)
        assert result["auto_manual_review"] is True

    def test_fraud_score_is_fraction(self, engine):
        # All three flags → score = 1.0
        result = engine.check_fraud_thresholds(300000.0, 5, 10)
        assert result["fraud_score"] == pytest.approx(1.0)


# ------------------------------------------------------------------
# Document requirements
# ------------------------------------------------------------------

class TestDocumentRequirements:
    def test_pharmacy_requires_prescription_and_bill(self, engine):
        docs = engine.get_required_documents("PHARMACY")
        assert "PRESCRIPTION" in docs["required"]
        assert "PHARMACY_BILL" in docs["required"]

    def test_unknown_claim_type_returns_empty(self, engine):
        docs = engine.get_required_documents("UNKNOWN_TYPE")
        assert docs["required"] == []
        assert docs["optional"] == []
