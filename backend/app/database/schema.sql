-- ============================================================
-- InterVue AI — SQLite schema (canonical DDL)
-- Timestamps are ISO-8601 UTC TEXT. JSON blobs are stored as TEXT.
-- ============================================================

PRAGMA foreign_keys = ON;

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
    created_at    TEXT NOT NULL
);
