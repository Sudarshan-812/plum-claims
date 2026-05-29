# Plum Claims Processing System

AI-powered multi-agent health insurance claims processing — built for the Plum AI Engineer assignment.

## Live Demo

| Service | URL |
|---------|-----|
| Frontend | https://plum-claims-six.vercel.app |
| Backend API | https://plum-claims-production-1d84.up.railway.app |
| Health check | https://plum-claims-production-1d84.up.railway.app/health |
| API docs | https://plum-claims-production-1d84.up.railway.app/docs |

## Test Results

```
97/97 unit + integration tests passing
12/12 test case scenarios passing
```

## What It Does

A member submits a health insurance claim with supporting documents. The system:

1. **Verifies** that the correct document types are present (prescription, hospital bill, etc.)
2. **Parses** document images with Gemini 2.5 Flash Vision — extracts patient name, diagnosis, line items, amounts
3. **Detects fraud** by checking claim frequency thresholds
4. **Evaluates policy** — waiting periods, exclusions, network discounts, co-pay, sub-limits
5. **Decides** APPROVED / PARTIAL / REJECTED / MANUAL\_REVIEW with a full explanation
6. **Records** a complete audit trail that can be replayed step-by-step

Every step runs in a LangGraph state machine. Every decision is traceable.

---

## Quick Start (Local)

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
cp .env.example .env
# add your GEMINI_API_KEY to .env
uvicorn main:app --reload
```

Backend runs at `http://localhost:8000`. API docs at `/docs`.

### Frontend

```bash
cd frontend
npm install
# .env.local already set to http://localhost:8000
npm run dev
```

Frontend runs at `http://localhost:3000`.

### Run Tests

```bash
cd backend
pytest tests/ -v
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.13, FastAPI, LangGraph |
| Document AI | Google Gemini 2.5 Flash Vision (`google-generativeai`) |
| Policy engine | Custom rules engine reading `policy_terms.json` |
| Frontend | Next.js 16, TypeScript, Tailwind CSS, shadcn/ui |
| Deployment | Railway (backend), Vercel (frontend) |

---

## Repository Structure

```
plum-claims/
├── backend/
│   ├── agents/           # 6 specialised agents
│   │   ├── verification.py
│   │   ├── parsing.py      ← Gemini Vision
│   │   ├── fraud.py
│   │   ├── policy_eval.py
│   │   ├── decision.py
│   │   └── audit.py
│   ├── services/
│   │   ├── orchestrator.py ← LangGraph state machine
│   │   └── policy_engine.py
│   ├── models/           # Pydantic models
│   ├── api/              # FastAPI routes
│   ├── data/
│   │   ├── policy_terms.json   ← PLUM_GHI_2024 policy
│   │   └── test_cases.json     ← 12 test scenarios
│   └── tests/
│       ├── test_decision.py
│       ├── test_policy_engine.py
│       ├── test_verification.py
│       └── test_integration.py ← 12 end-to-end scenarios
└── frontend/
    ├── app/
    │   ├── page.tsx              ← dashboard
    │   ├── claims/new/           ← submit claim
    │   └── claims/[id]/          ← detail + replay
    └── components/
        ├── claims/
        ├── trace/                ← audit timeline + replay modal
        └── forms/
```

---

## Policy Details (PLUM\_GHI\_2024)

The system enforces the real PLUM\_GHI\_2024 group policy for TechCorp Solutions:

- **Sum insured:** ₹5,00,000 per employee
- **Per-claim limit:** ₹5,000 (consultation only)
- **Co-pay:** 10% on consultation, 0% on other categories
- **Network discount:** 20% consultation, 10% diagnostic at network hospitals
- **Waiting periods:** 30 days initial, 90 days diabetes/hypertension, 270 days maternity
- **Dental exclusions:** Teeth whitening, veneers, orthodontic braces
- **Pre-auth required:** MRI/CT scan above ₹10,000

---

## Architecture

See **[docs/architecture.md](docs/architecture.md)** for:
- How each agent is designed and why
- LangGraph state machine walkthrough
- Failure handling strategy
- Design decisions and tradeoffs
- Scaling path to 10x

## Component Contracts

See **[docs/component_contracts.md](docs/component_contracts.md)** for:
- Input/output schemas for all 8 components
- Error conditions and fallbacks
- Worked examples for each method

## Evaluation Report

See **[docs/eval_report.md](docs/eval_report.md)** for:
- All 12 test cases with expected vs actual outcomes
- Calculation walkthroughs for financial test cases
- Known limitations and edge cases identified
