-- Migration: Create game_scores table for unified score submission
-- Date: 2026-05-03
-- Description: Unified score table for all Octile Universe games
-- Safe to run multiple times (CREATE TABLE IF NOT EXISTS)

-- Create game_scores table
CREATE TABLE IF NOT EXISTS game_scores (
    -- Primary key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Game identifier
    game_id TEXT NOT NULL,

    -- Player identity (shared across games)
    browser_uuid TEXT NOT NULL,
    user_id INTEGER,  -- FK to octile_users.id (nullable for anonymous)

    -- Common metrics
    score_value REAL NOT NULL,  -- Primary metric (time/points/etc)
    time_seconds REAL,  -- Duration (nullable for score-based games)

    -- Game-specific data (JSONB for flexibility)
    game_data TEXT NOT NULL,  -- JSON string (SQLite doesn't have native JSON type)

    -- Metadata
    platform TEXT,  -- 'web', 'android', 'ios'
    ota_version INTEGER,
    submission_id TEXT NOT NULL UNIQUE,  -- Client-generated UUID for idempotency

    -- Anti-cheat & verification
    solution TEXT,  -- Game-specific solution encoding
    moves_data TEXT,  -- Game-specific move log
    flagged INTEGER DEFAULT 0,  -- 0=normal, 1=flagged
    flagged_reason TEXT,

    -- Rewards (server-authoritative)
    exp INTEGER DEFAULT 0,
    diamonds INTEGER DEFAULT 0,
    coins INTEGER DEFAULT 0,  -- legacy

    -- Client info (extracted by worker)
    client_ip TEXT,
    user_agent TEXT,

    -- Timestamps
    client_timestamp DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
-- Note: SQLite doesn't support IF NOT EXISTS for indexes in older versions
-- We use DROP IF EXISTS + CREATE pattern for safety

-- Index: submission_id (unique constraint, already defined in table)
-- No separate index needed, UNIQUE creates implicit index

-- Index: game_id (for game-specific queries)
DROP INDEX IF EXISTS idx_game_scores_game_id;
CREATE INDEX idx_game_scores_game_id ON game_scores(game_id);

-- Index: browser_uuid (for player history)
DROP INDEX IF EXISTS idx_game_scores_uuid;
CREATE INDEX idx_game_scores_uuid ON game_scores(browser_uuid);

-- Index: game_id + browser_uuid (for player progress per game)
DROP INDEX IF EXISTS idx_game_scores_game_uuid;
CREATE INDEX idx_game_scores_game_uuid ON game_scores(game_id, browser_uuid);

-- Index: game_id + score_value (for leaderboards)
DROP INDEX IF EXISTS idx_game_scores_game_score;
CREATE INDEX idx_game_scores_game_score ON game_scores(game_id, score_value);

-- Index: user_id (for authenticated user queries)
DROP INDEX IF EXISTS idx_game_scores_userid;
CREATE INDEX idx_game_scores_userid ON game_scores(user_id);

-- Index: created_at (for recent submissions)
DROP INDEX IF EXISTS idx_game_scores_created;
CREATE INDEX idx_game_scores_created ON game_scores(created_at);

-- Verification query (check table exists and has correct structure)
-- Run this after migration to verify success:
-- SELECT sql FROM sqlite_master WHERE type='table' AND name='game_scores';
-- SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='game_scores';
