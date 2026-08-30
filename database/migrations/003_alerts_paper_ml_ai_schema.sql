-- ============================================================
-- Migration: 003_alerts_paper_ml_ai_schema
-- Description: Schema for Alert Rules, Alert History, Paper Trading
--              (Portfolios, Orders, Positions), ML Predictions, and AI Reports
-- ============================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Alert Rules Table
-- ============================================================
CREATE TABLE IF NOT EXISTS alert_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    condition TEXT NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    channel TEXT NOT NULL DEFAULT 'IN_APP',
    webhook_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_triggered TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_user_id ON alert_rules(user_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_symbol ON alert_rules(symbol);
CREATE INDEX IF NOT EXISTS idx_alert_rules_is_active ON alert_rules(is_active);

-- ============================================================
-- Alert History / Trigger Audit Log Table
-- ============================================================
CREATE TABLE IF NOT EXISTS alert_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id UUID REFERENCES alert_rules(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    alert_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    triggered_value DOUBLE PRECISION NOT NULL,
    threshold_value DOUBLE PRECISION NOT NULL,
    message TEXT NOT NULL,
    channel_dispatched TEXT NOT NULL DEFAULT 'IN_APP'
);

CREATE INDEX IF NOT EXISTS idx_alert_history_user_id ON alert_history(user_id);
CREATE INDEX IF NOT EXISTS idx_alert_history_alert_id ON alert_history(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_history_timestamp ON alert_history(timestamp DESC);

-- ============================================================
-- Paper Trading Portfolios Table
-- ============================================================
CREATE TABLE IF NOT EXISTS paper_portfolios (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    virtual_capital DOUBLE PRECISION NOT NULL DEFAULT 1000000.0,
    available_margin DOUBLE PRECISION NOT NULL DEFAULT 1000000.0,
    used_margin DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_paper_portfolios_user_id UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_portfolios_user_id ON paper_portfolios(user_id);

-- ============================================================
-- Paper Trading Orders Table
-- ============================================================
CREATE TABLE IF NOT EXISTS paper_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    underlying TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL DEFAULT 'MARKET',
    product TEXT NOT NULL DEFAULT 'INTRADAY',
    quantity INTEGER NOT NULL,
    price DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    trigger_price DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'FILLED',
    fill_price DOUBLE PRECISION,
    rejection_reason TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_paper_orders_user_id ON paper_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_paper_orders_order_id ON paper_orders(order_id);
CREATE INDEX IF NOT EXISTS idx_paper_orders_timestamp ON paper_orders(timestamp DESC);

-- ============================================================
-- Paper Trading Positions Table
-- ============================================================
CREATE TABLE IF NOT EXISTS paper_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    position_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    underlying TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    side TEXT NOT NULL,
    product TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    average_price DOUBLE PRECISION NOT NULL,
    ltp DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    unrealized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    used_margin DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    is_open BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_paper_positions_user_pos UNIQUE (user_id, position_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_positions_user_id ON paper_positions(user_id);
CREATE INDEX IF NOT EXISTS idx_paper_positions_is_open ON paper_positions(is_open);

-- ============================================================
-- ML Predictions Table
-- ============================================================
CREATE TABLE IF NOT EXISTS ml_predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    spot_price DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    bullish_pct DOUBLE PRECISION NOT NULL,
    neutral_pct DOUBLE PRECISION NOT NULL,
    bearish_pct DOUBLE PRECISION NOT NULL,
    trend_strength DOUBLE PRECISION NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL,
    predicted_bias TEXT NOT NULL,
    market_regime TEXT NOT NULL,
    top_features JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_version TEXT NOT NULL DEFAULT 'XGBoost-LightGBM-Ensemble-v1.0'
);

CREATE INDEX IF NOT EXISTS idx_ml_predictions_symbol ON ml_predictions(symbol);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_timestamp ON ml_predictions(timestamp DESC);

-- ============================================================
-- AI Reports Table
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'mock_ai',
    market_bias TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    summary TEXT NOT NULL,
    raw_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_reports_symbol ON ai_reports(symbol);
CREATE INDEX IF NOT EXISTS idx_ai_reports_timestamp ON ai_reports(timestamp DESC);

-- ============================================================
-- Triggers: Auto updated_at timestamp
-- ============================================================
DROP TRIGGER IF EXISTS update_alert_rules_updated_at ON public.alert_rules;
CREATE TRIGGER update_alert_rules_updated_at
    BEFORE UPDATE ON public.alert_rules
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_paper_portfolios_updated_at ON public.paper_portfolios;
CREATE TRIGGER update_paper_portfolios_updated_at
    BEFORE UPDATE ON public.paper_portfolios
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_paper_positions_updated_at ON public.paper_positions;
CREATE TRIGGER update_paper_positions_updated_at
    BEFORE UPDATE ON public.paper_positions
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ============================================================
-- Row Level Security (RLS)
-- ============================================================

ALTER TABLE alert_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ml_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_reports ENABLE ROW LEVEL SECURITY;

-- Alert Rules RLS
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'alert_rules_select_own') THEN
        CREATE POLICY alert_rules_select_own ON alert_rules FOR SELECT USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'alert_rules_insert_own') THEN
        CREATE POLICY alert_rules_insert_own ON alert_rules FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'alert_rules_update_own') THEN
        CREATE POLICY alert_rules_update_own ON alert_rules FOR UPDATE USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'alert_rules_delete_own') THEN
        CREATE POLICY alert_rules_delete_own ON alert_rules FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

-- Alert History RLS
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'alert_history_select_own') THEN
        CREATE POLICY alert_history_select_own ON alert_history FOR SELECT USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'alert_history_insert_own') THEN
        CREATE POLICY alert_history_insert_own ON alert_history FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

-- Paper Portfolios RLS
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'paper_portfolios_select_own') THEN
        CREATE POLICY paper_portfolios_select_own ON paper_portfolios FOR SELECT USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'paper_portfolios_insert_own') THEN
        CREATE POLICY paper_portfolios_insert_own ON paper_portfolios FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'paper_portfolios_update_own') THEN
        CREATE POLICY paper_portfolios_update_own ON paper_portfolios FOR UPDATE USING (auth.uid() = user_id);
    END IF;
END $$;

-- Paper Orders RLS
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'paper_orders_select_own') THEN
        CREATE POLICY paper_orders_select_own ON paper_orders FOR SELECT USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'paper_orders_insert_own') THEN
        CREATE POLICY paper_orders_insert_own ON paper_orders FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

-- Paper Positions RLS
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'paper_positions_select_own') THEN
        CREATE POLICY paper_positions_select_own ON paper_positions FOR SELECT USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'paper_positions_insert_own') THEN
        CREATE POLICY paper_positions_insert_own ON paper_positions FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'paper_positions_update_own') THEN
        CREATE POLICY paper_positions_update_own ON paper_positions FOR UPDATE USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'paper_positions_delete_own') THEN
        CREATE POLICY paper_positions_delete_own ON paper_positions FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

-- ML Predictions RLS (Public read for authenticated and anon, service role writes)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ml_predictions_select_all') THEN
        CREATE POLICY ml_predictions_select_all ON ml_predictions FOR SELECT USING (TRUE);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ml_predictions_insert_all') THEN
        CREATE POLICY ml_predictions_insert_all ON ml_predictions FOR INSERT WITH CHECK (TRUE);
    END IF;
END $$;

-- AI Reports RLS (Public read, write enabled)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ai_reports_select_all') THEN
        CREATE POLICY ai_reports_select_all ON ai_reports FOR SELECT USING (TRUE);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ai_reports_insert_all') THEN
        CREATE POLICY ai_reports_insert_all ON ai_reports FOR INSERT WITH CHECK (TRUE);
    END IF;
END $$;
