-- Safe, non-destructive migration for queue pause/resume support.
-- Apply manually after review:
-- psql "$DATABASE_URL" -f database/migrations/001_add_queue_paused_to_businesses.sql

ALTER TABLE businesses
ADD COLUMN IF NOT EXISTS queue_paused BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN businesses.queue_paused IS 'Whether the business queue is temporarily paused.';
