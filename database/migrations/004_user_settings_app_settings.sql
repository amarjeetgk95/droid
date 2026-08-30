-- ============================================================
-- Migration: 004_user_settings_app_settings
-- Description: Extend user_settings to persist full AppSettings
--              (broker, quantitative, ai, paper, preferences) in
--              Supabase as JSONB, making Supabase the source of truth.
-- ============================================================

-- Add JSONB column for full application settings
ALTER TABLE user_settings
    ADD COLUMN IF NOT EXISTS app_settings JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Keep legacy flat columns in sync via helper function (optional)
-- On first deploy, backfill existing rows with defaults derived
-- from legacy columns so that reads always return a valid JSON.

-- Backfill: populate app_settings from legacy columns where empty
UPDATE user_settings
SET app_settings = jsonb_build_object(
    'preferences', jsonb_build_object(
        'theme', COALESCE(theme, 'dark'),
        'defaultIndexSymbol', COALESCE(default_symbol, 'NIFTY 50'),
        'numberFormat', 'INDIAN'
    ),
    'broker', jsonb_build_object(
        'provider', COALESCE(preferred_market_provider, 'mock')
    ),
    'ai', jsonb_build_object(
        'provider', COALESCE(preferred_ai_provider, 'mock_ai'),
        'geminiModel', COALESCE(preferred_ai_model, 'gemini-2.5-flash')
    ),
    'quantitative', jsonb_build_object(
        'riskFreeRate', 0.0675,
        'timeConvention', 'ACT365',
        'defaultPricingModel', 'FUTURES_BLACK76',
        'ivMethod', 'BRENT',
        'brokeragePerOrder', 20,
        'slippagePct', 0.05
    ),
    'paper', jsonb_build_object(
        'initialCapital', 1000000,
        'autoSquareOffTime', '15:20',
        'maxCapitalPerTradePct', 20,
        'maxDailyDrawdownHaltPct', 10,
        'requireOrderConfirm', true,
        'allowOvernightPositions', true
    )
)
WHERE app_settings = '{}'::jsonb;

-- Index for efficient JSONB queries (e.g., filtering by theme)
CREATE INDEX IF NOT EXISTS idx_user_settings_app_settings_gin
    ON user_settings USING GIN (app_settings);

COMMENT ON COLUMN user_settings.app_settings IS 'Full AppSettings JSON (broker, quantitative, ai, paper, preferences). Supabase is source of truth; localStorage is cache/mirror.';
