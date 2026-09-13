-- 015 Institutional flow warehouse (PIT-safe, append-only, revision-aware).
-- NSE daily cash + derivatives positioning. available_time = T+1 18:00 IST.
-- Revisions are new rows (is_revision=true), never UPDATEs, so AS-OF joins stay correct.

CREATE TABLE IF NOT EXISTS public.institutional_flow_daily (
    event_date DATE NOT NULL,
    available_time_utc TIMESTAMPTZ NOT NULL,
    ingestion_time_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    fii_cash_net_crores NUMERIC(14,2) NOT NULL,
    dii_cash_net_crores NUMERIC(14,2) NOT NULL,
    fii_cash_buy_crores NUMERIC(14,2),
    fii_cash_sell_crores NUMERIC(14,2),
    dii_cash_buy_crores NUMERIC(14,2),
    dii_cash_sell_crores NUMERIC(14,2),
    fii_fut_long INT,
    fii_fut_short INT,
    fii_fut_net INT,
    fii_lsr NUMERIC(10,4),
    pcr NUMERIC(10,4),
    source TEXT NOT NULL DEFAULT 'mrchartist_proxy_fetch-pipeline',
    is_revision BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_institutional_flow_daily PRIMARY KEY (event_date, is_revision, source)
);

CREATE INDEX IF NOT EXISTS idx_flow_daily_available
    ON public.institutional_flow_daily (available_time_utc);
CREATE INDEX IF NOT EXISTS idx_flow_daily_event
    ON public.institutional_flow_daily (event_date);
