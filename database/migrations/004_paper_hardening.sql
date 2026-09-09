-- ============================================================
-- Migration: 004_paper_hardening
-- Description: Industrial-grade paper trading hardening —
--   idempotency keys + fill audit trail on paper_orders.
--   Online-safe: all columns nullable, IF NOT EXISTS guards.
-- ============================================================

-- New audit columns on paper_orders
ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS client_order_id TEXT;
ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS fill_source TEXT;
ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS estimated_costs DOUBLE PRECISION;
ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS filled_at TIMESTAMPTZ;

-- Idempotency: same (user, client_order_id) must never double-fill.
-- Partial unique index so NULL keys (legacy rows) are unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_orders_user_client
  ON paper_orders(user_id, client_order_id)
  WHERE client_order_id IS NOT NULL;

-- Fill-audit + status filtering for the order book API.
CREATE INDEX IF NOT EXISTS idx_paper_orders_user_status_time
  ON paper_orders(user_id, status, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_paper_orders_fill_source
  ON paper_orders(fill_source) WHERE fill_source IS NOT NULL;

-- Allow the PENDING -> FILLED lifecycle (CHECK constraints if present).
-- Status values: PENDING, FILLED, CANCELLED, REJECTED, EXPIRED.
-- No DDL needed for TEXT columns; documented here for RLS parity.

-- RLS: allow holders to update their own resting (PENDING) orders
-- (needed for cancel/fill transitions via service-role bypass otherwise).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'paper_orders_update_own') THEN
        CREATE POLICY paper_orders_update_own ON paper_orders FOR UPDATE USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'paper_orders_delete_own') THEN
        CREATE POLICY paper_orders_delete_own ON paper_orders FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;
