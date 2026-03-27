-- ============================================================
-- Supabase Migration: PJ Assistant Tables
-- Run this in Supabase SQL Editor (Dashboard > SQL Editor)
-- ============================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
-- ============================================================
-- 2. Customer Profiles table
-- ============================================================
CREATE TABLE IF NOT EXISTS customer_profiles (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    document TEXT NOT NULL,          -- CNPJ
    segment TEXT NOT NULL DEFAULT 'standard',
    monthly_revenue NUMERIC(15,2) DEFAULT 0,
    account_age_months INTEGER DEFAULT 0,
    credit_score INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_customer_profiles_customer_id ON customer_profiles(customer_id);
-- ============================================================
-- 3. Customer Transactions table
-- ============================================================
CREATE TABLE IF NOT EXISTS customer_transactions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    amount NUMERIC(15,2) NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('credit', 'debit')),
    category TEXT NOT NULL DEFAULT 'uncategorized',
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- Index for fast lookup by customer
CREATE INDEX IF NOT EXISTS idx_customer_transactions_customer_id ON customer_transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_customer_transactions_date ON customer_transactions(date DESC);
-- ============================================================
-- 4. Documents table for RAG (pgvector)
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding VECTOR(384)            -- 384 dimensions for all-MiniLM-L6-v2
);
-- Index for vector similarity search (IVFFlat)
CREATE INDEX IF NOT EXISTS idx_documents_embedding ON documents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);
-- ============================================================
-- 5. RPC function for semantic search
-- ============================================================
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding VECTOR(384),
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id TEXT,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        d.id,
        d.content,
        d.metadata,
        1 - (d.embedding <=> query_embedding) AS similarity
    FROM documents d
    WHERE 1 - (d.embedding <=> query_embedding) > match_threshold
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
$$;
-- ============================================================
-- 6. Row Level Security (RLS)
-- ============================================================
ALTER TABLE customer_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
-- Service role can do everything (used by our backend)
CREATE POLICY "Service role full access profiles"
    ON customer_profiles FOR ALL
    USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access transactions"
    ON customer_transactions FOR ALL
    USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access documents"
    ON documents FOR ALL
    USING (auth.role() = 'service_role');
-- Anon can only read (for BFA with anon key if needed)
CREATE POLICY "Anon read profiles"
    ON customer_profiles FOR SELECT
    USING (auth.role() = 'anon');
CREATE POLICY "Anon read transactions"
    ON customer_transactions FOR SELECT
    USING (auth.role() = 'anon');
CREATE POLICY "Anon read documents"
    ON documents FOR SELECT
    USING (auth.role() = 'anon');
-- ============================================================
-- 7. Seed data (sample customers and transactions)
-- ============================================================

-- Sample customer profiles
INSERT INTO customer_profiles (customer_id, name, document, segment, monthly_revenue, account_age_months, credit_score)
VALUES
    ('cust-001', 'TechSolutions Ltda', '12.345.678/0001-90', 'middle_market', 250000.00, 48, 780),
    ('cust-002', 'Padaria Pão Dourado ME', '98.765.432/0001-10', 'small_business', 45000.00, 24, 620),
    ('cust-003', 'Global Importações S.A.', '11.222.333/0001-44', 'corporate', 1500000.00, 96, 850),
    ('cust-004', 'Startup Inovação Ltda', '55.666.777/0001-88', 'startup', 15000.00, 6, 500),
    ('cust-005', 'Construtora Horizonte Ltda', '33.444.555/0001-22', 'middle_market', 800000.00, 60, 720)
ON CONFLICT (customer_id) DO NOTHING;
-- Sample transactions for cust-001
INSERT INTO customer_transactions (customer_id, date, amount, type, category, description)
VALUES
    ('cust-001', '2025-12-01', 85000.00, 'credit', 'revenue', 'Contrato de consultoria - Cliente A'),
    ('cust-001', '2025-12-03', -12000.00, 'debit', 'payroll', 'Folha de pagamento'),
    ('cust-001', '2025-12-05', -3500.00, 'debit', 'rent', 'Aluguel escritório'),
    ('cust-001', '2025-12-07', 120000.00, 'credit', 'revenue', 'Projeto de software - Cliente B'),
    ('cust-001', '2025-12-10', -8000.00, 'debit', 'supplier', 'Licenças de software'),
    ('cust-001', '2025-12-12', -2500.00, 'debit', 'utilities', 'Internet e telefonia'),
    ('cust-001', '2025-12-15', 45000.00, 'credit', 'revenue', 'Manutenção mensal - Cliente C'),
    ('cust-001', '2025-12-18', -15000.00, 'debit', 'marketing', 'Campanha Google Ads'),
    ('cust-001', '2025-12-20', -5000.00, 'debit', 'tax', 'IRPJ estimativa'),
    ('cust-001', '2025-12-22', -1800.00, 'debit', 'utilities', 'Energia elétrica'),
    ('cust-001', '2025-12-28', 60000.00, 'credit', 'revenue', 'Consultoria estratégica - Cliente D'),
    ('cust-001', '2025-12-30', -20000.00, 'debit', 'payroll', 'Bonificação equipe')
ON CONFLICT DO NOTHING;
-- Sample transactions for cust-002
INSERT INTO customer_transactions (customer_id, date, amount, type, category, description)
VALUES
    ('cust-002', '2025-12-01', 15000.00, 'credit', 'revenue', 'Vendas semana 1'),
    ('cust-002', '2025-12-05', -6000.00, 'debit', 'supplier', 'Farinha e insumos'),
    ('cust-002', '2025-12-08', 12000.00, 'credit', 'revenue', 'Vendas semana 2'),
    ('cust-002', '2025-12-10', -4500.00, 'debit', 'payroll', 'Salários funcionários'),
    ('cust-002', '2025-12-15', 18000.00, 'credit', 'revenue', 'Vendas semana 3 + encomendas'),
    ('cust-002', '2025-12-18', -2000.00, 'debit', 'rent', 'Aluguel ponto comercial'),
    ('cust-002', '2025-12-20', -800.00, 'debit', 'utilities', 'Conta de luz'),
    ('cust-002', '2025-12-25', -3000.00, 'debit', 'supplier', 'Compra equipamento'),
    ('cust-002', '2025-12-28', 14000.00, 'credit', 'revenue', 'Vendas semana 4')
ON CONFLICT DO NOTHING;
-- Sample transactions for cust-004 (startup with negative cashflow)
INSERT INTO customer_transactions (customer_id, date, amount, type, category, description)
VALUES
    ('cust-004', '2025-12-01', 5000.00, 'credit', 'revenue', 'Primeiro cliente pagante'),
    ('cust-004', '2025-12-05', -8000.00, 'debit', 'payroll', 'Salários co-founders'),
    ('cust-004', '2025-12-10', -3000.00, 'debit', 'infrastructure', 'AWS + serviços cloud'),
    ('cust-004', '2025-12-15', -2000.00, 'debit', 'marketing', 'Anúncios Instagram'),
    ('cust-004', '2025-12-20', 10000.00, 'credit', 'revenue', 'Venda licença SaaS'),
    ('cust-004', '2025-12-25', -5000.00, 'debit', 'supplier', 'Ferramentas de desenvolvimento')
ON CONFLICT DO NOTHING;
-- ============================================================
-- 8. Updated_at trigger
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trigger_customer_profiles_updated_at
    BEFORE UPDATE ON customer_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
