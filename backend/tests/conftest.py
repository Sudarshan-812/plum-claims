"""Shared fixtures for the test suite."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Make sure the backend package root is importable regardless of where
# pytest is invoked from.
sys.path.insert(0, str(Path(__file__).parent.parent))


SAMPLE_POLICY: dict = {
    "policy_id": "PLM-TEST-001",
    "insurer": "Test Insurance Co",
    "product_name": "Plum Health Plus",
    "members": [
        {
            "member_id": "MEM001",
            "name": "Alice Sharma",
            "date_of_joining": "2024-01-01",
            "sum_insured": 500000.0,
            "pre_existing_conditions": ["hypertension"],
        },
        {
            "member_id": "MEM002",
            "name": "Bob Patel",
            "date_of_joining": "2026-05-15",
            "sum_insured": 300000.0,
            "pre_existing_conditions": [],
        },
    ],
    "waiting_periods": {
        "initial_waiting_period_days": 30,
        "pre_existing_condition_days": 365,
        "specific_conditions": {
            "diabetes": 90,
            "maternity": 270,
        },
    },
    "coverage": {
        "sub_limits": {
            "DENTAL": 20000.0,
            "VISION": 10000.0,
            "PHARMACY": 50000.0,
            "ALTERNATIVE_MEDICINE": 15000.0,
        },
        "copay_percent": 10.0,
        "non_network_penalty_percent": 20.0,
    },
    "exclusions": {
        "procedures": ["lasik", "teeth whitening", "cosmetic surgery"],
        "diagnoses": ["self-inflicted injury"],
        "claim_type_exclusions": {
            "DENTAL": ["orthodontic retainer"],
        },
    },
    "document_requirements": {
        "PHARMACY": {
            "required": ["PRESCRIPTION", "PHARMACY_BILL"],
            "optional": ["LAB_REPORT"],
        },
        "CONSULTATION": {
            "required": ["HOSPITAL_BILL"],
            "optional": ["PRESCRIPTION", "LAB_REPORT", "DIAGNOSTIC_REPORT"],
        },
        "DIAGNOSTIC": {
            "required": ["DIAGNOSTIC_REPORT"],
            "optional": ["PRESCRIPTION"],
        },
        "DENTAL": {
            "required": ["DENTAL_REPORT", "HOSPITAL_BILL"],
            "optional": [],
        },
    },
    "pre_authorization": {
        "amount_threshold": 100000.0,
        "required_for_types": [],
        "required_procedures": ["bypass surgery", "organ transplant"],
    },
    "network_hospitals": [
        "Apollo Hospitals",
        "Fortis Healthcare",
        "Max Super Speciality",
        "Manipal Hospital",
    ],
    "fraud_detection": {
        "thresholds": {
            "high_value_claim": 200000.0,
            "max_same_day_claims": 3,
            "max_monthly_claims": 5,
        }
    },
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
