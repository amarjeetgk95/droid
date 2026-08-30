-- ============================================================
-- Migration: 002_seed_instruments_expiries
-- Description: Seed demo instrument and expiry metadata
-- WARNING: This is DEMO data only, not authoritative NSE data
-- ============================================================

-- Seed instruments (DEMO)
INSERT INTO instruments (symbol, display_name, exchange, instrument_type, underlying, is_active) VALUES
    ('NIFTY', 'NIFTY 50', 'NSE', 'INDEX', 'NIFTY', TRUE),
    ('BANKNIFTY', 'NIFTY BANK', 'NSE', 'INDEX', 'BANKNIFTY', TRUE),
    ('FINNIFTY', 'NIFTY FIN SERVICE', 'NSE', 'INDEX', 'FINNIFTY', TRUE),
    ('INDIAVIX', 'INDIA VIX', 'NSE', 'INDEX', 'INDIAVIX', TRUE),
    ('MIDCPNIFTY', 'NIFTY MID SELECT', 'NSE', 'INDEX', 'MIDCPNIFTY', TRUE),
    ('SENSEX', 'SENSEX', 'BSE', 'INDEX', 'SENSEX', TRUE),
    ('BANKEX', 'BANKEX', 'BSE', 'INDEX', 'BANKEX', TRUE)
ON CONFLICT (exchange, symbol) DO NOTHING;

-- Seed demo expiries for NIFTY (DEMO - not authoritative)
-- Weekly expiries on Thursday, monthly on last Thursday
INSERT INTO expiries (instrument_id, expiry_date, expiry_type, is_active, metadata_source, effective_from)
SELECT
    i.id,
    d::date,
    CASE WHEN d = date_trunc('month', d) + interval '1 month' - interval '1 day' - ((extract(dow from date_trunc('month', d) + interval '1 month' - interval '1 day')::int - 4 + 7) % 7) * interval '1 day'
         THEN 'MONTHLY' ELSE 'WEEKLY' END,
    TRUE,
    'DEMO_SEED',
    CURRENT_DATE
FROM instruments i
CROSS JOIN generate_series(
    CURRENT_DATE,
    CURRENT_DATE + INTERVAL '90 days',
    INTERVAL '1 day'
) d
WHERE i.symbol = 'NIFTY'
  AND extract(dow from d) = 4  -- Thursday
ON CONFLICT DO NOTHING;

-- Seed demo expiries for BANKNIFTY (DEMO - Wednesday expiry)
INSERT INTO expiries (instrument_id, expiry_date, expiry_type, is_active, metadata_source, effective_from)
SELECT
    i.id,
    d::date,
    CASE WHEN d = date_trunc('month', d) + interval '1 month' - interval '1 day' - ((extract(dow from date_trunc('month', d) + interval '1 month' - interval '1 day')::int - 3 + 7) % 7) * interval '1 day'
         THEN 'MONTHLY' ELSE 'WEEKLY' END,
    TRUE,
    'DEMO_SEED',
    CURRENT_DATE
FROM instruments i
CROSS JOIN generate_series(
    CURRENT_DATE,
    CURRENT_DATE + INTERVAL '90 days',
    INTERVAL '1 day'
) d
WHERE i.symbol = 'BANKNIFTY'
  AND extract(dow from d) = 3  -- Wednesday
ON CONFLICT DO NOTHING;

-- Seed demo expiries for FINNIFTY (DEMO - Tuesday expiry)
INSERT INTO expiries (instrument_id, expiry_date, expiry_type, is_active, metadata_source, effective_from)
SELECT
    i.id,
    d::date,
    CASE WHEN d = date_trunc('month', d) + interval '1 month' - interval '1 day' - ((extract(dow from date_trunc('month', d) + interval '1 month' - interval '1 day')::int - 2 + 7) % 7) * interval '1 day'
         THEN 'MONTHLY' ELSE 'WEEKLY' END,
    TRUE,
    'DEMO_SEED',
    CURRENT_DATE
FROM instruments i
CROSS JOIN generate_series(
    CURRENT_DATE,
    CURRENT_DATE + INTERVAL '90 days',
    INTERVAL '1 day'
) d
WHERE i.symbol = 'FINNIFTY'
  AND extract(dow from d) = 2  -- Tuesday
ON CONFLICT DO NOTHING;
