CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TABLE IF NOT EXISTS water_intake_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    date TEXT NOT NULL,
    delta_ml INTEGER NOT NULL CHECK (delta_ml <> 0),
    event_type TEXT NOT NULL DEFAULT 'ADD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_water_intake_events_event_type CHECK (event_type IN ('ADD', 'REMOVE', 'ADJUSTMENT'))
);
CREATE INDEX IF NOT EXISTS idx_water_intake_events_user_id ON water_intake_events(user_id);
CREATE INDEX IF NOT EXISTS idx_water_intake_events_user_date ON water_intake_events(user_id, date DESC, created_at ASC);
INSERT INTO water_intake_events (user_id, date, delta_ml, event_type, created_at)
SELECT w.user_id, w.date, w.consumed_ml, 'ADJUSTMENT', w.created_at
FROM water_daily_intake w
WHERE w.consumed_ml > 0
  AND NOT EXISTS (
      SELECT 1
      FROM water_intake_events e
      WHERE e.user_id = w.user_id
        AND e.date = w.date
  );
ALTER TABLE water_intake_events DISABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS weight_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    weight_kg NUMERIC(6,2) NOT NULL CHECK (weight_kg > 0),
    measured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_weight_entries_user_id ON weight_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_weight_entries_user_measured_at ON weight_entries(user_id, measured_at DESC);
ALTER TABLE weight_entries DISABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS developer_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    user_name TEXT NOT NULL,
    message TEXT NOT NULL,
    image_url TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    developer_response TEXT,
    responded_at TIMESTAMPTZ,
    responded_by TEXT,
    response_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_developer_feedback_status CHECK (status IN ('OPEN', 'ANSWERED'))
);
CREATE INDEX IF NOT EXISTS idx_developer_feedback_user_id ON developer_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_developer_feedback_status ON developer_feedback(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_developer_feedback_created_at ON developer_feedback(created_at DESC);
DROP TRIGGER IF EXISTS trg_developer_feedback_updated_at ON developer_feedback;
CREATE TRIGGER trg_developer_feedback_updated_at
BEFORE UPDATE ON developer_feedback
FOR EACH ROW
EXECUTE FUNCTION set_updated_at_timestamp();
ALTER TABLE developer_feedback DISABLE ROW LEVEL SECURITY;
