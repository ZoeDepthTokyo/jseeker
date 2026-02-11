-- Migration 003: Job Discovery Architecture Fixes
-- Adds market field, search sessions, and tag weights

-- 1. Add market column to job_discoveries (if not exists)
-- SQLite doesn't support IF NOT EXISTS for ALTER TABLE ADD COLUMN
-- So we use a pragma check approach
ALTER TABLE job_discoveries ADD COLUMN market TEXT;

-- 2. Create search_sessions table for pause/resume functionality
CREATE TABLE IF NOT EXISTS search_sessions (
    id INTEGER PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active', -- active, paused, completed, stopped
    tags TEXT, -- JSON array of search tags
    markets TEXT, -- JSON array of markets
    sources TEXT, -- JSON array of sources
    limit_reached BOOLEAN DEFAULT FALSE,
    total_found INTEGER DEFAULT 0,
    completed_at TIMESTAMP
);

-- 3. Create tag_weights table for weighted search ranking
CREATE TABLE IF NOT EXISTS tag_weights (
    tag TEXT PRIMARY KEY,
    weight INTEGER DEFAULT 50, -- 1-100 scale, 50 is default
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Create index on market field for faster filtering
CREATE INDEX IF NOT EXISTS idx_job_discoveries_market ON job_discoveries(market);

-- 5. Create index on source field for faster filtering
CREATE INDEX IF NOT EXISTS idx_job_discoveries_source ON job_discoveries(source);

-- 6. Create composite index on (market, location) for grouped queries
CREATE INDEX IF NOT EXISTS idx_job_discoveries_market_location ON job_discoveries(market, location);
