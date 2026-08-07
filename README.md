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

## 4. Database Schema (SQLite)

Canonical DDL lives in `backend/app/database/schema.sql`.

| Table | Purpose | Key relationships |
|-------|---------|-------------------|
| `sessions` | One interview run per candidate | `candidate_id`, `curriculum_id`, FK to `sessions.id` self-ref not needed |
| `messages` | Full conversation transcript | FK `session_id → sessions.id` |
| `scores` | Per-question / per-topic scores | FK `session_id`, `question_id` |
| `feedback` | Structured evaluation + report | FK `session_id` |

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
| `EvaluationEngine` | Score candidate answers per question/topic | `GeminiService`, `MessageRepository` |
| `MemoryEngine` | Summarize + compress long conversations | `ConversationMemory` |
| `FeedbackGenerator` | Assemble structured report from scores | `EvaluationEngine`, `ScoreRepository` |
| `PromptBuilder` | Build validated prompt payloads (future) | `prompts/templates` |
| `GeminiService` | **Placeholder** — LLM call wrapper, disabled by config | — |

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
| `DATABASE_PATH` | backend | `data/intervue.db` | SQLite file location |
| `GEMINI_API_KEY` | backend | *(empty)* | Gemini key — **disabled for now** |
| `GEMINI_MODEL` | backend | `gemini-2.0-flash` | Model identifier (future) |
| `GEMINI_ENABLED` | backend | `false` | Master switch for LLM integration |
| `CORS_ORIGINS` | backend | `http://localhost:5173` | Allowed frontend origins |
| `VITE_API_BASE_URL` | frontend | `http://127.0.0.1:8000/api` | Backend base URL |

---

## 9. Deployment Notes

| Layer | Platform | Config |
|-------|----------|--------|
| Frontend | **Vercel** | Build `npm run build`, output `dist`; rewrite all routes to `index.html` for SPA routing |
| Backend | **Render** | Start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; SQLite persisted via Render disk mounted at `DATABASE_PATH` |

> SQLite is single-file; in production attach a Render persistent disk. For
> multi-instance scaling, swap the repository layer for PostgreSQL (contracts
> are already repository-isolated).

---

## 10. Roadmap (deliberately not implemented)

- [ ] Gemini API integration (flip `GEMINI_ENABLED=true`)
- [ ] Prompt templates in `prompts/templates/`
- [ ] Question planning & adaptation logic
- [ ] Answer evaluation & scoring
- [ ] Feedback/report generation
- [ ] Frontend UI implementation
- [ ] Unit tests in `backend/tests/`
