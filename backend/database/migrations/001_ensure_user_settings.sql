-- Ensure user_settings table exists for Telegram persistence
-- Run this ONCE in Supabase SQL Editor if the table doesn't exist

CREATE TABLE IF NOT EXISTS user_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
    theme TEXT DEFAULT 'dark',
    default_symbol TEXT DEFAULT 'NIFTY',
    default_timeframe TEXT DEFAULT '5m',
    default_expiry TEXT,
    preferred_market_provider TEXT DEFAULT 'fyers',
    preferred_ai_provider TEXT DEFAULT 'gemini',
    preferred_ai_model TEXT,
    notification_enabled BOOLEAN DEFAULT true,
    app_settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookups during Telegram restore
CREATE INDEX IF NOT EXISTS idx_user_settings_app_settings ON user_settings USING GIN (app_settings);
