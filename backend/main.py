"""FastAPI application entry point for the Plum claims processing system."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.claims import router as claims_router
from api.health import router as health_router
from config import get_policy_path
from services.orchestrator import ClaimsOrchestrator
from services.policy_engine import PolicyEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Load shared resources on startup; clean up on shutdown."""
    policy_path = get_policy_path()
    logger.info("Loading policy from %s", policy_path)
    policy_engine = PolicyEngine(policy_path)
    app.state.policy_engine = policy_engine
    app.state.orchestrator = ClaimsOrchestrator(policy_engine)
    logger.info("Startup complete — policy_id=%s", policy_engine.policy_id)
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Plum Claims Processing API",
    version="0.1.0",
    description="AI-powered health insurance claims processing for Plum.",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Request logging middleware
# ------------------------------------------------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log method, path and response status for every request."""
    t0 = time.monotonic()
    response = await call_next(request)
    duration_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "%s %s → %d (%dms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ------------------------------------------------------------------
# Global exception handler
# ------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a clean JSON error for any unhandled exception."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again later.",
        },
    )


# ------------------------------------------------------------------
# Routers
# ------------------------------------------------------------------

app.include_router(health_router, tags=["health"])
app.include_router(claims_router, prefix="/api", tags=["claims"])
