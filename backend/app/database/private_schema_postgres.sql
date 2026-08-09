-- ============================================================
-- InterVue AI — private archive schema (PostgreSQL / production)
-- Mirrors backend/app/database/private_schema.sql. This is the
-- "private database": it stores a snapshot of every enrolled
-- candidate plus the full report of each interview they complete.
-- It is never exposed through the public API contract. In
-- production it shares the same PostgreSQL instance as the public
-- tables but keeps its own isolated table names.
-- All statements are idempotent (IF NOT EXISTS).
-- Timestamps are ISO-8601 UTC TEXT. JSON blobs are stored as TEXT.
-- ============================================================

-- ------------------------------------------------------------
-- enrolled_candidates : immutable snapshot of an enrolled profile
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enrolled_candidates (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    email               TEXT,
    role                TEXT NOT NULL DEFAULT '',
    years_of_experience DOUBLE PRECISION NOT NULL DEFAULT 0,
    experience_level    TEXT NOT NULL DEFAULT 'mid',
    skills              TEXT NOT NULL DEFAULT '[]',     -- JSON array of {name, level}
    learning_journey    TEXT NOT NULL DEFAULT '[]',     -- JSON array of LearningJourneyEntry
    preferred_languages TEXT NOT NULL DEFAULT '[]',     -- JSON array of strings
    focus_areas         TEXT NOT NULL DEFAULT '[]',     -- JSON array of strings
    strengths           TEXT NOT NULL DEFAULT '[]',     -- JSON array of strings
    notes               TEXT NOT NULL DEFAULT '',
    enrolled_at         TEXT NOT NULL                   -- when the profile was first archived
);

-- ------------------------------------------------------------
-- enrolled_reports : one full report per completed interview
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enrolled_reports (
    session_id   TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    report       TEXT NOT NULL DEFAULT '{}',            -- full ReportRead JSON
    completed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_enrolled_reports_candidate ON enrolled_reports(candidate_id);
