-- Notifications schema for read, soft delete, and internal publishing.

CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'INFO',
    image_url TEXT,
    action_label TEXT,
    action_route TEXT,
    read_at TIMESTAMPTZ,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS message TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS type TEXT NOT NULL DEFAULT 'INFO';
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS action_label TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS action_route TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_created_at ON notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user_deleted_created_at ON notifications(user_id, is_deleted, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, is_deleted, read_at);
DROP TRIGGER IF EXISTS trg_notifications_updated_at ON notifications;
CREATE TRIGGER trg_notifications_updated_at
BEFORE UPDATE ON notifications
FOR EACH ROW
EXECUTE FUNCTION set_updated_at_timestamp();
ALTER TABLE notifications DISABLE ROW LEVEL SECURITY;
