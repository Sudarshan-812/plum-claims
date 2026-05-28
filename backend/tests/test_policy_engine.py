"""Comprehensive tests for PolicyEngine against PLUM_GHI_2024 policy structure."""

from __future__ import annotations

import pytest


# ------------------------------------------------------------------
# Member lookup
# ------------------------------------------------------------------

class TestMemberLookup:
    def test_existing_member_returned(self, engine):
        member = engine.get_member("EMP001")
        assert member is not None
        assert member["name"] == "Rajesh Kumar"

    def test_missing_member_returns_none(self, engine):
        assert engine.get_member("NONEXISTENT") is None

    def test_is_member_active_true(self, engine):
        assert engine.is_member_active("EMP001") is True

    def test_is_member_active_false(self, engine):
        assert engine.is_member_active("GHOST") is False


# ------------------------------------------------------------------
# Waiting periods
# ------------------------------------------------------------------

class TestWaitingPeriods:
    def test_initial_waiting_period_not_cleared(self, engine):
        # EMP_NEW joined 2024-05-01; 10 days in → 10 < 30 → not cleared
        result = engine.check_waiting_period("EMP_NEW", "2024-05-11", [])
        assert result["passed"] is False
        assert result["days_remaining"] > 0

    def test_initial_waiting_period_cleared(self, engine):
        # EMP001 joined 2024-04-01; 2026-05-28 → way past 30 days
        result = engine.check_waiting_period("EMP001", "2026-05-28", [])
        assert result["passed"] is True
        assert result["days_remaining"] == 0

    def test_exactly_on_30_day_boundary(self, engine):
        # EMP001 joined 2024-04-01; exactly 30 days later = 2024-05-01 (day 30)
        result = engine.check_waiting_period("EMP001", "2024-05-01", [])
        assert result["passed"] is True

    def test_diabetes_waiting_period_not_cleared(self, engine):
        # EMP005 joined 2024-09-01; 2024-10-15 = 44 days < 90-day diabetes period
        result = engine.check_waiting_period("EMP005", "2024-10-15", ["Type 2 Diabetes Mellitus"])
        assert result["passed"] is False
        assert result["waiting_period_days"] == 90
        assert result["days_remaining"] > 0

    def test_diabetes_waiting_period_cleared(self, engine):
        # EMP005 joined 2024-09-01; 91 days later = 2024-11-30
        result = engine.check_waiting_period("EMP005", "2024-11-30", ["Type 2 Diabetes Mellitus"])
        assert result["passed"] is True

    def test_eligible_from_date_returned(self, engine):
        # EMP005 joined 2024-09-01, diabetes 90 days → eligible from 2024-11-30
        result = engine.check_waiting_period("EMP005", "2024-10-15", ["diabetes"])
        assert result["eligible_from"] == "2024-11-30"

    def test_hypertension_waiting_period(self, engine):
        # EMP001 joined 2024-04-01, hypertension = 90 days; claim on day 60
        result = engine.check_waiting_period("EMP001", "2024-05-31", ["hypertension"])
        assert result["passed"] is False
        assert result["waiting_period_days"] == 90

    def test_unknown_member_returns_fail(self, engine):
        result = engine.check_waiting_period("GHOST", "2026-01-01", [])
        assert result["passed"] is False
        assert "not found" in result["reason"].lower()

    def test_normal_diagnosis_uses_initial_period_only(self, engine):
        # EMP001 joined 2024-04-01; viral fever has no specific waiting period
        result = engine.check_waiting_period("EMP001", "2024-11-01", ["Viral Fever"])
        assert result["passed"] is True


# ------------------------------------------------------------------
# Exclusions
# ------------------------------------------------------------------

class TestExclusions:
    def test_lasik_is_excluded(self, engine):
        result = engine.check_exclusions("VISION", [], ["LASIK eye surgery"])
        assert result["excluded"] is True

    def test_teeth_whitening_is_excluded_dental(self, engine):
        result = engine.check_exclusions("DENTAL", [], ["Teeth Whitening procedure"])
        assert result["excluded"] is True

    def test_bariatric_is_excluded(self, engine):
        result = engine.check_exclusions("CONSULTATION", ["Morbid Obesity"], ["Bariatric Consultation"])
        assert result["excluded"] is True

    def test_obesity_programs_excluded(self, engine):
        result = engine.check_exclusions("CONSULTATION", ["Obesity"], ["Diet and Nutrition Program"])
        assert result["excluded"] is True

    def test_normal_viral_fever_not_excluded(self, engine):
        result = engine.check_exclusions("CONSULTATION", ["Viral Fever"], ["Paracetamol"])
        assert result["excluded"] is False
        assert result["exclusion_reason"] is None

    def test_root_canal_not_excluded(self, engine):
        result = engine.check_exclusions("DENTAL", [], ["Root Canal Treatment"])
        assert result["excluded"] is False

    def test_cosmetic_procedure_excluded(self, engine):
        result = engine.check_exclusions("CONSULTATION", ["Cosmetic procedure"], [])
        assert result["excluded"] is True


# ------------------------------------------------------------------
# Eligible amount — TC004 math: consultation 1500, non-network, 10% copay → 1350
# ------------------------------------------------------------------

class TestEligibleAmount:
    def test_tc004_consultation_copay_applied(self, engine):
        """TC004: 1500 consultation, non-network → 10% copay → 1350."""
        result = engine.calculate_eligible_amount(
            member_id="EMP001",
            claim_type="CONSULTATION",
            claimed_amount=1500.0,
            is_network_hospital=False,
            items=[],
        )
        assert result["per_claim_exceeded"] is False
        assert result["eligible_amount"] == pytest.approx(1350.0, abs=1)
        assert result["copay_amount"] == pytest.approx(150.0, abs=1)

    def test_tc010_network_discount_before_copay(self, engine):
        """TC010: 4500 consultation at Apollo → 20% discount first → 3600 → 10% copay → 3240."""
        result = engine.calculate_eligible_amount(
            member_id="EMP010",
            claim_type="CONSULTATION",
            claimed_amount=4500.0,
            is_network_hospital=True,
            items=[
                {"description": "Consultation Fee", "amount": 1500},
                {"description": "Medicines", "amount": 3000},
            ],
        )
        assert result["network_discount_applied"] is True
        assert result["eligible_amount"] == pytest.approx(3240.0, abs=1)
        assert result["copay_amount"] == pytest.approx(360.0, abs=1)

    def test_tc008_per_claim_limit_exceeded(self, engine):
        """TC008: 7500 consultation exceeds per_claim_limit 5000 → per_claim_exceeded flag."""
        result = engine.calculate_eligible_amount(
            member_id="EMP001",
            claim_type="CONSULTATION",
            claimed_amount=7500.0,
            is_network_hospital=False,
            items=[],
        )
        assert result["per_claim_exceeded"] is True
        assert result["eligible_amount"] == 0.0

    def test_tc006_dental_partial_exclusion(self, engine):
        """TC006: Root Canal 8000 (ok) + Teeth Whitening 4000 (excluded) → 8000 approved."""
        result = engine.calculate_eligible_amount(
            member_id="EMP002",
            claim_type="DENTAL",
            claimed_amount=12000.0,
            is_network_hospital=False,
            items=[
                {"description": "Root Canal Treatment", "amount": 8000},
                {"description": "Teeth Whitening", "amount": 4000},
            ],
        )
        assert result["eligible_amount"] == pytest.approx(8000.0, abs=1)
        assert len(result["rejected_items"]) == 1
        assert result["rejected_items"][0]["description"] == "Teeth Whitening"
        assert len(result["approved_items"]) == 1

    def test_dental_sub_limit_cap(self, engine):
        """Dental sub_limit 10000: claim 15000 → cap at 10000, copay 0 → 10000."""
        result = engine.calculate_eligible_amount(
            member_id="EMP001",
            claim_type="DENTAL",
            claimed_amount=15000.0,
            is_network_hospital=False,
            items=[],
        )
        assert result["sub_limit_applied"] is True
        assert result["eligible_amount"] == pytest.approx(10000.0, abs=1)

    def test_no_copay_for_dental(self, engine):
        """Dental copay_percent=0 → no copay deducted."""
        result = engine.calculate_eligible_amount(
            member_id="EMP001",
            claim_type="DENTAL",
            claimed_amount=5000.0,
            is_network_hospital=False,
            items=[],
        )
        assert result["copay_amount"] == 0.0
        assert result["eligible_amount"] == pytest.approx(5000.0, abs=1)

    def test_network_discount_not_applied_for_non_network(self, engine):
        result = engine.calculate_eligible_amount(
            member_id="EMP001",
            claim_type="CONSULTATION",
            claimed_amount=2000.0,
            is_network_hospital=False,
            items=[],
        )
        assert result["network_discount_applied"] is False

    def test_breakdown_has_network_and_copay_steps(self, engine):
        result = engine.calculate_eligible_amount(
            member_id="EMP001",
            claim_type="CONSULTATION",
            claimed_amount=4500.0,
            is_network_hospital=True,
            items=[],
        )
        bd = " ".join(result["calculation_breakdown"])
        assert "Network discount" in bd
        assert "Co-pay" in bd

    def test_per_claim_limit_not_applied_to_dental(self, engine):
        """per_claim_limit (5000) must NOT block a dental claim of 8000 (uses sub_limit 10000)."""
        result = engine.calculate_eligible_amount(
            member_id="EMP001",
            claim_type="DENTAL",
            claimed_amount=8000.0,
            is_network_hospital=False,
            items=[],
        )
        assert result["per_claim_exceeded"] is False
        assert result["eligible_amount"] == pytest.approx(8000.0, abs=1)


# ------------------------------------------------------------------
# Network hospital
# ------------------------------------------------------------------

class TestNetworkHospital:
    def test_apollo_is_network(self, engine):
        assert engine.is_network_hospital("Apollo Hospitals Bangalore") is True

    def test_fortis_partial_match(self, engine):
        assert engine.is_network_hospital("Fortis") is True

    def test_unknown_clinic_not_network(self, engine):
        assert engine.is_network_hospital("City Clinic, Bengaluru") is False

    def test_case_insensitive(self, engine):
        assert engine.is_network_hospital("NARAYANA HEALTH") is True

    def test_empty_hospital_name(self, engine):
        assert engine.is_network_hospital("") is False


# ------------------------------------------------------------------
# Pre-authorisation
# ------------------------------------------------------------------

class TestPreAuthorisation:
    def test_mri_above_threshold_requires_pre_auth(self, engine):
        """TC007: MRI Lumbar Spine at 15000 > 10000 threshold → pre-auth required."""
        result = engine.requires_pre_authorization(
            "DIAGNOSTIC", 15000.0, ["MRI Lumbar Spine"]
        )
        assert result["required"] is True
        assert "MRI" in result["reason"]

    def test_mri_below_threshold_no_pre_auth(self, engine):
        """MRI at 8000 < 10000 threshold → no pre-auth."""
        result = engine.requires_pre_authorization(
            "DIAGNOSTIC", 8000.0, ["MRI scan"]
        )
        assert result["required"] is False

    def test_ct_scan_above_threshold(self, engine):
        result = engine.requires_pre_authorization(
            "DIAGNOSTIC", 12000.0, ["CT Scan Chest"]
        )
        assert result["required"] is True

    def test_normal_blood_test_no_pre_auth(self, engine):
        result = engine.requires_pre_authorization(
            "DIAGNOSTIC", 3000.0, ["CBC Blood Test"]
        )
        assert result["required"] is False

    def test_consultation_low_amount_no_pre_auth(self, engine):
        result = engine.requires_pre_authorization("CONSULTATION", 1500.0, [])
        assert result["required"] is False


# ------------------------------------------------------------------
# Fraud thresholds (real policy: fraud_thresholds key)
# ------------------------------------------------------------------

class TestFraudThresholds:
    def test_normal_claim_no_flags(self, engine):
        result = engine.check_fraud_thresholds(3000.0, 0, 1)
        assert result["auto_manual_review"] is False
        assert result["fraud_flags"] == []
        assert result["fraud_score"] == 0.0

    def test_high_value_claim_flagged(self, engine):
        """Claims >= 25000 (high_value_claim_threshold) are flagged."""
        result = engine.check_fraud_thresholds(30000.0, 0, 1)
        assert result["auto_manual_review"] is True
        assert any("High-value" in f for f in result["fraud_flags"])

    def test_same_day_limit_is_2(self, engine):
        """same_day_claims_limit=2: count=2 means this is the 3rd claim (>=2) → flag."""
        result = engine.check_fraud_thresholds(3000.0, 2, 1)
        assert result["auto_manual_review"] is True

    def test_same_day_below_limit_no_flag(self, engine):
        result = engine.check_fraud_thresholds(3000.0, 1, 1)
        assert not any("same-day" in f.lower() for f in result["fraud_flags"])

    def test_monthly_limit_flagged(self, engine):
        """monthly_claims_limit=6: count=6 means this is the 7th → flag."""
        result = engine.check_fraud_thresholds(3000.0, 0, 6)
        assert result["auto_manual_review"] is True

    def test_fraud_score_is_fraction(self, engine):
        result = engine.check_fraud_thresholds(30000.0, 3, 7)
        assert result["fraud_score"] == pytest.approx(1.0)


# ------------------------------------------------------------------
# Document requirements (updated for real policy)
# ------------------------------------------------------------------

class TestDocumentRequirements:
    def test_consultation_requires_prescription_and_bill(self, engine):
        docs = engine.get_required_documents("CONSULTATION")
        assert "PRESCRIPTION" in docs["required"]
        assert "HOSPITAL_BILL" in docs["required"]

    def test_pharmacy_requires_prescription_and_pharmacy_bill(self, engine):
        docs = engine.get_required_documents("PHARMACY")
        assert "PRESCRIPTION" in docs["required"]
        assert "PHARMACY_BILL" in docs["required"]

    def test_diagnostic_requires_three_docs(self, engine):
        docs = engine.get_required_documents("DIAGNOSTIC")
        assert "PRESCRIPTION" in docs["required"]
        assert "LAB_REPORT" in docs["required"]
        assert "HOSPITAL_BILL" in docs["required"]

    def test_dental_requires_hospital_bill(self, engine):
        docs = engine.get_required_documents("DENTAL")
        assert "HOSPITAL_BILL" in docs["required"]

    def test_unknown_claim_type_returns_empty(self, engine):
        docs = engine.get_required_documents("UNKNOWN_TYPE")
        assert docs["required"] == []
        assert docs["optional"] == []
