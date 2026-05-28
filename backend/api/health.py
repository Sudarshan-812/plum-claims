"""Health check endpoint."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    """
    Return the health status of the API and whether the policy is loaded.
    """
    policy_engine = request.app.state.policy_engine
    policy_loaded = policy_engine is not None
    return {
        "status": "ok",
        "policy_loaded": policy_loaded,
        "policy_id": policy_engine.policy_id if policy_loaded else None,
        "timestamp": datetime.utcnow().isoformat(),
    }
