# InterVue AI — Adaptive AI Technical Interview Agent

> **Tagline:** Adaptive AI Technical Interview Agent

InterVue AI conducts personalized, conversational technical interviews based on a
candidate's learning journey. It remembers previous conversations, adapts questions
to candidate answers, asks intelligent follow-ups, and generates structured feedback.

This repository is a **production-ready project foundation** (architecture + skeleton).
Business logic, prompt engineering, and Gemini API integration are intentionally
**not implemented yet**.

---

## 1. Architecture Overview

Clean architecture with strict separation of responsibilities across three layers.

### High-level flow

```
Candidate          FastAPI API              Services Layer              Data Layer
   │                    │                         │                        │
   ├─ start ───────────► POST /api/interview ────► InterviewEngine ───────► sessions / messages
   │                    │                         │      │
   │◄─ first question ──┤                         │      ├──► CurriculumLoader ──► data/curriculum.json
   │                    │                         │      ├──► QuestionPlanner
   │                    │                         │      ├──► CandidateAnalyzer ──► data/candidate.json
   │  answer ──────────► POST /api/interview/{id}  │      ├──► MemoryEngine ──────► conversation memory
   │                    │                         │      └──► GeminiService (placeholder)
   │◄─ follow-up ───────┤                         │
   │  ...               │                         │
   │  complete ────────► POST /api/interview/{id}/complete
   │                    │                         └──► EvaluationEngine ─► FeedbackGenerator ─► feedback
   │◄─ report ──────────┤
```

### Folder structure

```
vibecode/
├── README.md
├── .gitignore
├── backend/
│   ├── requirements.txt
│   ├── run.py                        # Dev entry point (uvicorn)
│   ├── .env.example
│   ├── tests/
│   │   └── __init__.py
│   └── app/
│       ├── main.py                   # FastAPI app factory, router registration
│       ├── api/                      # HTTP layer — routing only, no logic
│       │   ├── deps.py               # Dependency injection wiring
│       │   ├── middleware.py         # CORS, request logging, error handling
│       │   └── routes/
│       │       ├── interview.py      # POST /api/interview  (skeleton)
│       │       ├── sessions.py       # Session queries        (skeleton)
│       │       └── health.py         # /api/health            (liveness)
│       ├── services/                 # Application/business services (stubs)
│       │   ├── session_manager.py
│       │   ├── candidate_analyzer.py
│       │   ├── curriculum_loader.py
│       │   ├── question_planner.py
│       │   ├── interview_engine.py
│       │   ├── evaluation_engine.py
│       │   ├── memory_engine.py
│       │   ├── feedback_generator.py
│       │   ├── prompt_builder.py
│       │   └── gemini_service.py     # Placeholder only
│       ├── models/                   # Pydantic DTOs (API contracts)
│       │   ├── common.py             # Reusable primitives (IDs, timestamps)
│       │   ├── session.py
│       │   ├── message.py
│       │   ├── candidate.py
│       │   ├── curriculum.py
│       │   ├── score.py
│       │   ├── feedback.py
│       │   └── interview.py          # API request/response contracts
│       ├── database/
│       │   ├── connection.py         # SQLite pool/connection management
│       │   ├── schema.sql            # DDL — canonical schema definition
│       │   └── repositories/         # Data-access layer
│       │       ├── base.py           # Generic CRUD base
│       │       ├── session_repository.py
│       │       ├── message_repository.py
│       │       ├── score_repository.py
│       │       └── feedback_repository.py
│       ├── memory/
│       │   ├── conversation_memory.py  # Per-session transcript store (future Redis-ready)
│       │   └── state_machine.py        # Interview state transitions
│       ├── prompts/
│       │   ├── templates/              # Prompt templates (empty for now)
│       │   └── __init__.py
│       ├── utils/
│       │   ├── config.py             # Pydantic-settings config
│       │   ├── errors.py             # Domain exceptions + mapping
│       │   └── logging.py            # Logging bootstrap
│       └── data/
│           ├── curriculum.json       # Knowledge source: learning path
│           └── candidate.json        # Knowledge source: candidate profile
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── tailwind.config.js
    ├── postcss.config.js
    ├── index.html
    ├── .env.example
    └── src/
        ├── main.tsx                  # React entry
        ├── App.tsx                   # Router definition
        ├── index.css                 # Tailwind directives
        ├── types/                    # Shared TS contracts
        │   ├── index.ts
        │   ├── candidate.ts
        │   ├── session.ts
        │   ├── interview.ts
        │   └── feedback.ts
        ├── pages/                    # Route pages (empty shells)
        │   ├── Landing.tsx
        │   ├── CandidateSelection.tsx
        │   ├── Interview.tsx
        │   ├── Report.tsx
        │   └── NotFound.tsx
        ├── layouts/MainLayout.tsx    # Shared page shell
        ├── components/
        │   ├── Navbar.tsx
        │   ├── Footer.tsx
        │   └── Loading.tsx
        ├── hooks/
        │   ├── useInterview.ts       # Interview state hook
        │   └── useSession.ts         # Session data hook
        ├── services/
        │   ├── http.ts               # Fetch wrapper (axios-like)
        │   └── api.ts                # Typed API client
        └── context/InterviewContext.tsx  # Interview state provider
```

---

## 2. Design Principles

| Principle | How it is applied |
|-----------|-------------------|
| **SOLID** | Single-responsibility services; interfaces (Protocols) in `services/base.py`-style contracts; services are composed, not fat. |
| **Dependency Injection** | Services receive repositories / other services via constructor; FastAPI wires the graph in `api/deps.py`. |
| **Clean Architecture** | `api` (delivery) → `services` (application) → `repositories` (data). No business logic in routes. |
| **Type hints** | Full type annotations across backend and frontend TS contracts. |
| **Pydantic models** | All API contracts validated at the boundary. |
| **Reusable components** | Shared `Loading`, `Navbar`, `Footer`, layout + hooks. |

---

## 3. Interview State Machine

```
   START ──► INTRODUCTION ──► QUESTION ──► FOLLOW_UP
                 ▲               │              │
                 │               │              ▼
                 │            NEXT_TOPIC ◄─────┤
                 │               │
                 ▼               ▼
              SUMMARY ────────► COMPLETED
```

Transitions are validated by `memory/state_machine.py`. See that module for the
transition table. Allowed transitions are data-driven so new states can be added
without touching the engine.

---

## 4. Database Schema

Canonical DDL for the **public** tables lives in `backend/app/database/schema.sql`
(SQLite) with a PostgreSQL twin at `schema_postgres.sql`. The **private archive**
(see §5) lives in `private_schema.sql` / `private_schema_postgres.sql`.

The backend auto-selects its backend: when `DATABASE_URL` is set to a
`postgres://` DSN it connects to PostgreSQL and runs the `*_postgres.sql` DDL;
otherwise it uses SQLite at `DATABASE_PATH` and the plain `schema.sql` files.
Repositories are backend-agnostic, so no code changes are needed when switching.

| Table | Purpose | Key relationships |
|-------|---------|-------------------|
| `candidates` | Persistent candidate profiles | `id` PK, unique `email` |
| `sessions` | One interview run per candidate | `candidate_id`, `curriculum_id` |
| `messages` | Full conversation transcript | FK `session_id → sessions.id` |
| `scores` | Per-question / per-topic scores | FK `session_id`, `question_id` |
| `feedback` | Structured evaluation + report | FK `session_id` |
| `enrolled_candidates` | (private) immutable enrolled-profile snapshot | mirrors `candidates` |
| `enrolled_reports` | (private) full report of each completed interview | FK `candidate_id` |

### ERD (logical)

```
sessions (1) ──── (N) messages
   │
   ├── (1) ──── (N) scores
   └── (1) ──── (1) feedback
```

Timestamps are UTC ISO-8601 (`TEXT`). Primary keys are `TEXT` UUIDs generated
server-side.

---

## 5. API Contract (skeleton)

Base URL: `/api`

| Method | Path                            | Description                     | Status |
|--------|---------------------------------|---------------------------------|--------|
| GET    | `/api/health`                   | Liveness + version              | Ready  |
| POST   | `/api/interview`                | Create a session, return first step | Ready (placeholder) |
| POST   | `/api/interview/{session_id}/answer` | Submit candidate answer     | Ready (placeholder) |
| POST   | `/api/interview/{session_id}/complete` | End interview, return report | Ready (placeholder) |
| GET    | `/api/interview/{session_id}`   | Fetch current session state    | Ready  |
| GET    | `/api/sessions`                 | List sessions                  | Ready  |
| GET    | `/api/sessions/{session_id}/report` | Retrieve final report      | Ready (placeholder) |

Placeholder responses include a `payload` dict that mirrors the future shape, so
frontend contracts are already stable.

---

## 6. Backend Services (responsibilities)

| Service | Responsibility | Primary collaborators |
|---------|----------------|-----------------------|
| `SessionManager` | Create/load/close interview sessions; persist state | `SessionRepository`, `StateMachine` |
| `CandidateAnalyzer` | Parse candidate profile from `candidate.json` into structured traits | `candidate.json` |
| `CurriculumLoader` | Load & cache curriculum from `curriculum.json` | `curriculum.json` |
| `QuestionPlanner` | Pick next question / topic based on state + curriculum | `CurriculumLoader`, `MemoryEngine` |
| `InterviewEngine` | Orchestrate the conversation loop (top-level coordinator) | All other services |
| `EvaluationEngine` | Score candidate answers per question/topic | `GeminiService`, `MessageRepository`, `AIVerifierEnsemble` |
| `AIVerifierEnsemble` | Cross-check each answer with a panel of independent AIs; majority consensus gates the verdict and mark | `GeminiService`, `PromptBuilder` |
| `MemoryEngine` | Summarize + compress long conversations | `ConversationMemory` |
| `FeedbackGenerator` | Assemble structured report from scores | `EvaluationEngine`, `ScoreRepository` |
| `PromptBuilder` | Build validated prompt payloads (future) | `prompts/templates` |
| `GeminiService` | **Placeholder** — LLM call wrapper, disabled by config | — |

### Scoring pipeline

Every answer is first scored deterministically (lexical concept coverage × a
length factor, fully explainable). When Gemini is enabled, AI semantic scoring
is layered on top: with `AI_VERIFIER_MODELS` set, a **panel of independent AI
models** verifies each answer — the majority decides whether it is correct and
the consensus determines the 0-10 mark; without it, a single Gemini call judges
the answer. Any AI failure falls back to the previous stage, so the AI can never
break scoring.

---

## 7. Getting Started

### Prerequisites
- Python 3.11+ (tested with 3.14)
- Node 20+ and npm
- (Optional) Gemini API key — not required for the skeleton

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (POSIX: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # POSIX: cp .env.example .env
python run.py                     # → http://127.0.0.1:8000  (docs at /docs)
```

### Frontend

```bash
cd frontend
npm install
npm run dev                       # → http://127.0.0.1:5173
```

### Smoke test

```bash
curl http://127.0.0.1:8000/api/health
curl -X POST http://127.0.0.1:8000/api/interview \
     -H "Content-Type: application/json" \
     -d '{"candidate_id": "candidate-001", "curriculum_id": "curriculum-001"}'
```

---

## 8. Environment Variables

| Variable | Backend / Frontend | Default | Purpose |
|----------|--------------------|---------|---------|
| `APP_ENV` | backend | `development` | Runtime environment |
| `DATABASE_PATH` | backend | `data/intervue.db` | SQLite file location (local dev) |
| `DATABASE_URL` | backend | *(empty)* | `postgres://` DSN — when set, the backend uses PostgreSQL instead of SQLite |
| `GEMINI_API_KEY` | backend | *(empty)* | Gemini key — **disabled for now** |
| `GEMINI_MODEL` | backend | `gemini-2.0-flash` | Model identifier (future) |
| `GEMINI_ENABLED` | backend | `false` | Master switch for LLM integration |
| `AI_VERIFIER_MODELS` | backend | *(empty)* | Comma-separated model ids that independently verify every answer (multi-AI scoring) |
| `AI_VERIFIER_AGREEMENT` | backend | `0.5` | Fraction of verifier AIs that must confirm an answer for it to count as correct |
| `CORS_ORIGINS` | backend | `http://localhost:5173` | Allowed frontend origins |
| `VITE_API_URL` | frontend | `/api` | Backend base URL (dev: `http://127.0.0.1:8000/api`); normalized to end with `/api` |
| `VITE_API_BASE_URL` | frontend | *(legacy)* | Deprecated alias for `VITE_API_URL` |

---

## 9. Deployment Notes

One-click deployment is defined in `render.yaml` (Render Blueprint): it provisions
a managed **PostgreSQL** database, the FastAPI backend, and the static-built
frontend, and wires `DATABASE_URL`, `CORS_ORIGINS`, and `VITE_API_URL` between
them automatically.

| Layer | Platform | Config |
|-------|----------|--------|
| Frontend | **Render** (Static Site) | Build `npm run build`, output `dist`; SPA rewrite `/* → /index.html` in `render.yaml` |
| Backend | **Render** (Web Service) | Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; health check `/api/health` |
| Database | **Render** (PostgreSQL) | Managed, wired via `DATABASE_URL`; schema auto-initialized from `schema_postgres.sql` |

> Local development stays on SQLite (`DATABASE_PATH`) with zero config; the
> repository layer is backend-agnostic, so switching to PostgreSQL in production
> requires only setting `DATABASE_URL`. The backend never runs a render-time
> migration — it applies the idempotent DDL on startup.

---

## 10. Roadmap (deliberately not implemented)

- [ ] Gemini API integration (flip `GEMINI_ENABLED=true`)
- [ ] Prompt templates in `prompts/templates/`
- [ ] Question planning & adaptation logic
- [ ] Answer evaluation & scoring
- [ ] Feedback/report generation
- [ ] Frontend UI implementation
- [ ] Unit tests in `backend/tests/`
