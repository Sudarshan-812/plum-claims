"""Pydantic models for policy-related data."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class MemberRecord(BaseModel):
    """A single insured member from the policy file."""

    member_id: str
    name: str
    date_of_joining: str  # YYYY-MM-DD
    sum_insured: float
    pre_existing_conditions: list[str] = []


class PolicySummary(BaseModel):
    """High-level policy metadata returned by health endpoints."""

    policy_id: str
    insurer: str
    product_name: str
    member_count: int
