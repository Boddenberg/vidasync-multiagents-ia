-- ============================================================
-- Migration 003: Auth — PJ Assistant
-- ============================================================
-- Handles: credentials (bcrypt passwords), refresh tokens,
--          password reset codes, customer_profiles extension
-- ============================================================

-- ============================================================
-- 1. Extend customer_profiles for registration fields
-- ============================================================
ALTER TABLE customer_profiles
    ADD COLUMN IF NOT EXISTS company_name TEXT,
    ADD COLUMN IF NOT EXISTS email TEXT,
    ADD COLUMN IF NOT EXISTS account_status TEXT NOT NULL DEFAULT 'active'
        CHECK (account_status IN ('active', 'blocked', 'closed', 'pending')),
    ADD COLUMN IF NOT EXISTS relationship_since TIMESTAMPTZ DEFAULT NOW();
-- Representative (legal representative of the PJ)
ALTER TABLE customer_profiles
    ADD COLUMN IF NOT EXISTS representante_name TEXT,
    ADD COLUMN IF NOT EXISTS representante_cpf TEXT,
    ADD COLUMN IF NOT EXISTS representante_phone TEXT,
    ADD COLUMN IF NOT EXISTS representante_birth_date TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_profiles_document
    ON customer_profiles(document);
CREATE INDEX IF NOT EXISTS idx_customer_profiles_email
    ON customer_profiles(email);
-- ============================================================
-- 2. Credentials table (password hashes)
-- ============================================================
CREATE TABLE IF NOT EXISTS auth_credentials (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT UNIQUE NOT NULL
        REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    failed_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    password_changed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_auth_credentials_customer
    ON auth_credentials(customer_id);
-- ============================================================
-- 3. Refresh tokens table (supports rotation)
-- ============================================================
CREATE TABLE IF NOT EXISTS auth_refresh_tokens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT NOT NULL
        REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMPTZ,
    user_agent TEXT,
    ip_address TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_customer
    ON auth_refresh_tokens(customer_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash
    ON auth_refresh_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires
    ON auth_refresh_tokens(expires_at);
-- ============================================================
-- 4. Password reset codes
-- ============================================================
CREATE TABLE IF NOT EXISTS auth_password_reset_codes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT NOT NULL
        REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reset_codes_customer
    ON auth_password_reset_codes(customer_id);
-- ============================================================
-- 5. RLS
-- ============================================================
ALTER TABLE auth_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_password_reset_codes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access auth_credentials"
    ON auth_credentials FOR ALL
    USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access auth_refresh_tokens"
    ON auth_refresh_tokens FOR ALL
    USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access auth_password_reset_codes"
    ON auth_password_reset_codes FOR ALL
    USING (auth.role() = 'service_role');
-- ============================================================
-- 6. updated_at triggers
-- ============================================================
CREATE TRIGGER trigger_auth_credentials_updated_at
    BEFORE UPDATE ON auth_credentials
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
-- ============================================================
-- 7. Cleanup: auto-expire old refresh tokens (optional RPC)
-- ============================================================
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS void
LANGUAGE sql
AS $$
    DELETE FROM auth_refresh_tokens
    WHERE expires_at < NOW() OR revoked = TRUE;

    DELETE FROM auth_password_reset_codes
    WHERE expires_at < NOW() OR used = TRUE;
$$;
