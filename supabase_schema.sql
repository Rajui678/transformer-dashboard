-- Run this once in your Supabase project's SQL Editor
-- Dashboard: app.supabase.com → SQL Editor → New Query

CREATE TABLE IF NOT EXISTS reports (
    id          BIGSERIAL    PRIMARY KEY,
    report_date DATE         NOT NULL,
    tr_name     TEXT         NOT NULL,
    data_json   JSONB        NOT NULL,
    pdf_blob    TEXT,                    -- base64-encoded PDF bytes
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Index for fast trend queries
CREATE INDEX IF NOT EXISTS idx_reports_tr_name ON reports (tr_name, report_date);

-- Row Level Security (RLS) — enable when you add auth
-- ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "authenticated users only"
--   ON reports FOR ALL
--   USING (auth.role() = 'authenticated');

-- Optional: restrict anon key to SELECT only
-- REVOKE INSERT, UPDATE, DELETE ON reports FROM anon;
-- GRANT  INSERT, UPDATE, DELETE ON reports TO authenticated;

COMMENT ON TABLE reports IS
  'Transformer field test reports — managed by Transformer Testing Dashboard';
