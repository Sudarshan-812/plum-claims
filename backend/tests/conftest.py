"""Shared fixtures — sample policy mirrors the real PLUM_GHI_2024 structure."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Sample policy matching the real PLUM_GHI_2024 structure exactly
# ---------------------------------------------------------------------------
SAMPLE_POLICY: dict = {
    "policy_id": "PLUM_GHI_2024",
    "policy_name": "Group Health Insurance — Standard Plan",
    "insurer": "ICICI Lombard General Insurance",
    "coverage": {
        "sum_insured_per_employee": 500000,
        "annual_opd_limit": 50000,
        "per_claim_limit": 5000,
    },
    "opd_categories": {
        "consultation": {
            "sub_limit": 2000,
            "copay_percent": 10,
            "network_discount_percent": 20,
            "covered": True,
        },
        "diagnostic": {
            "sub_limit": 10000,
            "copay_percent": 0,
            "network_discount_percent": 10,
            "pre_auth_threshold": 10000,
            "high_value_tests_requiring_pre_auth": ["MRI", "CT Scan", "PET Scan"],
            "covered": True,
        },
        "pharmacy": {
            "sub_limit": 15000,
            "copay_percent": 0,
            "covered": True,
        },
        "dental": {
            "sub_limit": 10000,
            "copay_percent": 0,
            "covered": True,
            "covered_procedures": ["Root Canal Treatment", "Tooth Extraction", "Dental Filling"],
            "excluded_procedures": [
                "Teeth Whitening",
                "Veneers",
                "Orthodontic Treatment (Braces)",
                "Bleaching",
            ],
        },
        "vision": {
            "sub_limit": 5000,
            "copay_percent": 0,
            "covered": True,
            "excluded_items": ["LASIK Surgery", "Refractive Surgery"],
        },
        "alternative_medicine": {
            "sub_limit": 8000,
            "copay_percent": 0,
            "covered": True,
        },
    },
    "waiting_periods": {
        "initial_waiting_period_days": 30,
        "pre_existing_conditions_days": 365,
        "specific_conditions": {
            "diabetes": 90,
            "hypertension": 90,
            "maternity": 270,
            "obesity_treatment": 365,
            "cataract": 365,
        },
    },
    "exclusions": {
        "conditions": [
            "Self-inflicted injuries",
            "Obesity and weight loss programs",
            "Bariatric surgery",
            "Cosmetic or aesthetic procedures",
            "Experimental treatments",
            "Health supplements and tonics",
        ],
        "dental_exclusions": [
            "Teeth whitening",
            "Orthodontic treatment",
            "Cosmetic dental procedures",
            "Veneers",
            "Bleaching",
        ],
        "vision_exclusions": [
            "LASIK",
            "Refractive surgery",
            "Cosmetic eye surgery",
        ],
    },
    "document_requirements": {
        "CONSULTATION": {
            "required": ["PRESCRIPTION", "HOSPITAL_BILL"],
            "optional": ["LAB_REPORT", "DIAGNOSTIC_REPORT"],
        },
        "DIAGNOSTIC": {
            "required": ["PRESCRIPTION", "LAB_REPORT", "HOSPITAL_BILL"],
            "optional": ["DISCHARGE_SUMMARY"],
        },
        "PHARMACY": {
            "required": ["PRESCRIPTION", "PHARMACY_BILL"],
            "optional": [],
        },
        "DENTAL": {
            "required": ["HOSPITAL_BILL"],
            "optional": ["PRESCRIPTION", "DENTAL_REPORT"],
        },
        "VISION": {
            "required": ["PRESCRIPTION", "HOSPITAL_BILL"],
            "optional": [],
        },
        "ALTERNATIVE_MEDICINE": {
            "required": ["PRESCRIPTION", "HOSPITAL_BILL"],
            "optional": [],
        },
    },
    "pre_authorization": {
        "required_for": [
            "MRI scan (amount > 10000)",
            "CT scan (amount > 10000)",
            "PET scan",
        ],
        "validity_days": 30,
    },
    "network_hospitals": [
        "Apollo Hospitals",
        "Fortis Healthcare",
        "Max Healthcare",
        "Manipal Hospitals",
        "Narayana Health",
    ],
    "fraud_thresholds": {
        "same_day_claims_limit": 2,
        "monthly_claims_limit": 6,
        "high_value_claim_threshold": 25000,
        "auto_manual_review_above": 25000,
    },
    "members": [
        {
            "member_id": "EMP001",
            "name": "Rajesh Kumar",
            "join_date": "2024-04-01",
            "relationship": "SELF",
        },
        {
            "member_id": "EMP002",
            "name": "Priya Singh",
            "join_date": "2024-04-01",
            "relationship": "SELF",
        },
        {
            "member_id": "EMP005",
            "name": "Vikram Joshi",
            "join_date": "2024-09-01",
            "relationship": "SELF",
        },
        {
            "member_id": "EMP010",
            "name": "Deepak Shah",
            "join_date": "2024-04-01",
            "relationship": "SELF",
        },
        # Recently joined member (still within initial 30-day period as of 2024-05-10)
        {
            "member_id": "EMP_NEW",
            "name": "New Employee",
            "join_date": "2024-05-01",
            "relationship": "SELF",
        },
    ],
}


@pytest.fixture(scope="session")
def policy_file(tmp_path_factory) -> str:
    """Write sample policy JSON to a temp file and return its path."""
    tmp_dir = tmp_path_factory.mktemp("policy")
    policy_path = tmp_dir / "policy_terms.json"
    policy_path.write_text(json.dumps(SAMPLE_POLICY), encoding="utf-8")
    return str(policy_path)


@pytest.fixture(scope="session")
def engine(policy_file):
    """Return a PolicyEngine loaded with the sample policy."""
    from services.policy_engine import PolicyEngine
    return PolicyEngine(policy_file)
