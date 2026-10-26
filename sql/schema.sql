-- =============================================================================
-- ApexMarket: Empirical Multi-Provider Inference Arbitrage & Verified Escrow Settlement Engine
-- Master PostgreSQL Schema Definition (v3.0 Blueprint)
-- All financial balances are strictly tracked in BIGINT micro-dollars ($1.00 = 1,000,000 micros)
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -----------------------------------------------------------------------------
-- ENUM TYPES
-- -----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE workload_sensitivity AS ENUM ('PUBLIC', 'SYNTHETIC', 'CONFIDENTIAL');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE node_trust_tier AS ENUM ('ANCHOR', 'VERIFIED_PROVIDER', 'PROBATION_SPOT');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE job_status AS ENUM ('QUEUED', 'RUNNING', 'COMPLETED', 'PARTIAL_FAIL', 'ABORTED_BUDGET');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE shred_status AS ENUM ('PENDING', 'RUNNING', 'VERIFIED_PASS', 'VERIFIED_FAIL_REROUTED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE payout_batch_status AS ENUM ('CREATED', 'SUBMITTED_PENDING', 'COMPLETED', 'FAILED_REVERSED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- -----------------------------------------------------------------------------
-- 1. CLIENTS & API AUTHENTICATION
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clients (
    client_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_name TEXT NOT NULL,
    api_key_hash TEXT NOT NULL UNIQUE,
    paypal_payer_id TEXT,
    paypal_vault_id TEXT,
    available_balance_micros BIGINT NOT NULL DEFAULT 0 CHECK (available_balance_micros >= 0),
    locked_escrow_micros BIGINT NOT NULL DEFAULT 0 CHECK (locked_escrow_micros >= 0),
    hourly_spend_limit_micros BIGINT NOT NULL DEFAULT 50000000 CHECK (hourly_spend_limit_micros >= 0), -- Default $50/hr
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clients_api_key_hash ON clients(api_key_hash);

-- -----------------------------------------------------------------------------
-- 2. COMPUTE NODES REGISTRY
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compute_nodes (
    node_id TEXT PRIMARY KEY,
    provider_name TEXT NOT NULL,
    endpoint_url TEXT NOT NULL,
    model_id TEXT NOT NULL,
    trust_tier node_trust_tier NOT NULL DEFAULT 'PROBATION_SPOT',
    paypal_receiver_email TEXT NOT NULL,
    input_price_per_1m_micros BIGINT NOT NULL CHECK (input_price_per_1m_micros >= 0),
    output_price_per_1m_micros BIGINT NOT NULL CHECK (output_price_per_1m_micros >= 0),
    max_concurrent_requests INT NOT NULL DEFAULT 10 CHECK (max_concurrent_requests > 0),
    pending_probation_micros BIGINT NOT NULL DEFAULT 0 CHECK (pending_probation_micros >= 0),
    withdrawable_micros BIGINT NOT NULL DEFAULT 0 CHECK (withdrawable_micros >= 0),
    payout_pending_micros BIGINT NOT NULL DEFAULT 0 CHECK (payout_pending_micros >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_compute_nodes_active_withdrawable ON compute_nodes(is_active, withdrawable_micros);
CREATE INDEX IF NOT EXISTS idx_compute_nodes_trust_tier ON compute_nodes(trust_tier);

-- -----------------------------------------------------------------------------
-- 3. BATCH JOBS
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS batch_jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(client_id),
    sensitivity workload_sensitivity NOT NULL DEFAULT 'CONFIDENTIAL',
    status job_status NOT NULL DEFAULT 'QUEUED',
    total_prompts INT NOT NULL CHECK (total_prompts BETWEEN 1 AND 5000),
    max_tokens_per_prompt INT NOT NULL CHECK (max_tokens_per_prompt BETWEEN 1 AND 4096),
    max_cost_ceiling_micros BIGINT NOT NULL CHECK (max_cost_ceiling_micros > 0),
    reserved_escrow_micros BIGINT NOT NULL DEFAULT 0 CHECK (reserved_escrow_micros >= 0),
    actual_settled_cost_micros BIGINT NOT NULL DEFAULT 0 CHECK (actual_settled_cost_micros >= 0),
    platform_fee_micros BIGINT NOT NULL DEFAULT 0 CHECK (platform_fee_micros >= 0), -- 10% of net savings take-rate
    baseline_anchor_cost_micros BIGINT NOT NULL DEFAULT 0 CHECK (baseline_anchor_cost_micros >= 0),
    baseline_batch_api_cost_micros BIGINT NOT NULL DEFAULT 0 CHECK (baseline_batch_api_cost_micros >= 0),
    total_makespan_ms DOUBLE PRECISION,
    results_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_batch_jobs_client_status ON batch_jobs(client_id, status);
CREATE INDEX IF NOT EXISTS idx_batch_jobs_created_at ON batch_jobs(created_at DESC);

-- -----------------------------------------------------------------------------
-- 4. JOB SHREDS & PER-SHRED ATTESTATION
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_shreds (
    shred_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES batch_jobs(job_id) ON DELETE CASCADE,
    node_id TEXT NOT NULL REFERENCES compute_nodes(node_id),
    status shred_status NOT NULL DEFAULT 'PENDING',
    prompt_indices INT[] NOT NULL,
    measured_input_tokens INT NOT NULL DEFAULT 0 CHECK (measured_input_tokens >= 0),
    measured_output_tokens INT NOT NULL DEFAULT 0 CHECK (measured_output_tokens >= 0),
    shred_cost_micros BIGINT NOT NULL DEFAULT 0 CHECK (shred_cost_micros >= 0),
    canary_pass_rate DOUBLE PRECISION,
    anchor_nll_score DOUBLE PRECISION,
    nemotron_judge_score DOUBLE PRECISION,
    server_hmac_attestation TEXT,
    retry_count INT NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_shreds_job_id ON job_shreds(job_id);
CREATE INDEX IF NOT EXISTS idx_job_shreds_node_id ON job_shreds(node_id);
CREATE INDEX IF NOT EXISTS idx_job_shreds_status ON job_shreds(status);

-- -----------------------------------------------------------------------------
-- 5. DOUBLE-ENTRY LEDGER ENTRIES
-- Foreign keys are checked at commit so escrow can be locked before the job row
-- is inserted in the same transaction.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ledger_entries (
    entry_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    idempotency_key TEXT NOT NULL UNIQUE,
    job_id UUID REFERENCES batch_jobs(job_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED,
    shred_id UUID REFERENCES job_shreds(shred_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED,
    debit_account TEXT NOT NULL,
    credit_account TEXT NOT NULL,
    amount_micros BIGINT NOT NULL CHECK (amount_micros > 0),
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_idempotency_key ON ledger_entries(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_job_id ON ledger_entries(job_id);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_debit ON ledger_entries(debit_account);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_credit ON ledger_entries(credit_account);

-- -----------------------------------------------------------------------------
-- 6. DETERMINISTIC PAYPAL PAYOUT BATCHES & ITEMS
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payout_batches (
    batch_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), -- Used directly as PayPal sender_batch_id
    paypal_batch_id TEXT UNIQUE,
    status payout_batch_status NOT NULL DEFAULT 'CREATED',
    total_amount_micros BIGINT NOT NULL CHECK (total_amount_micros > 0),
    total_fee_micros BIGINT NOT NULL DEFAULT 0 CHECK (total_fee_micros >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payout_items (
    item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), -- Used as sender_item_id
    batch_id UUID NOT NULL REFERENCES payout_batches(batch_id) ON DELETE CASCADE,
    node_id TEXT NOT NULL REFERENCES compute_nodes(node_id),
    amount_paid_micros BIGINT NOT NULL CHECK (amount_paid_micros >= 0), -- Rounded down to whole cents
    remainder_carried_micros BIGINT NOT NULL CHECK (remainder_carried_micros >= 0), -- Sub-cent remainder
    payout_receiver_email TEXT,
    paypal_item_id TEXT,
    item_status TEXT NOT NULL DEFAULT 'PENDING'
);

CREATE INDEX IF NOT EXISTS idx_payout_items_batch_id ON payout_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_payout_items_node_id ON payout_items(node_id);

-- -----------------------------------------------------------------------------
-- 7. PREPAID CLIENT TOP-UPS (PAYPAL ORDERS V2)
-- topup_id is our idempotency key with PayPal and the order's custom_id, so a
-- capture can only ever credit the client and amount recorded here.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paypal_topups (
    topup_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(client_id),
    paypal_order_id TEXT UNIQUE,
    paypal_capture_id TEXT UNIQUE,
    amount_micros BIGINT NOT NULL CHECK (amount_micros > 0),
    status TEXT NOT NULL DEFAULT 'CREATED' CHECK (status IN ('CREATED', 'CAPTURED', 'FAILED')),
    is_vaulted_charge BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    captured_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_paypal_topups_client_id ON paypal_topups(client_id);

-- Snapshot payout destinations so a retry never changes a reserved batch payload.
ALTER TABLE payout_items ADD COLUMN IF NOT EXISTS payout_receiver_email TEXT;

-- Durable job results storage to prevent in-memory volatility across restarts and workers.
ALTER TABLE batch_jobs ADD COLUMN IF NOT EXISTS results_payload JSONB;
