-- ============================================================
-- Tabela: onboarding_sessions
-- Armazena dados temporários de clientes abrindo conta PJ via chat.
-- O session_id é gerado pelo frontend (um por conversa).
-- A cada campo validado pelo BFA, o campo é salvo aqui via PATCH/upsert.
-- ============================================================

CREATE TABLE IF NOT EXISTS onboarding_sessions (
    id                      UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id              TEXT NOT NULL UNIQUE,
    cnpj                    TEXT,
    razao_social            TEXT,
    nome_fantasia           TEXT,
    email                   TEXT,
    representante_name      TEXT,
    representante_cpf       TEXT,
    representante_phone     TEXT,
    representante_birth_date TEXT,
    password_hash           TEXT,
    status                  TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress | completed
    customer_id             TEXT,     -- preenchido ao finalizar (UUID da conta criada)
    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);
-- Index para busca rápida por session_id
CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_session_id ON onboarding_sessions(session_id);
-- RLS: permitir acesso via service_role (o BFA usa service_role_key)
ALTER TABLE onboarding_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on onboarding_sessions"
    ON onboarding_sessions
    FOR ALL
    USING (true)
    WITH CHECK (true);
