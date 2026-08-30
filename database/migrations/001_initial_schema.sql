-- ============================================================
-- Migration: 001_initial_schema
-- Description: Initial Phase 2 schema for profiles, user_settings,
--              watchlists, watchlist_items, instruments, expiries
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Profiles table (references auth.users.id from Supabase Auth)
-- ============================================================
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_profiles_id ON profiles(id);

-- ============================================================
-- User settings table (one row per user)
-- ============================================================
CREATE TABLE IF NOT EXISTS user_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    theme TEXT NOT NULL DEFAULT 'dark',
    default_symbol TEXT NOT NULL DEFAULT 'NIFTY',
    default_timeframe TEXT NOT NULL DEFAULT '5m',
    default_expiry TEXT,
    preferred_market_provider TEXT NOT NULL DEFAULT 'mock',
    preferred_ai_provider TEXT NOT NULL DEFAULT 'mock_ai',
    preferred_ai_model TEXT,
    notification_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_settings_user_id UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings(user_id);

-- ============================================================
-- Watchlists table
-- ============================================================
CREATE TABLE IF NOT EXISTS watchlists (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'My Watchlist',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_watchlists_user_name UNIQUE (user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id);

-- ============================================================
-- Watchlist items table
-- ============================================================
CREATE TABLE IF NOT EXISTS watchlist_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    watchlist_id UUID NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    instrument_id BIGINT REFERENCES instruments(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_instrument_id ON watchlist_items(instrument_id);

-- ============================================================
-- Instruments table (metadata only)
-- ============================================================
CREATE TABLE IF NOT EXISTS instruments (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    display_name TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    instrument_type TEXT NOT NULL DEFAULT 'INDEX',
    underlying TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_instruments_exchange_symbol UNIQUE (exchange, symbol)
);

CREATE INDEX IF NOT EXISTS idx_instruments_symbol ON instruments(symbol);
CREATE INDEX IF NOT EXISTS idx_instruments_underlying ON instruments(underlying);
CREATE INDEX IF NOT EXISTS idx_instruments_is_active ON instruments(is_active);

-- ============================================================
-- Expiries table
-- ============================================================
CREATE TABLE IF NOT EXISTS expiries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    instrument_id BIGINT REFERENCES instruments(id) ON DELETE CASCADE,
    expiry_date DATE NOT NULL,
    expiry_datetime TIMESTAMPTZ,
    expiry_type TEXT NOT NULL DEFAULT 'WEEKLY',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata_source TEXT,
    effective_from DATE,
    effective_until DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_expiries_instrument_id ON expiries(instrument_id);
CREATE INDEX IF NOT EXISTS idx_expiries_expiry_date ON expiries(expiry_date);
CREATE INDEX IF NOT EXISTS idx_expiries_is_active ON expiries(is_active);

-- ============================================================
-- Trigger: Auto-create profile on new auth user
-- ============================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, display_name, created_at, updated_at)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1)),
        NOW(),
        NOW()
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================
-- Trigger: Auto-create default settings on profile creation
-- ============================================================
CREATE OR REPLACE FUNCTION public.handle_new_user_settings()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_settings (user_id, created_at, updated_at)
    VALUES (NEW.id, NOW(), NOW())
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_profile_created ON public.profiles;
CREATE TRIGGER on_profile_created
    AFTER INSERT ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user_settings();

-- ============================================================
-- Trigger: Update updated_at timestamp
-- ============================================================
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_profiles_updated_at ON public.profiles;
CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_settings_updated_at ON public.user_settings;
CREATE TRIGGER update_user_settings_updated_at
    BEFORE UPDATE ON public.user_settings
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_watchlists_updated_at ON public.watchlists;
CREATE TRIGGER update_watchlists_updated_at
    BEFORE UPDATE ON public.watchlists
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_instruments_updated_at ON public.instruments;
CREATE TRIGGER update_instruments_updated_at
    BEFORE UPDATE ON public.instruments
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_expiries_updated_at ON public.expiries;
CREATE TRIGGER update_expiries_updated_at
    BEFORE UPDATE ON public.expiries
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ============================================================
-- Row Level Security (RLS)
-- ============================================================

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist_items ENABLE ROW LEVEL SECURITY;

-- Profiles: users can read/update own profile
CREATE POLICY profiles_select_own ON profiles
    FOR SELECT USING (auth.uid() = id);
CREATE POLICY profiles_update_own ON profiles
    FOR UPDATE USING (auth.uid() = id);

-- User settings: users can CRUD own settings
CREATE POLICY user_settings_select_own ON user_settings
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY user_settings_insert_own ON user_settings
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY user_settings_update_own ON user_settings
    FOR UPDATE USING (auth.uid() = user_id);

-- Watchlists: users can CRUD own watchlists
CREATE POLICY watchlists_select_own ON watchlists
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY watchlists_insert_own ON watchlists
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY watchlists_update_own ON watchlists
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY watchlists_delete_own ON watchlists
    FOR DELETE USING (auth.uid() = user_id);

-- Watchlist items: access through parent watchlist ownership
CREATE POLICY watchlist_items_select_own ON watchlist_items
    FOR SELECT USING (
        watchlist_id IN (SELECT id FROM watchlists WHERE user_id = auth.uid())
    );
CREATE POLICY watchlist_items_insert_own ON watchlist_items
    FOR INSERT WITH CHECK (
        watchlist_id IN (SELECT id FROM watchlists WHERE user_id = auth.uid())
    );
CREATE POLICY watchlist_items_update_own ON watchlist_items
    FOR UPDATE USING (
        watchlist_id IN (SELECT id FROM watchlists WHERE user_id = auth.uid())
    );
CREATE POLICY watchlist_items_delete_own ON watchlist_items
    FOR DELETE USING (
        watchlist_id IN (SELECT id FROM watchlists WHERE user_id = auth.uid())
    );

-- Instruments: public read, no direct user write
CREATE POLICY instruments_select_all ON instruments
    FOR SELECT USING (TRUE);

-- Expiries: public read, no direct user write
CREATE POLICY expiries_select_all ON expiries
    FOR SELECT USING (TRUE);
