# Component Contracts

Each component's precise input schema, output schema, error conditions, and a worked example.

---

## PolicyEngine (`services/policy_engine.py`)

**Role:** Single source of truth for all policy rules. Loaded once at startup from `data/policy_terms.json`. All agents call into PolicyEngine — none read the JSON directly.

### `get_required_documents(claim_type: str) → dict`

```
Input:
  claim_type: str   e.g. "CONSULTATION"

Output:
  {
    "required": list[str],   e.g. ["PRESCRIPTION", "HOSPITAL_BILL"]
    "optional": list[str]    e.g. ["LAB_REPORT"]
  }

Errors: none (returns empty lists for unknown claim types)
```

### `check_waiting_period(member_id, claim_date, diagnosis) → dict`

```
Input:
  member_id:   str         e.g. "EMP005"
  claim_date:  str         "YYYY-MM-DD"
  diagnosis:   list[str]  e.g. ["Type 2 Diabetes Mellitus"]

Output:
  {
    "passed":               bool,
    "waiting_period_days":  int,
    "days_since_joining":   int,
    "days_remaining":       int,    # 0 if passed
    "eligible_from":        str,    # "YYYY-MM-DD"
    "reason":               str
  }

Errors: none (unknown member returns passed=False with "Member not found")

Example:
  Input:  member_id="EMP005", claim_date="2024-10-15", diagnosis=["Type 2 Diabetes Mellitus"]
  Output: {
    "passed": false,
    "waiting_period_days": 90,
    "days_since_joining": 44,
    "days_remaining": 46,
    "eligible_from": "2024-11-30",
    "reason": "Condition 'diabetes' has a 90-day waiting period"
  }
```

### `check_exclusions(claim_type, diagnosis, treatment_items) → dict`

```
Input:
  claim_type:      str         e.g. "DENTAL"
  diagnosis:       list[str]
  treatment_items: list[str]   e.g. ["Teeth Whitening", "Root Canal Treatment"]

Output:
  {
    "excluded":          bool,
    "exclusion_reason":  str | null,
    "excluded_items":    list[str]
  }

Errors: none
```

### `calculate_eligible_amount(member_id, claim_type, claimed_amount, is_network_hospital, items) → dict`

```
Input:
  member_id:          str
  claim_type:         str
  claimed_amount:     float
  is_network_hospital: bool
  items:              list[{"description": str, "amount": float}]

Output:
  {
    "eligible_amount":          float,
    "copay_amount":             float,
    "sub_limit":                float,
    "sub_limit_applied":        bool,
    "per_claim_exceeded":       bool,
    "network_discount_applied": bool,
    "approved_items":           list[{"description": str, "amount": float}],
    "rejected_items":           list[{"description": str, "amount": float, "reason": str}],
    "calculation_breakdown":    list[str]
  }

Errors: none (unknown member treated as zero prior claims)

Financial rule order (must be preserved):
  1. Per-claim limit check (CONSULTATION only, rejects immediately if exceeded)
  2. Item-level exclusion filtering (DENTAL/VISION only)
  3. Sub-limit cap (non-CONSULTATION categories)
  4. Network discount (applied FIRST, before co-pay)
  5. Co-pay deduction (applied AFTER discount)

Example (TC010 — Apollo Hospitals, network):
  Input:  claim_type="CONSULTATION", claimed_amount=4500, is_network=true,
          items=[{Consultation Fee: 1500}, {Medicines: 3000}]
  Output: {
    "eligible_amount": 3240.0,
    "copay_amount": 360.0,
    "network_discount_applied": true,
    "calculation_breakdown": [
      "Claimed amount: ₹4,500.00",
      "Network discount 20%: -₹900.00 → ₹3,600.00",
      "Co-pay 10%: -₹360.00 → ₹3,240.00",
      "Final eligible amount: ₹3,240.00"
    ]
  }
```

### `requires_pre_authorization(claim_type, claimed_amount, treatment_items) → dict`

```
Input:
  claim_type:      str
  claimed_amount:  float
  treatment_items: list[str]   e.g. ["MRI Lumbar Spine"]

Output:
  {
    "required": bool,
    "reason":   str
  }

Errors: none

Special rule: For DIAGNOSTIC claims, pre-auth is triggered only when:
  (a) the test name matches high_value_tests_requiring_pre_auth (MRI, CT Scan, PET Scan)
  AND (b) claimed_amount > pre_auth_threshold (10000)
  The general pre_authorization.required_for list is NOT applied to DIAGNOSTIC.
```

### `check_fraud_thresholds(claimed_amount, same_day_claim_count, monthly_claim_count) → dict`

```
Input:
  claimed_amount:       float
  same_day_claim_count: int    # claims already filed today (not including this one)
  monthly_claim_count:  int    # claims filed this month so far

Output:
  {
    "auto_manual_review": bool,
    "fraud_flags":        list[str],
    "fraud_score":        float      # len(flags) / 3, range [0.0, 1.0]
  }

Errors: none
```

---

## DocumentVerificationAgent (`agents/verification.py`)

**Role:** Confirm correct document types are present. Does NOT read document contents.

### `verify(claim_type, uploaded_documents) → VerificationResult`

```
Input:
  claim_type:          str
  uploaded_documents:  list[UploadedDocument]
    UploadedDocument.document_type: DocumentType enum

Output (VerificationResult dataclass):
  status:               "PASS" | "FAIL"
  missing_required:     list[str]    # DocumentType values that are absent
  unexpected_documents: list[str]    # filenames not in required or optional list
  error_message:        str | None   # human-readable, actionable if FAIL
  checked_at:           datetime

Errors: none (always returns a result)

Example (TC001):
  Input:  claim_type="CONSULTATION",
          docs=[{type: PRESCRIPTION}, {type: PRESCRIPTION}]
  Output: {
    "status": "FAIL",
    "missing_required": ["HOSPITAL_BILL"],
    "error_message": "Your CONSULTATION claim requires Doctor's Prescription and
      Hospital Bill / Invoice. We received: Doctor's Prescription.
      Please upload:
        (1) Hospital Bill / Invoice — itemised bill on hospital letterhead..."
  }
```

---

## DocumentParsingAgent (`agents/parsing.py`)

**Role:** Extract structured data from medical document images using Gemini 2.5 Flash.

### `parse(document_bytes, document_type, filename) → DocumentParsingResult`

```
Input:
  document_bytes: bytes         # raw file bytes (JPEG, PNG, WEBP, or PDF)
  document_type:  DocumentType  # drives which JSON prompt to use
  filename:       str           # used to detect PDF and media type

Output (DocumentParsingResult Pydantic model):
  document_type:         DocumentType
  filename:              str
  patient_name:          str | None
  patient_age:           int | None
  patient_gender:        "M" | "F" | None
  doctor_name:           str | None
  doctor_registration:   str | None
  doctor_specialization: str | None
  hospital_name:         str | None
  hospital_address:      str | None
  diagnosis:             list[str]
  treatment_items:       list[str]
  medicines:             list[str]
  total_amount:          float | None
  line_items:            list[ExtractedLineItem]
  treatment_date:        str | None   # "YYYY-MM-DD"
  bill_date:             str | None   # "YYYY-MM-DD"
  overall_confidence:    float        # 0.0 – 1.0
  low_confidence_fields: list[str]
  parsing_notes:         list[str]
  extraction_warnings:   list[str]
  parsing_status:        "SUCCESS" | "PARTIAL" | "FAILED"
  error_message:         str | None

Errors raised: none (all exceptions caught; returns parsing_status="FAILED")

Failure modes:
  - Gemini API error         → parsing_status="FAILED", error_message=exception text
  - JSON not in response     → parsing_status="PARTIAL", overall_confidence=0.3
  - PDF conversion fails     → uses blank white image stub, continues
  - client is None           → delegates to parse_mock()
```

### `parse_mock(document_type, member_name, amount, diagnosis, ...) → DocumentParsingResult`

```
Input: (all optional with defaults)
  document_type:   DocumentType
  member_name:     str = "Rajesh Kumar"
  amount:          float = 1500.0
  diagnosis:       list[str] | None
  hospital_name:   str | None
  doctor_name:     str | None
  line_items:      list[dict] | None   # [{"description": str, "amount": float}]
  patient_name:    str | None
  treatment_items: list[str] | None
  parsing_status:  str = "SUCCESS"     # can be forced to "FAILED" for TC002
  error_message:   str | None
  confidence:      float | None

Output: DocumentParsingResult with realistic Indian medical data
Errors: none
```

---

## FraudDetectionAgent (`agents/fraud.py`)

**Role:** Thin wrapper around `PolicyEngine.check_fraud_thresholds()`. Exists to isolate the fraud logic call from the orchestrator.

### `check(claimed_amount, same_day_count, monthly_count) → dict`

```
Input:
  claimed_amount:  float
  same_day_count:  int = 0
  monthly_count:   int = 0

Output:
  {
    "auto_manual_review": bool,
    "fraud_flags":        list[str],
    "fraud_score":        float
  }

Errors raised: can raise if PolicyEngine is misconfigured (rare)

Example (TC009 — 4th same-day claim):
  Input:  claimed_amount=4800, same_day_count=3
  Output: {
    "auto_manual_review": true,
    "fraud_flags": ["Unusual same-day claim frequency: 4 claims today (limit 2)"],
    "fraud_score": 0.3333
  }
```

---

## PolicyEvaluationAgent (`agents/policy_eval.py`)

**Role:** Orchestrates all policy checks for a single claim and returns a combined evaluation result.

### `evaluate(member_id, claim_type, claimed_amount, claim_date, diagnosis, treatment_items, hospital_name, line_items) → dict`

```
Input:
  member_id:       str
  claim_type:      str
  claimed_amount:  float
  claim_date:      str             "YYYY-MM-DD"
  diagnosis:       list[str]       aggregated from all parsed documents
  treatment_items: list[str]       aggregated from all parsed documents
  hospital_name:   str             from submission or parsed documents
  line_items:      list[dict] | None

Output:
  {
    "waiting_period": {
      "passed": bool,
      "waiting_period_days": int,
      "days_since_joining": int,
      "days_remaining": int,
      "eligible_from": str,
      "reason": str
    },
    "exclusions": {
      "excluded": bool,
      "exclusion_reason": str | null,
      "excluded_items": list[str]
    },
    "eligible_amount": {
      "eligible_amount": float,
      "copay_amount": float,
      "sub_limit": float,
      "sub_limit_applied": bool,
      "per_claim_exceeded": bool,
      "network_discount_applied": bool,
      "approved_items": list[dict],
      "rejected_items": list[dict],
      "calculation_breakdown": list[str]
    },
    "pre_auth": {
      "required": bool,
      "reason": str
    },
    "is_network_hospital": bool,
    "passed": bool    # True when waiting_period.passed AND NOT pre_auth.required AND NOT per_claim_exceeded
  }

Errors raised: can raise if member_id not found and edge case in PolicyEngine
Graceful fallback: LangGraph evaluate_policy node catches all exceptions and substitutes a safe default result
```

---

## DecisionAgent (`agents/decision.py`)

**Role:** Final arbiter. Synthesises all upstream results into a single typed decision.

### `decide(verification_passed, policy_evaluation, fraud_result) → dict`

```
Input:
  verification_passed:  bool
  policy_evaluation:    dict   (output of PolicyEvaluationAgent.evaluate())
  fraud_result:         dict   (output of FraudDetectionAgent.check())

Output:
  {
    "decision":          ClaimDecision enum  (APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW)
    "approved_amount":   float
    "approved_items":    list[dict]
    "rejected_items":    list[dict]
    "rejection_reasons": list[str]   e.g. ["WAITING_PERIOD"]
    "decision_reason":   str         human-readable explanation
    "confidence_score":  float       0.0 – 1.0
  }

Errors raised: none (all inputs are dicts; gracefully handles missing keys)

Priority order (first match wins):
  1. verification_passed=False           → REJECTED
  2. fraud_result.auto_manual_review     → MANUAL_REVIEW
  3. exclusions.excluded AND eligible=0  → REJECTED (EXCLUDED_CONDITION)
  4. waiting_period.passed=False         → REJECTED (WAITING_PERIOD)
  5. pre_auth.required=True             → REJECTED (PRE_AUTH_MISSING)
  6. eligible_amount.per_claim_exceeded  → REJECTED (PER_CLAIM_EXCEEDED)
  7. rejected_items present OR sub_limit → PARTIAL
  8. default                             → APPROVED

Confidence scores by outcome:
  APPROVED:      0.90
  PARTIAL:       0.88
  REJECTED:      0.92 – 0.97 (varies by reason)
  MANUAL_REVIEW: 1 - fraud_score
  Per failed component: -0.15 deducted after base confidence
```

---

## ClaimsOrchestrator (`services/orchestrator.py`)

**Role:** Assembles the LangGraph state machine and exposes `process_async()` as the single entry point for claim processing.

### `process_async(claim, documents, document_bytes, hospital_name, same_day_count, monthly_count, prebuilt_parsing_results) → tuple[ClaimRecord, ClaimTrace]`

```
Input:
  claim:                    ClaimRecord   (status=PENDING)
  documents:                list[UploadedDocument]
  document_bytes:           list[bytes] = []      # parallel with documents
  hospital_name:            str = ""
  same_day_count:           int = 0
  monthly_count:            int = 0
  prebuilt_parsing_results: list[DocumentParsingResult] | None = None
                            # if set, skips live Gemini parsing (used by tests)

Output:
  (ClaimRecord, ClaimTrace)
  ClaimRecord fields updated:  status, decision, approved_amount,
                               decision_reason, confidence_score, trace_id
  ClaimTrace fields:           trace_id, claim_id, started_at, completed_at,
                               steps (list[AgentStep]), final_decision, final_confidence

Errors raised:
  - All individual node failures are caught internally
  - Only unrecoverable state corruption would propagate (should not happen)

LangGraph ClaimState fields:
  claim_id, member_id, claim_type, claimed_amount, treatment_date
  uploaded_documents, document_bytes, hospital_name
  same_day_count, monthly_count
  prebuilt_parsing_results   (optional, for tests)
  verification_result        (set by verify_documents node)
  parsing_results            (set by parse_documents node)
  parsing_quality_issue      (set by parse_documents if unreadable/name mismatch)
  fraud_result               (set by detect_fraud node)
  policy_result              (set by evaluate_policy node)
  decision_result            (set by make_decision node)
  trace_steps                (Annotated[list, operator.add] — appended by every node)
  errors                     (Annotated[list, operator.add] — component failures)
  trace_id                   str
  pipeline_status            "RUNNING" | "STOPPED_EARLY" | "COMPLETED"
  stop_reason                str | None
```

### `process(claim, documents, ...) → tuple[ClaimRecord, ClaimTrace]`

```
Synchronous wrapper around process_async(). Uses asyncio.new_event_loop().
Safe to call from non-async contexts. Used by CLI scripts and tests that
don't run inside an event loop.
```

---

## REST API (`api/claims.py`)

### `POST /api/claims`

```
Content-Type: multipart/form-data

Form fields:
  claim_data: str   JSON string:
    {
      "member_id":       str        e.g. "EMP001"
      "claim_type":      str        e.g. "CONSULTATION"
      "claimed_amount":  float      > 0
      "treatment_date":  str        "YYYY-MM-DD"
      "documents":       []         always empty — files come via multipart
      "notes":           str?
    }
  files: File[]    one or more uploaded documents

Response 201:
  { "claim_id": str, "status": "PENDING", "message": str }

Response 400 (verification fail):
  {
    "error": "document_verification_failed",
    "message": str,           # actionable, names the missing document type
    "missing_required": list[str]
  }

Response 422: malformed claim_data JSON
```

### `GET /api/claims`

```
Response 200: list[ClaimRecord]   (last 50, newest first)
```

### `GET /api/claims/{claim_id}`

```
Response 200: { "claim": ClaimRecord, "trace": ClaimTrace | null }
Response 404: claim not found
```

### `GET /api/claims/{claim_id}/trace`

```
Response 200: ClaimTrace   (full audit trail with all AgentStep records)
Response 404: claim or trace not found
```

### `GET /api/claims/{claim_id}/replay`

```
Response 200:
  {
    "claim_id":        str,
    "final_decision":  str | null,
    "final_confidence": float | null,
    "total_steps":     int,
    "steps": [
      {
        "step_number":   int,
        "agent_name":    str,
        "title":         str,    # human-readable
        "description":   str,
        "input_summary": str,
        "output_summary": str,
        "status":        str,
        "duration_ms":   int,
        "full_data":     { "input": dict, "output": dict, "error": str | null }
      }
    ]
  }
```

### `POST /api/claims/{claim_id}/reprocess`

```
Response 200: { "claim_id": str, "status": "PROCESSING", "message": str }
Response 404: claim not found
```
