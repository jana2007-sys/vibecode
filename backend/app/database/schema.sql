-- ============================================================
-- InterVue AI — SQLite schema (canonical DDL)
-- Timestamps are ISO-8601 UTC TEXT. JSON blobs are stored as TEXT.
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- candidates : persistent candidate profiles
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidates (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    email               TEXT,                          -- nullable: seeded/direct profiles may lack one
    role                TEXT NOT NULL DEFAULT '',
    years_of_experience REAL NOT NULL DEFAULT 0,
    experience_level    TEXT NOT NULL DEFAULT 'mid',   -- junior | mid | senior
    skills              TEXT NOT NULL DEFAULT '[]',    -- JSON array of {name, level}
    learning_journey    TEXT NOT NULL DEFAULT '[]',    -- JSON array of LearningJourneyEntry
    preferred_languages TEXT NOT NULL DEFAULT '[]',    -- JSON array of strings
    focus_areas         TEXT NOT NULL DEFAULT '[]',    -- JSON array of strings
    strengths           TEXT NOT NULL DEFAULT '[]',    -- JSON array of strings
    notes               TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

-- Emails are unique where present (SQLite treats NULLs as distinct, so this
-- index never rejects rows created without an email).
CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_email ON candidates(email);

-- ------------------------------------------------------------
-- sessions : one interview run per candidate + curriculum
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    candidate_id  TEXT NOT NULL,
    curriculum_id TEXT NOT NULL,
    state         TEXT NOT NULL DEFAULT 'START',
    topic_index   INTEGER NOT NULL DEFAULT 0,
    context       TEXT NOT NULL DEFAULT '{}',      -- JSON: active topic, follow-up depth, ...
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    completed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_candidate ON sessions(candidate_id);

-- ------------------------------------------------------------
-- messages : full conversation transcript
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,                      -- system | interviewer | candidate
    content    TEXT NOT NULL,
    metadata   TEXT NOT NULL DEFAULT '{}',         -- JSON: question_id, topic_id, ...
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

-- ------------------------------------------------------------
-- scores : per-question / per-topic evaluation results
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scores (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    topic_id    TEXT NOT NULL DEFAULT '',
    question_id TEXT NOT NULL DEFAULT '',
    score       REAL NOT NULL CHECK (score >= 0 AND score <= 10),
    rationale   TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scores_session ON scores(session_id);

-- ------------------------------------------------------------
-- feedback : one structured report per session
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL UNIQUE REFERENCES sessions(id) ON DELETE CASCADE,
    overall_score REAL NOT NULL CHECK (overall_score >= 0 AND overall_score <= 10),
    summary       TEXT NOT NULL DEFAULT '',
    strengths     TEXT NOT NULL DEFAULT '[]',      -- JSON array
    improvements  TEXT NOT NULL DEFAULT '[]',      -- JSON array
    topics        TEXT NOT NULL DEFAULT '[]',      -- JSON array of TopicSummary
    created_at    TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'deterministic'   -- ai | deterministic
);
