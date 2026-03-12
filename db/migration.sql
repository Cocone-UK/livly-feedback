-- Livly Feedback System — Database Schema
-- Run this in Supabase SQL Editor to create all tables

-- Scrape run audit log
CREATE TABLE IF NOT EXISTS scrape_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source text NOT NULL,
    region text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    items_fetched int NOT NULL DEFAULT 0,
    items_new int NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'running',
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_scrape_runs_source_region ON scrape_runs (source, region);
CREATE INDEX idx_scrape_runs_started_at ON scrape_runs (started_at DESC);

-- Raw feedback from all sources
CREATE TABLE IF NOT EXISTS feedback_raw (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    content_hash text NOT NULL,
    source text NOT NULL,
    region text NOT NULL,
    external_id text NOT NULL,
    author text,
    content text NOT NULL,
    rating smallint,
    channel text,
    source_url text,
    posted_at timestamptz NOT NULL,
    scraped_at timestamptz NOT NULL DEFAULT now(),
    superseded_by uuid REFERENCES feedback_raw(id),
    scrape_run_id uuid NOT NULL REFERENCES scrape_runs(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_feedback_raw_content_hash ON feedback_raw (content_hash) WHERE superseded_by IS NULL;
CREATE INDEX idx_feedback_raw_source_region ON feedback_raw (source, region);
CREATE INDEX idx_feedback_raw_external_id ON feedback_raw (source, external_id);
CREATE INDEX idx_feedback_raw_posted_at ON feedback_raw (posted_at DESC);
CREATE INDEX idx_feedback_raw_superseded ON feedback_raw (superseded_by) WHERE superseded_by IS NULL;

-- AI classification results
CREATE TABLE IF NOT EXISTS feedback_classified (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id uuid NOT NULL REFERENCES feedback_raw(id),
    sentiment text NOT NULL,
    categories text[] NOT NULL DEFAULT '{}',
    severity text NOT NULL,
    language text NOT NULL,
    summary text NOT NULL,
    summary_jp text NOT NULL,
    key_quotes text[] NOT NULL DEFAULT '{}',
    classified_at timestamptz NOT NULL DEFAULT now(),
    model_used text NOT NULL
);

CREATE UNIQUE INDEX idx_feedback_classified_feedback_id ON feedback_classified (feedback_id);
CREATE INDEX idx_feedback_classified_sentiment ON feedback_classified (sentiment);
CREATE INDEX idx_feedback_classified_severity ON feedback_classified (severity);
CREATE INDEX idx_feedback_classified_classified_at ON feedback_classified (classified_at DESC);
