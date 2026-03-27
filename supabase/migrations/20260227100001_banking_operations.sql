-- ============================================================
-- Migration 002: Banking Operations - PJ Assistant
-- Run this in Supabase SQL Editor (Dashboard > SQL Editor)
-- ============================================================
-- Covers: Auth, Accounts, PIX, Scheduled Transfers, Credit Card PJ,
--         Bill Payments (boleto/barcode), Debit Purchases,
--         Spending Analytics, Notifications, Audit Log
-- ============================================================

-- ============================================================
-- 0. Extensions
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- ============================================================
-- 1. USERS & AUTHENTICATION
-- ============================================================
-- Supabase Auth handles JWT/session, but we need a profile table
-- that links auth.users to our business domain.

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    full_name TEXT NOT NULL,
    cpf TEXT UNIQUE,                          -- CPF do representante legal
    role TEXT NOT NULL DEFAULT 'owner'
        CHECK (role IN ('owner', 'admin', 'operator', 'viewer')),
    avatar_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    email_verified BOOLEAN DEFAULT FALSE,
    phone_verified BOOLEAN DEFAULT FALSE,
    mfa_enabled BOOLEAN DEFAULT FALSE,
    last_login_at TIMESTAMPTZ,
    login_count INTEGER DEFAULT 0,
    failed_login_count INTEGER DEFAULT 0,
    locked_until TIMESTAMPTZ,
    accepted_terms_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_cpf ON users(cpf);
-- Mapping: which users can operate which companies
CREATE TABLE IF NOT EXISTS user_companies (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'owner'
        CHECK (role IN ('owner', 'admin', 'operator', 'viewer')),
    is_default BOOLEAN DEFAULT FALSE,
    permissions JSONB DEFAULT '["read"]',     -- granular: ["read","pix","transfer","card","bill_pay"]
    added_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, customer_id)
);
CREATE INDEX IF NOT EXISTS idx_user_companies_user ON user_companies(user_id);
CREATE INDEX IF NOT EXISTS idx_user_companies_customer ON user_companies(customer_id);
-- ============================================================
-- 2. ACCOUNTS (Contas Bancárias PJ)
-- ============================================================

CREATE TABLE IF NOT EXISTS accounts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    account_type TEXT NOT NULL DEFAULT 'checking'
        CHECK (account_type IN ('checking', 'savings', 'payment', 'escrow')),
    branch TEXT NOT NULL,                     -- agência
    account_number TEXT NOT NULL,
    digit TEXT NOT NULL,
    bank_code TEXT NOT NULL DEFAULT '341',    -- Itaú = 341
    bank_name TEXT NOT NULL DEFAULT 'Itaú Unibanco',
    balance NUMERIC(15,2) DEFAULT 0.00,
    available_balance NUMERIC(15,2) DEFAULT 0.00,  -- saldo disponível (descontando bloqueios)
    overdraft_limit NUMERIC(15,2) DEFAULT 0.00,    -- limite de cheque especial
    currency TEXT NOT NULL DEFAULT 'BRL',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'blocked', 'closed', 'pending_activation')),
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(branch, account_number, digit)
);
CREATE INDEX IF NOT EXISTS idx_accounts_customer ON accounts(customer_id);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
-- ============================================================
-- 3. PIX KEYS (Chaves Pix)
-- ============================================================

CREATE TABLE IF NOT EXISTS pix_keys (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    key_type TEXT NOT NULL
        CHECK (key_type IN ('cpf', 'cnpj', 'email', 'phone', 'random')),
    key_value TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'pending', 'inactive', 'portability_requested')),
    registered_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pix_keys_account ON pix_keys(account_id);
CREATE INDEX IF NOT EXISTS idx_pix_keys_customer ON pix_keys(customer_id);
CREATE INDEX IF NOT EXISTS idx_pix_keys_value ON pix_keys(key_value);
-- ============================================================
-- 4. PIX TRANSFERS
-- ============================================================

CREATE TABLE IF NOT EXISTS pix_transfers (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,     -- para evitar duplicação
    source_account_id UUID NOT NULL REFERENCES accounts(id),
    source_customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id),
    -- Destino (pode ser externo, então não FK)
    destination_key_type TEXT NOT NULL
        CHECK (destination_key_type IN ('cpf', 'cnpj', 'email', 'phone', 'random', 'manual')),
    destination_key_value TEXT NOT NULL,
    destination_name TEXT,
    destination_document TEXT,                -- CPF/CNPJ do destinatário
    destination_bank TEXT,
    destination_branch TEXT,
    destination_account TEXT,
    destination_account_type TEXT
        CHECK (destination_account_type IN ('checking', 'savings', 'payment', NULL)),
    amount NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL DEFAULT 'BRL',
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled', 'returned')),
    failure_reason TEXT,
    end_to_end_id TEXT UNIQUE,               -- ID E2E do BACEN
    initiated_by UUID REFERENCES users(id),
    approved_by UUID REFERENCES users(id),   -- para alçada
    requires_approval BOOLEAN DEFAULT FALSE,
    ip_address INET,
    device_id TEXT,
    -- Pix com cartão de crédito
    funded_by TEXT DEFAULT 'balance'
        CHECK (funded_by IN ('balance', 'credit_card')),
    credit_card_id UUID,                     -- referência ao cartão se funded_by = 'credit_card'
    credit_card_installments INTEGER DEFAULT 1,
    scheduled_for TIMESTAMPTZ,               -- NULL = imediato
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pix_transfers_source ON pix_transfers(source_customer_id);
CREATE INDEX IF NOT EXISTS idx_pix_transfers_status ON pix_transfers(status);
CREATE INDEX IF NOT EXISTS idx_pix_transfers_created ON pix_transfers(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pix_transfers_scheduled ON pix_transfers(scheduled_for)
    WHERE scheduled_for IS NOT NULL AND status = 'pending';
CREATE INDEX IF NOT EXISTS idx_pix_transfers_idempotency ON pix_transfers(idempotency_key);
-- ============================================================
-- 5. SCHEDULED TRANSFERS (TED/DOC/Agendamentos genéricos)
-- ============================================================

CREATE TABLE IF NOT EXISTS scheduled_transfers (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,
    source_account_id UUID NOT NULL REFERENCES accounts(id),
    source_customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id),
    transfer_type TEXT NOT NULL
        CHECK (transfer_type IN ('pix', 'ted', 'doc', 'internal')),
    -- Destino
    destination_bank_code TEXT NOT NULL,
    destination_branch TEXT NOT NULL,
    destination_account TEXT NOT NULL,
    destination_account_type TEXT NOT NULL DEFAULT 'checking'
        CHECK (destination_account_type IN ('checking', 'savings', 'payment')),
    destination_name TEXT NOT NULL,
    destination_document TEXT NOT NULL,
    amount NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL DEFAULT 'BRL',
    description TEXT DEFAULT '',
    -- Recorrência
    schedule_type TEXT NOT NULL DEFAULT 'once'
        CHECK (schedule_type IN ('once', 'daily', 'weekly', 'biweekly', 'monthly')),
    scheduled_date DATE NOT NULL,
    recurrence_end_date DATE,
    next_execution_date DATE,
    recurrence_count INTEGER DEFAULT 0,      -- quantas vezes já executou
    max_recurrences INTEGER,                 -- limite (NULL = infinito)
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'processing', 'completed', 'failed', 'cancelled', 'paused')),
    failure_reason TEXT,
    initiated_by UUID REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    requires_approval BOOLEAN DEFAULT FALSE,
    last_executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_scheduled_transfers_customer ON scheduled_transfers(source_customer_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_transfers_next ON scheduled_transfers(next_execution_date)
    WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_scheduled_transfers_status ON scheduled_transfers(status);
-- ============================================================
-- 6. CREDIT CARDS PJ
-- ============================================================

CREATE TABLE IF NOT EXISTS credit_cards (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES accounts(id),
    -- Dados do cartão (mascarados)
    card_number_last4 TEXT NOT NULL,
    card_holder_name TEXT NOT NULL,
    card_brand TEXT NOT NULL DEFAULT 'Visa'
        CHECK (card_brand IN ('Visa', 'Mastercard', 'Elo', 'Amex')),
    card_type TEXT NOT NULL DEFAULT 'corporate'
        CHECK (card_type IN ('corporate', 'virtual', 'additional')),
    -- Limites
    credit_limit NUMERIC(15,2) NOT NULL DEFAULT 0,
    available_limit NUMERIC(15,2) NOT NULL DEFAULT 0,
    used_limit NUMERIC(15,2) NOT NULL DEFAULT 0,
    -- Fatura
    billing_day INTEGER NOT NULL DEFAULT 10 CHECK (billing_day BETWEEN 1 AND 28),
    due_day INTEGER NOT NULL DEFAULT 20 CHECK (due_day BETWEEN 1 AND 28),
    -- Status
    status TEXT NOT NULL DEFAULT 'pending_activation'
        CHECK (status IN ('pending_activation', 'active', 'blocked', 'cancelled', 'expired')),
    blocked_reason TEXT,
    -- PIX com cartão de crédito
    pix_credit_enabled BOOLEAN DEFAULT FALSE,
    pix_credit_limit NUMERIC(15,2) DEFAULT 0,
    pix_credit_used NUMERIC(15,2) DEFAULT 0,
    -- Controle
    is_contactless_enabled BOOLEAN DEFAULT TRUE,
    is_international_enabled BOOLEAN DEFAULT FALSE,
    is_online_enabled BOOLEAN DEFAULT TRUE,
    daily_limit NUMERIC(15,2) DEFAULT 10000.00,
    single_transaction_limit NUMERIC(15,2) DEFAULT 5000.00,
    -- Meta
    issued_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    requested_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_credit_cards_customer ON credit_cards(customer_id);
CREATE INDEX IF NOT EXISTS idx_credit_cards_account ON credit_cards(account_id);
CREATE INDEX IF NOT EXISTS idx_credit_cards_status ON credit_cards(status);
-- Transações do cartão de crédito
CREATE TABLE IF NOT EXISTS credit_card_transactions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    card_id UUID NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id),
    transaction_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    posting_date TIMESTAMPTZ,                -- data de lançamento na fatura
    amount NUMERIC(15,2) NOT NULL,
    original_amount NUMERIC(15,2),           -- valor original (se compra internacional)
    original_currency TEXT DEFAULT 'BRL',
    merchant_name TEXT NOT NULL,
    merchant_category_code TEXT,             -- MCC
    category TEXT NOT NULL DEFAULT 'other'
        CHECK (category IN (
            'food', 'transport', 'fuel', 'office_supplies', 'technology',
            'travel', 'subscription', 'marketing', 'utilities', 'insurance',
            'maintenance', 'professional_services', 'tax', 'other'
        )),
    installments INTEGER DEFAULT 1,
    current_installment INTEGER DEFAULT 1,
    installment_amount NUMERIC(15,2),
    transaction_type TEXT NOT NULL DEFAULT 'purchase'
        CHECK (transaction_type IN ('purchase', 'pix_credit', 'annual_fee', 'interest',
                                     'insurance', 'refund', 'chargeback', 'payment')),
    status TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (status IN ('pending', 'confirmed', 'cancelled', 'disputed', 'refunded')),
    description TEXT DEFAULT '',
    is_international BOOLEAN DEFAULT FALSE,
    authorization_code TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cc_transactions_card ON credit_card_transactions(card_id);
CREATE INDEX IF NOT EXISTS idx_cc_transactions_customer ON credit_card_transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_cc_transactions_date ON credit_card_transactions(transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_cc_transactions_category ON credit_card_transactions(category);
-- Faturas do cartão de crédito
CREATE TABLE IF NOT EXISTS credit_card_invoices (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    card_id UUID NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id),
    reference_month TEXT NOT NULL,            -- '2026-02'
    open_date DATE NOT NULL,
    close_date DATE NOT NULL,
    due_date DATE NOT NULL,
    total_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    minimum_payment NUMERIC(15,2) NOT NULL DEFAULT 0,
    previous_balance NUMERIC(15,2) DEFAULT 0,
    payments_received NUMERIC(15,2) DEFAULT 0,
    interest_amount NUMERIC(15,2) DEFAULT 0,
    fine_amount NUMERIC(15,2) DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'closed', 'paid', 'partially_paid', 'overdue')),
    paid_at TIMESTAMPTZ,
    paid_amount NUMERIC(15,2),
    barcode TEXT,                             -- código de barras do boleto da fatura
    digitable_line TEXT,                     -- linha digitável
    pdf_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(card_id, reference_month)
);
CREATE INDEX IF NOT EXISTS idx_cc_invoices_card ON credit_card_invoices(card_id);
CREATE INDEX IF NOT EXISTS idx_cc_invoices_customer ON credit_card_invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_cc_invoices_due ON credit_card_invoices(due_date);
CREATE INDEX IF NOT EXISTS idx_cc_invoices_status ON credit_card_invoices(status);
-- ============================================================
-- 7. BILL PAYMENTS (Pagamento de Contas / Boletos)
-- ============================================================

CREATE TABLE IF NOT EXISTS bill_payments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id),
    account_id UUID NOT NULL REFERENCES accounts(id),
    -- Input do boleto
    input_method TEXT NOT NULL DEFAULT 'typed'
        CHECK (input_method IN ('typed', 'pasted', 'camera_scan', 'file_upload')),
    barcode TEXT,                             -- código de barras (44 dígitos)
    digitable_line TEXT,                      -- linha digitável (47 ou 48 dígitos)
    barcode_raw_image_url TEXT,              -- URL da imagem original (se escaneou)
    -- Dados extraídos/validados do boleto
    bill_type TEXT NOT NULL DEFAULT 'bank_slip'
        CHECK (bill_type IN ('bank_slip', 'utility', 'tax_slip', 'government')),
    -- bank_slip = boleto bancário (47 dígitos)
    -- utility = concessionária (48 dígitos)
    -- tax_slip = guia de imposto (DARF, GPS, etc.)
    -- government = GRU, GNRE
    beneficiary_name TEXT,
    beneficiary_document TEXT,               -- CNPJ do cedente
    beneficiary_bank_code TEXT,
    payer_name TEXT,
    payer_document TEXT,
    -- Valores
    original_amount NUMERIC(15,2),           -- valor original do boleto
    discount_amount NUMERIC(15,2) DEFAULT 0,
    interest_amount NUMERIC(15,2) DEFAULT 0,
    fine_amount NUMERIC(15,2) DEFAULT 0,
    final_amount NUMERIC(15,2) NOT NULL,     -- valor efetivamente pago
    currency TEXT NOT NULL DEFAULT 'BRL',
    -- Datas
    due_date DATE,
    payment_date DATE,
    scheduled_date DATE,                     -- se agendado
    settlement_date DATE,                    -- data de liquidação
    -- Status
    status TEXT NOT NULL DEFAULT 'pending_validation'
        CHECK (status IN (
            'pending_validation',  -- validando código de barras
            'validated',           -- boleto validado, aguardando confirmação
            'pending',             -- confirmado, aguardando processamento
            'processing',          -- em processamento
            'scheduled',           -- agendado para data futura
            'completed',           -- pago com sucesso
            'failed',              -- falhou
            'cancelled',           -- cancelado pelo usuário
            'expired'              -- boleto vencido / não pago
        )),
    failure_reason TEXT,
    -- Controle
    initiated_by UUID REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    requires_approval BOOLEAN DEFAULT FALSE,
    ip_address INET,
    device_id TEXT,
    receipt_url TEXT,                         -- comprovante em PDF
    provider_reference TEXT,                 -- referência do provider externo
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bill_payments_customer ON bill_payments(customer_id);
CREATE INDEX IF NOT EXISTS idx_bill_payments_status ON bill_payments(status);
CREATE INDEX IF NOT EXISTS idx_bill_payments_scheduled ON bill_payments(scheduled_date)
    WHERE scheduled_date IS NOT NULL AND status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_bill_payments_barcode ON bill_payments(barcode);
CREATE INDEX IF NOT EXISTS idx_bill_payments_digitable ON bill_payments(digitable_line);
-- ============================================================
-- 8. DEBIT PURCHASES (Compras no Débito)
-- ============================================================

CREATE TABLE IF NOT EXISTS debit_purchases (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id),
    account_id UUID NOT NULL REFERENCES accounts(id),
    transaction_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    amount NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    merchant_name TEXT NOT NULL,
    merchant_category_code TEXT,             -- MCC
    category TEXT NOT NULL DEFAULT 'other'
        CHECK (category IN (
            'food', 'transport', 'fuel', 'office_supplies', 'technology',
            'travel', 'subscription', 'marketing', 'utilities', 'insurance',
            'maintenance', 'professional_services', 'tax', 'other'
        )),
    description TEXT DEFAULT '',
    card_last4 TEXT,                          -- últimos 4 do cartão de débito
    authorization_code TEXT,
    terminal_id TEXT,
    status TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (status IN ('pending', 'confirmed', 'cancelled', 'disputed', 'refunded')),
    is_contactless BOOLEAN DEFAULT FALSE,
    ip_address INET,
    device_id TEXT,
    location_lat NUMERIC(10,7),
    location_lng NUMERIC(10,7),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_debit_purchases_customer ON debit_purchases(customer_id);
CREATE INDEX IF NOT EXISTS idx_debit_purchases_account ON debit_purchases(account_id);
CREATE INDEX IF NOT EXISTS idx_debit_purchases_date ON debit_purchases(transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_debit_purchases_category ON debit_purchases(category);
-- ============================================================
-- 9. SPENDING ANALYTICS (Análise de Gastos)
-- ============================================================
-- Tabela materializada / cache para analytics rápido

CREATE TABLE IF NOT EXISTS spending_summaries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    account_id UUID REFERENCES accounts(id),
    period_type TEXT NOT NULL
        CHECK (period_type IN ('daily', 'weekly', 'monthly', 'yearly')),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    -- Totais
    total_income NUMERIC(15,2) DEFAULT 0,
    total_expenses NUMERIC(15,2) DEFAULT 0,
    net_cashflow NUMERIC(15,2) DEFAULT 0,
    -- Contagens
    transaction_count INTEGER DEFAULT 0,
    income_count INTEGER DEFAULT 0,
    expense_count INTEGER DEFAULT 0,
    -- Médias
    avg_income NUMERIC(15,2) DEFAULT 0,
    avg_expense NUMERIC(15,2) DEFAULT 0,
    largest_income NUMERIC(15,2) DEFAULT 0,
    largest_expense NUMERIC(15,2) DEFAULT 0,
    -- Breakdown por categoria (JSONB para flexibilidade)
    category_breakdown JSONB DEFAULT '{}',
    -- {"food": {"total": 1200.50, "count": 15, "pct": 12.5}, ...}
    -- PIX stats
    pix_sent_total NUMERIC(15,2) DEFAULT 0,
    pix_sent_count INTEGER DEFAULT 0,
    pix_received_total NUMERIC(15,2) DEFAULT 0,
    pix_received_count INTEGER DEFAULT 0,
    -- Cartão
    credit_card_total NUMERIC(15,2) DEFAULT 0,
    debit_card_total NUMERIC(15,2) DEFAULT 0,
    -- Boletos
    bills_paid_total NUMERIC(15,2) DEFAULT 0,
    bills_paid_count INTEGER DEFAULT 0,
    -- Comparação com período anterior
    income_variation_pct NUMERIC(8,2) DEFAULT 0,   -- +5.2% ou -3.1%
    expense_variation_pct NUMERIC(8,2) DEFAULT 0,
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(customer_id, account_id, period_type, period_start)
);
CREATE INDEX IF NOT EXISTS idx_spending_summaries_customer ON spending_summaries(customer_id);
CREATE INDEX IF NOT EXISTS idx_spending_summaries_period ON spending_summaries(period_type, period_start);
-- Budget / Orçamentos por categoria
CREATE TABLE IF NOT EXISTS spending_budgets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    monthly_limit NUMERIC(15,2) NOT NULL,
    alert_threshold_pct NUMERIC(5,2) DEFAULT 80.00, -- alerta quando atingir 80%
    is_active BOOLEAN DEFAULT TRUE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(customer_id, category)
);
CREATE INDEX IF NOT EXISTS idx_spending_budgets_customer ON spending_budgets(customer_id);
-- ============================================================
-- 10. FAVORITES / CONTACTS (Contatos frequentes para PIX/TED)
-- ============================================================

CREATE TABLE IF NOT EXISTS favorites (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    nickname TEXT NOT NULL,
    -- Destino
    destination_type TEXT NOT NULL DEFAULT 'pix'
        CHECK (destination_type IN ('pix', 'ted', 'doc', 'bill')),
    pix_key_type TEXT
        CHECK (pix_key_type IN ('cpf', 'cnpj', 'email', 'phone', 'random', NULL)),
    pix_key_value TEXT,
    bank_code TEXT,
    branch TEXT,
    account_number TEXT,
    account_type TEXT
        CHECK (account_type IN ('checking', 'savings', 'payment', NULL)),
    recipient_name TEXT NOT NULL,
    recipient_document TEXT,                  -- CPF/CNPJ
    is_frequent BOOLEAN DEFAULT FALSE,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_favorites_customer ON favorites(customer_id);
CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);
-- ============================================================
-- 11. NOTIFICATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS notifications (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    customer_id TEXT REFERENCES customer_profiles(customer_id),
    type TEXT NOT NULL
        CHECK (type IN (
            'pix_sent', 'pix_received',
            'transfer_scheduled', 'transfer_executed', 'transfer_failed',
            'bill_due', 'bill_paid', 'bill_failed',
            'card_purchase', 'card_invoice_available', 'card_invoice_due',
            'card_limit_alert', 'card_approved', 'card_blocked',
            'budget_alert', 'budget_exceeded',
            'balance_low',
            'security_alert', 'login_alert',
            'general'
        )),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    data JSONB DEFAULT '{}',                 -- payload adicional
    channel TEXT NOT NULL DEFAULT 'push'
        CHECK (channel IN ('push', 'email', 'sms', 'in_app')),
    priority TEXT NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id, is_read)
    WHERE is_read = FALSE;
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);
-- ============================================================
-- 12. AUDIT LOG (Registro de Auditoria)
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    customer_id TEXT REFERENCES customer_profiles(customer_id),
    action TEXT NOT NULL,
    -- ex: 'pix.create', 'pix.approve', 'card.request', 'bill.pay', 'login', 'login.failed'
    resource_type TEXT NOT NULL,              -- 'pix_transfer', 'credit_card', 'bill_payment', etc.
    resource_id TEXT,                         -- UUID do recurso afetado
    details JSONB DEFAULT '{}',              -- dados adicionais
    ip_address INET,
    user_agent TEXT,
    device_id TEXT,
    status TEXT NOT NULL DEFAULT 'success'
        CHECK (status IN ('success', 'failure', 'denied')),
    risk_score NUMERIC(5,2),                 -- 0-100 score de risco
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_customer ON audit_log(customer_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at DESC);
-- Particionar por mês seria ideal em produção

-- ============================================================
-- 13. DEVICE REGISTRY (Dispositivos autorizados)
-- ============================================================

CREATE TABLE IF NOT EXISTS user_devices (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    device_name TEXT,
    device_model TEXT,
    os TEXT,
    os_version TEXT,
    app_version TEXT,
    push_token TEXT,                          -- FCM/APNs token
    is_trusted BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    registered_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, device_id)
);
CREATE INDEX IF NOT EXISTS idx_user_devices_user ON user_devices(user_id);
-- ============================================================
-- 14. TRANSACTION LIMITS (Limites transacionais)
-- ============================================================

CREATE TABLE IF NOT EXISTS transaction_limits (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    account_id UUID REFERENCES accounts(id),
    transaction_type TEXT NOT NULL
        CHECK (transaction_type IN ('pix', 'ted', 'doc', 'bill_payment', 'debit_purchase', 'credit_purchase')),
    -- Limites
    daily_limit NUMERIC(15,2) NOT NULL,
    daily_used NUMERIC(15,2) DEFAULT 0,
    monthly_limit NUMERIC(15,2) NOT NULL,
    monthly_used NUMERIC(15,2) DEFAULT 0,
    single_limit NUMERIC(15,2) NOT NULL,     -- limite por transação
    -- Horário noturno (20h-6h) pode ter limite diferente
    nightly_single_limit NUMERIC(15,2),
    nightly_daily_limit NUMERIC(15,2),
    -- Controle
    last_reset_daily TIMESTAMPTZ DEFAULT NOW(),
    last_reset_monthly TIMESTAMPTZ DEFAULT NOW(),
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(customer_id, transaction_type)
);
CREATE INDEX IF NOT EXISTS idx_transaction_limits_customer ON transaction_limits(customer_id);
-- ============================================================
-- 15. BARCODE VALIDATION CACHE
-- ============================================================
-- Cache de validações de código de barras para evitar reprocessamento

CREATE TABLE IF NOT EXISTS barcode_validations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    barcode TEXT,
    digitable_line TEXT,
    bill_type TEXT,
    is_valid BOOLEAN NOT NULL,
    -- Dados extraídos
    bank_code TEXT,
    amount NUMERIC(15,2),
    due_date DATE,
    beneficiary_name TEXT,
    beneficiary_document TEXT,
    -- Erros
    validation_errors JSONB DEFAULT '[]',
    -- Provider
    validated_by TEXT DEFAULT 'internal',     -- 'internal', 'kobana', 'bank_api'
    provider_response JSONB DEFAULT '{}',
    -- Cache control
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours'),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_barcode_validations_barcode ON barcode_validations(barcode);
CREATE INDEX IF NOT EXISTS idx_barcode_validations_digitable ON barcode_validations(digitable_line);
-- ============================================================
-- 16. UPDATED_AT TRIGGERS
-- ============================================================

-- Reuse the update_updated_at() function from migration 001

CREATE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_user_companies_updated_at
    BEFORE UPDATE ON user_companies FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_accounts_updated_at
    BEFORE UPDATE ON accounts FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_pix_keys_updated_at
    BEFORE UPDATE ON pix_keys FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_pix_transfers_updated_at
    BEFORE UPDATE ON pix_transfers FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_scheduled_transfers_updated_at
    BEFORE UPDATE ON scheduled_transfers FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_credit_cards_updated_at
    BEFORE UPDATE ON credit_cards FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_cc_invoices_updated_at
    BEFORE UPDATE ON credit_card_invoices FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_bill_payments_updated_at
    BEFORE UPDATE ON bill_payments FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_spending_summaries_updated_at
    BEFORE UPDATE ON spending_summaries FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_spending_budgets_updated_at
    BEFORE UPDATE ON spending_budgets FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_favorites_updated_at
    BEFORE UPDATE ON favorites FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_transaction_limits_updated_at
    BEFORE UPDATE ON transaction_limits FOR EACH ROW EXECUTE FUNCTION update_updated_at();
-- ============================================================
-- 17. ROW LEVEL SECURITY (RLS) for new tables
-- ============================================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE pix_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE pix_transfers ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_transfers ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_card_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_card_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE bill_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE debit_purchases ENABLE ROW LEVEL SECURITY;
ALTER TABLE spending_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE spending_budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE favorites ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE transaction_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE barcode_validations ENABLE ROW LEVEL SECURITY;
-- Service role full access (backend BFA usa service_role key)
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'users', 'user_companies', 'accounts', 'pix_keys',
            'pix_transfers', 'scheduled_transfers',
            'credit_cards', 'credit_card_transactions', 'credit_card_invoices',
            'bill_payments', 'debit_purchases',
            'spending_summaries', 'spending_budgets',
            'favorites', 'notifications', 'audit_log',
            'user_devices', 'transaction_limits', 'barcode_validations'
        ])
    LOOP
        EXECUTE format(
            'CREATE POLICY "Service role full access %s" ON %I FOR ALL USING (auth.role() = ''service_role'')',
            tbl, tbl
        );
    END LOOP;
END $$;
-- Authenticated users can read their own data
CREATE POLICY "Users read own profile"
    ON users FOR SELECT
    USING (auth.uid() = id);
CREATE POLICY "Users update own profile"
    ON users FOR UPDATE
    USING (auth.uid() = id);
CREATE POLICY "Users read own companies"
    ON user_companies FOR SELECT
    USING (auth.uid() = user_id);
CREATE POLICY "Users read own notifications"
    ON notifications FOR SELECT
    USING (auth.uid() = user_id);
CREATE POLICY "Users update own notifications"
    ON notifications FOR UPDATE
    USING (auth.uid() = user_id);
CREATE POLICY "Users read own devices"
    ON user_devices FOR SELECT
    USING (auth.uid() = user_id);
-- ============================================================
-- 18. SEED DATA for new tables
-- ============================================================

-- Account for each customer
INSERT INTO accounts (customer_id, account_type, branch, account_number, digit, balance, available_balance, overdraft_limit)
VALUES
    ('cust-001', 'checking', '0001', '12345', '6', 485200.00, 485200.00, 50000.00),
    ('cust-002', 'checking', '0001', '67890', '1', 42700.00, 42700.00, 10000.00),
    ('cust-003', 'checking', '0001', '11111', '0', 2350000.00, 2350000.00, 200000.00),
    ('cust-004', 'checking', '0001', '22222', '3', 2000.00, 2000.00, 0.00),
    ('cust-005', 'checking', '0001', '33333', '7', 920000.00, 920000.00, 80000.00)
ON CONFLICT (branch, account_number, digit) DO NOTHING;
-- PIX keys
INSERT INTO pix_keys (account_id, customer_id, key_type, key_value, status)
SELECT a.id, a.customer_id, 'cnpj', cp.document, 'active'
FROM accounts a
JOIN customer_profiles cp ON cp.customer_id = a.customer_id
ON CONFLICT (key_value) DO NOTHING;
-- Transaction limits for each customer
INSERT INTO transaction_limits (customer_id, transaction_type, daily_limit, monthly_limit, single_limit, nightly_single_limit, nightly_daily_limit)
VALUES
    ('cust-001', 'pix',          100000.00,  2000000.00,  50000.00,  10000.00,  50000.00),
    ('cust-001', 'ted',          200000.00,  5000000.00,  100000.00, NULL,       NULL),
    ('cust-001', 'bill_payment', 500000.00,  5000000.00,  200000.00, NULL,       NULL),
    ('cust-002', 'pix',          20000.00,   400000.00,   10000.00,  3000.00,    10000.00),
    ('cust-002', 'ted',          50000.00,   500000.00,   25000.00,  NULL,       NULL),
    ('cust-002', 'bill_payment', 50000.00,   500000.00,   30000.00,  NULL,       NULL),
    ('cust-003', 'pix',          500000.00,  10000000.00, 200000.00, 50000.00,   200000.00),
    ('cust-003', 'ted',          1000000.00, 20000000.00, 500000.00, NULL,       NULL),
    ('cust-003', 'bill_payment', 1000000.00, 20000000.00, 500000.00, NULL,       NULL),
    ('cust-004', 'pix',          5000.00,    50000.00,    2000.00,   1000.00,    3000.00),
    ('cust-004', 'ted',          10000.00,   100000.00,   5000.00,   NULL,       NULL),
    ('cust-004', 'bill_payment', 10000.00,   100000.00,   5000.00,   NULL,       NULL),
    ('cust-005', 'pix',          200000.00,  4000000.00,  100000.00, 20000.00,   80000.00),
    ('cust-005', 'ted',          500000.00,  10000000.00, 250000.00, NULL,       NULL),
    ('cust-005', 'bill_payment', 500000.00,  10000000.00, 300000.00, NULL,       NULL)
ON CONFLICT (customer_id, transaction_type) DO NOTHING;
-- Credit card for cust-001 (active) and cust-003 (active)
INSERT INTO credit_cards (customer_id, account_id, card_number_last4, card_holder_name, card_brand, card_type,
    credit_limit, available_limit, used_limit, billing_day, due_day, status,
    pix_credit_enabled, pix_credit_limit, issued_at, expires_at)
SELECT
    'cust-001', a.id, '4532', 'TECHSOLUTIONS LTDA', 'Visa', 'corporate',
    80000.00, 65000.00, 15000.00, 10, 20, 'active',
    TRUE, 20000.00, NOW() - INTERVAL '1 year', NOW() + INTERVAL '3 years'
FROM accounts a WHERE a.customer_id = 'cust-001'
ON CONFLICT DO NOTHING;
INSERT INTO credit_cards (customer_id, account_id, card_number_last4, card_holder_name, card_brand, card_type,
    credit_limit, available_limit, used_limit, billing_day, due_day, status,
    pix_credit_enabled, pix_credit_limit, issued_at, expires_at)
SELECT
    'cust-003', a.id, '5412', 'GLOBAL IMPORTACOES SA', 'Mastercard', 'corporate',
    500000.00, 420000.00, 80000.00, 5, 15, 'active',
    TRUE, 100000.00, NOW() - INTERVAL '2 years', NOW() + INTERVAL '2 years'
FROM accounts a WHERE a.customer_id = 'cust-003'
ON CONFLICT DO NOTHING;
-- Spending budgets for cust-001
INSERT INTO spending_budgets (customer_id, category, monthly_limit, alert_threshold_pct)
VALUES
    ('cust-001', 'payroll',   50000.00, 90.00),
    ('cust-001', 'marketing', 25000.00, 80.00),
    ('cust-001', 'supplier',  30000.00, 85.00),
    ('cust-001', 'utilities', 8000.00,  75.00),
    ('cust-001', 'tax',       15000.00, 95.00)
ON CONFLICT (customer_id, category) DO NOTHING;
-- Sample PIX transfers
INSERT INTO pix_transfers (idempotency_key, source_account_id, source_customer_id,
    destination_key_type, destination_key_value, destination_name, destination_document,
    amount, description, status, funded_by, executed_at)
SELECT
    'pix-seed-001', a.id, 'cust-001',
    'cnpj', '98.765.432/0001-10', 'Padaria Pão Dourado ME', '98.765.432/0001-10',
    1500.00, 'Pagamento coffee break reunião', 'completed', 'balance', NOW() - INTERVAL '5 days'
FROM accounts a WHERE a.customer_id = 'cust-001'
ON CONFLICT (idempotency_key) DO NOTHING;
INSERT INTO pix_transfers (idempotency_key, source_account_id, source_customer_id,
    destination_key_type, destination_key_value, destination_name, destination_document,
    amount, description, status, funded_by, credit_card_id, credit_card_installments, executed_at)
SELECT
    'pix-seed-002', a.id, 'cust-001',
    'email', 'fornecedor@cloud.com', 'CloudHost Serviços', '44.555.666/0001-77',
    12000.00, 'Infraestrutura cloud anual', 'completed', 'credit_card',
    cc.id, 3, NOW() - INTERVAL '2 days'
FROM accounts a
JOIN credit_cards cc ON cc.customer_id = 'cust-001'
WHERE a.customer_id = 'cust-001'
ON CONFLICT (idempotency_key) DO NOTHING;
-- Sample bill payment
INSERT INTO bill_payments (idempotency_key, customer_id, account_id,
    input_method, digitable_line, bill_type,
    beneficiary_name, beneficiary_document,
    original_amount, final_amount, due_date, payment_date,
    status)
SELECT
    'bill-seed-001', 'cust-001', a.id,
    'typed', '23793.38128 60000.000003 00000.000400 1 84340000012500',
    'bank_slip',
    'Locadora Escritórios SA', '22.333.444/0001-55',
    3500.00, 3500.00, CURRENT_DATE + 5, CURRENT_DATE,
    'completed'
FROM accounts a WHERE a.customer_id = 'cust-001'
ON CONFLICT (idempotency_key) DO NOTHING;
-- ============================================================
-- 19. HELPER FUNCTIONS
-- ============================================================

-- Validar formato de linha digitável de boleto bancário (47 dígitos)
CREATE OR REPLACE FUNCTION validate_bank_slip_line(line TEXT)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    clean_line TEXT;
    result JSONB;
BEGIN
    -- Remove pontos, espaços
    clean_line := regexp_replace(line, '[^0-9]', '', 'g');

    IF length(clean_line) = 47 THEN
        result := jsonb_build_object(
            'is_valid', TRUE,
            'type', 'bank_slip',
            'digits', 47,
            'bank_code', substring(clean_line from 1 for 3),
            'currency_code', substring(clean_line from 4 for 1),
            'amount_raw', substring(clean_line from 38 for 10),
            'due_factor', substring(clean_line from 34 for 4)
        );
    ELSIF length(clean_line) = 48 THEN
        result := jsonb_build_object(
            'is_valid', TRUE,
            'type', 'utility',
            'digits', 48,
            'segment_id', substring(clean_line from 1 for 1),
            'amount_raw', substring(clean_line from 5 for 11)
        );
    ELSE
        result := jsonb_build_object(
            'is_valid', FALSE,
            'type', 'unknown',
            'digits', length(clean_line),
            'error', 'Linha digitável deve ter 47 (boleto) ou 48 (concessionária) dígitos'
        );
    END IF;

    RETURN result;
END;
$$;
-- Função para calcular resumo de gastos de um período
CREATE OR REPLACE FUNCTION compute_spending_summary(
    p_customer_id TEXT,
    p_period_start DATE,
    p_period_end DATE
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total_income', COALESCE(SUM(CASE WHEN type = 'credit' THEN amount ELSE 0 END), 0),
        'total_expenses', COALESCE(SUM(CASE WHEN type = 'debit' THEN ABS(amount) ELSE 0 END), 0),
        'net_cashflow', COALESCE(SUM(amount), 0),
        'transaction_count', COUNT(*),
        'income_count', COUNT(*) FILTER (WHERE type = 'credit'),
        'expense_count', COUNT(*) FILTER (WHERE type = 'debit'),
        'avg_income', COALESCE(AVG(amount) FILTER (WHERE type = 'credit'), 0),
        'avg_expense', COALESCE(AVG(ABS(amount)) FILTER (WHERE type = 'debit'), 0),
        'largest_income', COALESCE(MAX(amount) FILTER (WHERE type = 'credit'), 0),
        'largest_expense', COALESCE(MAX(ABS(amount)) FILTER (WHERE type = 'debit'), 0),
        'category_breakdown', COALESCE(
            (SELECT jsonb_object_agg(category, jsonb_build_object(
                'total', cat_total, 'count', cat_count
            ))
            FROM (
                SELECT category, SUM(ABS(amount)) as cat_total, COUNT(*) as cat_count
                FROM customer_transactions
                WHERE customer_id = p_customer_id
                AND date >= p_period_start AND date < p_period_end
                AND type = 'debit'
                GROUP BY category
            ) cats), '{}'::jsonb
        )
    ) INTO result
    FROM customer_transactions
    WHERE customer_id = p_customer_id
    AND date >= p_period_start AND date < p_period_end;

    RETURN COALESCE(result, '{}'::jsonb);
END;
$$;
