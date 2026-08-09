# PROMPTS.md

Prompt log used to vibe-code InterVue AI. These are the prompts (verbatim where
available) that drove the build and deployment of this project.

## 1. Project kickoff — architecture & skeleton

> Build a production-ready foundation for "InterVue AI" — an adaptive AI technical
> interview agent. Clean architecture: FastAPI backend with layered services
> (session manager, curriculum loader, question planner, evaluation engine,
> feedback generator, memory engine), SQLite-first database with a PostgreSQL
> twin schema, Pydantic DTOs, and a React + Vite + Tailwind frontend. Keep the
> business logic and Gemini integration as clearly-marked placeholders.

## 2. Database layer

> Add a generic CRUD base repository plus session, message, score, and feedback
> repositories. Define the canonical DDL in `schema.sql` with a `schema_postgres.sql`
> twin. The backend should auto-select the backend: if `DATABASE_URL` is a
> `postgres://` DSN, connect to PostgreSQL and run the `*_postgres.sql` DDL;
> otherwise use SQLite at `DATABASE_PATH`. Repositories must be backend-agnostic.

## 3. API contract & state machine

> Define the interview API contract under `/api`: create session, submit answer,
> complete interview, fetch session, list sessions, and fetch report. Implement a
> data-driven interview state machine (START -> INTRODUCTION -> QUESTION ->
> FOLLOW_UP -> NEXT_TOPIC -> SUMMARY -> COMPLETED) with validated transitions.

## 4. Deterministic scoring + AI verifier ensemble

> Score each answer deterministically first (lexical concept coverage × length
> factor, fully explainable). When Gemini is enabled, layer AI semantic scoring on
> top: with `AI_VERIFIER_MODELS` set, run a panel of independent AI models and use
> majority consensus to gate correctness and the 0-10 mark; without it, a single
> Gemini call judges the answer. Any AI failure must fall back to the previous
> stage so the AI can never break scoring. Keep Gemini disabled by default.

## 5. Frontend UI

> Build the React frontend: landing page, candidate selection, live interview view,
> and report page, with shared Navbar/Footer/Loading components, a typed API client,
> and hooks for interview and session state. Use Tailwind, dark mode default, and an
> SPA-friendly React Router setup. Smoke-test the whole flow against the backend.

## 6. Custom candidate profiles

> Add support for custom candidate profiles with seeded, difficulty-aware question
> deck filling so candidate decks don't overlap. Keep the curriculum and candidate
> knowledge sources as JSON files (`data/curriculum.json`, `data/candidate.json`).

## 7. Render deployment blueprint

> Write a `render.yaml` blueprint that provisions a managed PostgreSQL database, the
> FastAPI backend (web service, health check `/api/health`, start command
> `uvicorn app.main:app --host 0.0.0.0 --port $PORT`), and the built React frontend
> (static site, publish `dist`, SPA rewrite `/* -> /index.html`). Wire
> `DATABASE_URL`, `CORS_ORIGINS`, and `VITE_API_URL` between the services
> automatically. Fix the Render deployment configuration so the blueprint works.

## 8. Deploy to Render and verify

> Deploy this project on Render and give the final URL link to verify.

> I'll paste my Render API key. ... [deployment session]

- Create the managed PostgreSQL instance (`intervue-db`, free plan) via
  `POST /v1/postgres`.
- Create the backend web service (`intervue-api`) with repo
  `https://github.com/jana2007-sys/vibecode`, rootDir `backend`, python runtime,
  env `DATABASE_URL` = the Postgres connection string, and
  `CORS_ORIGINS` set to the deployed frontend origin.
- Create the frontend static site (`intervue-frontend`) with rootDir `frontend`,
  build `npm install && npm run build`, publish `dist`, and
  `VITE_API_URL` = the backend URL.
- Diagnose the backend crash (`psycopg.OperationalError: SSL connection has been
  closed unexpectedly`) by pulling runtime logs, identify the Postgres IP
  allowlist as the cause, open it to `0.0.0.0/0`, and redeploy until
  `/api/health` returns `{"status":"ok","database":"ok"}`.
- Verify data is persisted by querying the live database
  (sessions, messages, scores, feedback, enrolled reports).

> How can I check whether the backend database is storing data in SQL?

> Can you push all in my GitHub?

> Can you post the project link to my GitHub? (added Live Demo links to README)

> Create PROMPTS.md in the repo so the build can be verified as genuinely
> vibe-coded.
