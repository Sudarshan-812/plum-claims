# System Architecture — Plum Claims Processing

## Overview

This system automates the triage and decision-making pipeline for outpatient health insurance claims submitted by employees under the **PLUM_GHI_2024** group policy (ICICI Lombard). A claim that previously required a human reviewer reading documents, cross-checking policy terms, and applying financial rules is now processed end-to-end in under five seconds — and every reasoning step is recorded in a structured audit trail.

The core design philosophy is **agents as verifiable specialists**. Each step in the pipeline is owned by one agent with a narrow responsibility. No single piece of code decides "approved or rejected" by itself; the decision emerges from a chain of typed outputs that can be inspected, replayed, and explained.

---

## System Components

### 1. DocumentVerificationAgent (`agents/verification.py`)

**What it does:** Before any AI call is made, this agent checks that the correct document *types* have been uploaded for the claimed category. It does not read document contents — only confirms that a PRESCRIPTION, HOSPITAL_BILL, etc. is present.

**Why it exists separately:** Verification is fast (no I/O, no LLM) and can terminate the pipeline immediately with a precise error message. Mixing it into the parser would delay the feedback and hide the root cause.

**Key design decisions:**
- Document type is inferred from filename keywords (`_detect_doc_type`), not file contents, so it runs at zero cost before any parsing.
- Error messages are *actionable* — they name the specific document type that is missing and what it must contain.
- Returns a `VerificationResult` dataclass (not a dict) so callers have typed access to `status`, `missing_required`, `error_message`.

---

### 2. DocumentParsingAgent (`agents/parsing.py`)

**What it does:** Sends each uploaded document image (or PDF converted to image) to **Gemini 2.5 Flash** with a document-type-specific structured JSON prompt. Returns a `DocumentParsingResult` Pydantic model containing patient name, diagnosis, line items, amounts, and a confidence score.

**Why it exists separately:** Parsing is the only step that touches an external LLM API and is therefore the slowest and most failure-prone step. Isolating it means its failures can be caught, logged, and degraded gracefully without affecting the policy or fraud evaluation.

**Key design decisions:**
- A separate prompt per document type (PRESCRIPTION, HOSPITAL_BILL, LAB_REPORT, PHARMACY_BILL) extracts the fields that actually matter for that document.
- PDFs are converted to a PIL image (first page, 200 Dpi) before sending to Gemini. This avoids multipart upload complexity and keeps the API call uniform.
- `parse_mock()` is a first-class method — not a test fixture — so integration tests can drive the full pipeline with deterministic data without incurring Gemini API calls.
- `asyncio.to_thread()` wraps the synchronous `generate_content()` call so the FastAPI event loop is never blocked.
- Confidence is computed from critical-field coverage, not from the model's own confidence token probabilities (which are unavailable in the generative endpoint).

---

### 3. FraudDetectionAgent (`agents/fraud.py`)

**What it does:** Checks three fraud thresholds from the policy: high-value claim (≥ ₹25,000), same-day claim frequency (≥ 2 same-day claims already filed), and monthly claim frequency (≥ 6 per month). Returns a fraud score and a list of triggered flags.

**Why it exists separately:** Fraud detection uses a completely different data source (claim history counts, not document contents) and a completely different logic (threshold comparison). Keeping it separate also makes it easy to upgrade later to an ML model without touching the rest of the pipeline.

**Key design decisions:**
- All thresholds are read from `policy_terms.json` — none are hardcoded. A policy update in JSON immediately changes system behaviour.
- The agent never *rejects* a claim on its own. It sets `auto_manual_review=True` and returns flagged signals. The `DecisionAgent` makes the actual routing decision.
- A `fraud_score` in [0.0, 1.0] is computed as `len(flags) / 3`. This is deliberately simple and transparent — no black-box scoring.

---

### 4. PolicyEvaluationAgent (`agents/policy_eval.py`)

**What it does:** Applies all policy financial rules in the correct order: member lookup → waiting period → item-level exclusions → sub-limit cap → network discount → co-pay. Returns an `eligible_amount` dict with a full calculation breakdown and a list of approved/rejected line items.

**Why it exists separately:** Policy evaluation is pure business logic — no I/O, no external calls. It reads from a PolicyEngine instance loaded once at startup. Separating it makes the financial rules trivially unit-testable and replaceable if policy terms change.

**Key design decisions:**
- Network discount is applied **before** co-pay (TC010 validates this). The order matters: 20% network discount on ₹4,500 → ₹3,600, then 10% co-pay → ₹3,240. Reversing the order gives ₹3,150 — a ₹90 error.
- Per-claim limit applies only to CONSULTATION claims. Other categories use their own `sub_limit`.
- Item-level exclusion filtering (for DENTAL, VISION) compares each line item description against the excluded procedures list using a distinctive-keyword match — not substring. The word "treatment" alone cannot trigger an exclusion match (`_GENERIC_WORDS` set prevents false positives like "Root Canal Treatment" matching "Orthodontic Treatment").

---

### 5. DecisionAgent (`agents/decision.py`)

**What it does:** Synthesises all prior agent outputs into a single `ClaimDecision` (APPROVED / PARTIAL / REJECTED / MANUAL_REVIEW) and a human-readable reason string.

**Why it exists separately:** The final decision is a pure function of the upstream results. No I/O, no side effects. This makes it trivially unit-testable against all 12 test cases in isolation.

**Key design decisions:**
- Fixed priority order prevents ambiguous outcomes: verification fail → fraud → all items excluded → waiting period → pre-auth → per-claim limit → partial → approved. Any upstream failure at a higher priority masks lower-priority checks (e.g., TC012 gets EXCLUDED_CONDITION, not PER_CLAIM_EXCEEDED, even though both apply).
- Confidence penalty: each failed pipeline component deducts 0.15 from the decision confidence (TC011 demonstrates this — confidence drops from 0.90 to 0.75).
- The `decision_reason` string is written for a claims adjuster to read, not a developer. It contains amounts, dates, and actionable next steps.

---

### 6. AuditAgent (`agents/audit.py`)

**What it does:** Records every pipeline step as an `AgentStep` (input, output, duration, status, error) and assembles the completed `ClaimTrace`.

**Why it exists separately:** Auditability is a regulatory requirement for insurance. Every decision must be explainable and reproducible. The AuditAgent ensures this happens even if other agents fail.

**Key design decisions:**
- Uses a context manager (`with audit.step(...)`) so duration is always measured correctly even when exceptions occur.
- `full_input` and `full_output` store raw dicts, not formatted strings, so the replay UI can render them as structured JSON.
- The trace is stored independently of the claim record, linked by `trace_id`, so the claim can be reprocessed without losing the original audit trail.

---

## Agent Orchestration

### Why LangGraph

The pipeline has a conditional branch: if document verification fails, the remaining four agents (parsing, fraud, policy, decision) should not run. A simple sequential function call cannot express this cleanly — you'd need nested `if` statements that tangle control flow with business logic.

LangGraph models the pipeline as a directed state machine where:
- **State** (`ClaimState`) is a typed dict accumulating results as agents run.
- **Nodes** are async functions (one per agent) that receive the current state and return partial updates.
- **Edges** are explicit transitions between nodes.
- **Conditional edges** inspect state to choose the next node.

The graph looks like this:

```
verify_documents
      │
      ├── [STOPPED_EARLY] ──────────────────────────────┐
      │                                                  │
parse_documents → detect_fraud → evaluate_policy → make_decision
                                                         │
                                                   save_audit → END
```

### How the State Machine Works

`ClaimState` uses two LangGraph reducer primitives:
- `trace_steps: Annotated[list, operator.add]` — each node appends one step; LangGraph merges by concatenation.
- `errors: Annotated[list, operator.add]` — component failures accumulate here; the DecisionAgent reads the count to apply a confidence penalty.

All other fields use last-write-wins (default), so `parsing_results`, `fraud_result`, and `policy_result` are simply overwritten by their respective nodes.

### Conditional Early Stopping

After `verify_documents`, the edge function `should_continue_after_verification` reads `state["pipeline_status"]`:

```python
def should_continue_after_verification(state) -> str:
    if state["pipeline_status"] == "STOPPED_EARLY":
        return "save_audit"   # jump directly to audit, skip all other agents
    return "parse_documents"  # normal path
```

This means TC001 (wrong documents) generates a trace with exactly 2 steps — `DocumentVerificationAgent` and `AuditAgent` — not 6. The trace clearly shows where and why the pipeline stopped.

---

## Data Flow

**Step-by-step for a valid claim submission:**

1. **HTTP POST /api/claims** — FastAPI receives a multipart form with JSON claim metadata and uploaded files.
2. **Fast sync verification** — `DocumentVerificationAgent.verify()` runs synchronously in the request handler. If it fails, a 400 response is returned immediately with a specific error message before a claim record is even created.
3. **Claim record created** — A `ClaimRecord` is written to the in-memory store with `status=PENDING`. The claim ID is returned to the client.
4. **Background task queued** — `ClaimsOrchestrator.process_async()` is scheduled as a FastAPI background task.
5. **LangGraph invoked** — `graph.ainvoke(initial_state)` runs the six-node state machine asynchronously.
6. **Document parsing** — Each uploaded file is converted to a PIL image and sent to Gemini 2.5 Flash with a structured JSON prompt. Responses are parsed and mapped to `DocumentParsingResult` objects.
7. **Fraud check** — Thresholds are evaluated against claim history counts passed in from the API layer.
8. **Policy evaluation** — Line items, diagnosis, treatment items extracted from parsed documents are passed to the PolicyEngine for eligibility calculation.
9. **Decision** — All upstream results are synthesised into a final `ClaimDecision`.
10. **Audit** — The completed `ClaimTrace` is written to the traces store and linked to the claim record.
11. **Claim record updated** — `status`, `decision`, `approved_amount`, `confidence_score`, `trace_id` are written back.
12. **Frontend polls GET /api/claims/{id}** — The dashboard auto-refreshes every 3 seconds until the claim exits PROCESSING status.

---

## Failure Handling Strategy

| Failure Mode | What Happens | Why |
|---|---|---|
| Document verification fails | Pipeline stops immediately; 400 returned to client with specific message | Fast, cheap. No point running LLM if docs are wrong. |
| Gemini API timeout or error | `parse()` returns `parsing_status="FAILED"`, node catches exception, adds to `errors[]`, continues with empty parsed data | Never crash the pipeline over a transient API failure. |
| Invalid member ID | `check_waiting_period()` returns `passed=False` with "Member not found" reason → REJECTED | Fail closed: unknown member cannot be approved. |
| All documents unreadable | `parse_documents` node detects all `parsing_status="FAILED"` → sets `parsing_quality_issue` → `make_decision` routes to MANUAL_REVIEW with "re-upload" message | Don't reject outright; give the member a chance to resubmit. |
| Patient name mismatch across docs | `parse_documents` detects multiple distinct patient names → MANUAL_REVIEW with specific names | Possible fraud or document mix-up; human review required. |
| PolicyEvaluationAgent throws | Node catches, uses safe fallback policy result (`waiting_period.passed=True`, `eligible=claimed_amount`), continues | Test TC011. Confidence is reduced by 0.15 per failure; a note is appended to `decision_reason`. |
| DecisionAgent throws | Pipeline returns `status=ERROR` on the claim record | This is the last resort; should never happen in practice given all inputs are typed. |

---

## Design Decisions & Tradeoffs

### Why Gemini Vision over other OCR approaches

**Traditional OCR (Tesseract, AWS Textract):** Produces raw text from images. Still requires a second LLM pass to extract structured fields. Two API calls, double the latency, two failure points.

**Gemini Vision (chosen):** Sends the image and a structured JSON schema in a single prompt. Returns structured JSON directly. One API call. The model handles handwritten text, stamps, rotated text, and mixed scripts (English + Devanagari) without pre-processing.

**Tradeoff:** Gemini Vision adds 3–8 seconds per document at inference time and costs API credits. For a 75,000 claims/year system (~200/day), this is acceptable.

### Why FastAPI over Django/Flask

FastAPI is async-native. `asyncio.to_thread()` (wrapping the synchronous Gemini SDK call) and LangGraph's `ainvoke()` both require an async event loop. Django's sync-by-default model would require `sync_to_async` wrappers and ASGI middleware overhead. FastAPI also gives automatic OpenAPI docs and Pydantic validation at zero extra cost.

### Why In-Memory Store over a Database

This is a three-day build. The time saved by not provisioning, migrating, and managing a Postgres instance was spent building the actual claims logic and evaluation report. The in-memory store is explicitly documented as a known limitation and the migration path is straightforward (see Scaling section).

### What Was Cut

- **Supabase persistence** — was planned for Day 2, cut in favour of completing the LangGraph orchestrator properly. Rows-level security and auth would add significant scope for minimal Day 3 demo value.
- **Redis queue** — background task via FastAPI is sufficient for single-instance demo. Redis would be needed only when horizontal scaling makes shared state necessary.
- **Real document scanning** — the 12 test cases use mock parsed data because we don't have real scanned Indian medical documents to test against. The `parse()` method with Gemini is production-ready; `parse_mock()` is used only in automated tests.
- **Member authentication** — the demo accepts any member_id string. A real deployment would validate against an HR system.

---

## Limitations

| Limitation | Impact | Mitigation Path |
|---|---|---|
| In-memory store resets on restart | All claims lost on Railway redeploy | Replace with PostgreSQL (see Scaling) |
| Gemini parsing latency (3–8s per doc) | Claim processing takes 10–30s total | Parallel document parsing; streaming progress to frontend |
| No authentication on API endpoints | Any client can submit or read claims | Add JWT / API key middleware |
| `https://*.vercel.app` in CORS | Starlette doesn't do wildcard subdomain matching; the explicit `plum-claims-six.vercel.app` entry is the one that actually works | Add all deployment domains explicitly |
| Mock parsing in tests | Test suite validates pipeline logic, not OCR accuracy | Build a golden-set of real scanned docs for OCR regression tests |
| Single Railway instance | All state is in memory; no horizontal scaling | See Scaling section |

---

## Scaling to 10x (75,000 → 750,000 Claims/Year)

75,000 claims/year = ~200/day = ~8/hour, which fits comfortably in one instance. At 750,000/year (~2,000/day, ~85/hour) the bottlenecks are:

**1. Storage:** Replace `claims_store` / `traces_store` dicts with **PostgreSQL** on Railway (or Supabase). Migrate `ClaimRecord` and `ClaimTrace` Pydantic models to SQLAlchemy or Tortoise ORM models. Schema migration cost: ~1 day.

**2. Processing queue:** FastAPI background tasks run in the same process. At high load, they compete with request handlers for CPU. Replace with **Celery + Redis** (or Railway's built-in background workers). The LangGraph pipeline becomes a Celery task; the API only enqueues and polls.

**3. Parallel document parsing:** Currently parsed sequentially. `asyncio.gather()` already wraps the per-document parse calls in `_parse_all_documents()`. The only change needed is to ensure the Gemini SDK's rate limiter is respected (exponential backoff on 429s).

**4. Document storage:** Replace in-memory file bytes with **S3 / Cloudflare R2**. Upload files to S3 at submission time; store only the S3 key on the claim record. Parsing nodes fetch the bytes on demand.

**5. Horizontal scaling:** Railway supports multiple replicas behind a load balancer. Once state is in Postgres + Redis, all replicas share state and scaling is just a slider.

**6. Caching:** PolicyEngine already loads from JSON at startup. At 10x scale, add a `@lru_cache` on expensive `check_waiting_period` calls (member join date doesn't change mid-request).
