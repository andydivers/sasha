-- Run this in Supabase SQL Editor (one time)
-- https://supabase.com/dashboard/project/wxrdudmtishleicfgoqv/sql/new

CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    language TEXT DEFAULT 'en',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chats (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    message TEXT,
    response TEXT,
    latency_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    title TEXT,
    due_date TIMESTAMPTZ,
    done BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    event_type TEXT,
    event_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS integrations (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    service TEXT,
    token_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    job_id TEXT UNIQUE,
    task_type TEXT,
    config JSONB DEFAULT '{}',
    next_run TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS sheet_url TEXT DEFAULT '';

ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS done BOOLEAN DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS pending_payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    service TEXT NOT NULL,
    amount NUMERIC(10,6) NOT NULL,
    unique_amount NUMERIC(12,6) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    network TEXT,
    txid TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_amount ON pending_payments(unique_amount) WHERE status = 'pending';

-- Local expense storage (no sheet required)
CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    description TEXT NOT NULL,
    amount TEXT DEFAULT '',
    category TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS has_seen_sheet_offer BOOLEAN DEFAULT FALSE;

ALTER TABLE expenses ADD COLUMN IF NOT EXISTS synced BOOLEAN DEFAULT FALSE;

ALTER TABLE users ADD COLUMN IF NOT EXISTS digest_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS digest_time TEXT DEFAULT '09:00';

CREATE TABLE IF NOT EXISTS movements (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    location TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
