/**
 * Market Intelligence workspace types — extracted from page.tsx so the
 * adapter mapping and rendering share one authoritative shape.
 * Backend remains authoritative; frontend never recreates trading logic.
 */

export type InstrumentId = 'NIFTY' | 'BANKNIFTY' | 'SENSEX' | 'BTCUSD' | 'BREAKOUT_SETUPS';

export type SecondaryTab =
  | 'overview'
  | 'price-action'
  | 'futures'
  | 'options'
  | 'volume'
  | 'levels'
  | 'volatility'
  | 'cross-market'
  | 'breakout'
  | '10-min'
  | 'continuation'
  | 'ai'
  | 'risk'
  | 'data-health'
  | 'audit';

export interface FullMiResponse {
  instrument_id: string;
  asset_class: string;
  pipeline: string;
  header: {
    instrument: string;
    display_name: string;
    live_status: string;
    price: string | null;
    price_formatted: string;
    session: string;
    session_label: string;
    last_update_utc: number;
    last_update_iso: string;
    data_quality: string;
    feed_health: string;
    spot_source?: string;
    used_cache?: boolean;
  };
  market_state: {
    regime: string;
    price_action: Record<string, unknown>;
    momentum: string;
    participation: Record<string, unknown>;
    volatility: string;
    vwap: string;
    scores: {
      bullish_score: number;
      bearish_score: number;
      breakout_pressure: number;
      breakdown_pressure: number;
      false_breakout_risk: number;
    };
  };
  price_action: {
    structure: string;
    trend: string;
    momentum: string;
    location: string;
    vwap: string;
    volume: string;
    breadth: string;
  };
  evidence: {
    supporting: { dimension: string; signal: string; detail: string; state: string }[];
    conflicting: { dimension: string; signal: string; detail: string; state: string }[];
    missing: string[];
    stale: string[];
    invalid: string[];
  };
  levels: {
    support: string[];
    resistance: string[];
    breakout_trigger: string | null;
    breakdown_trigger: string | null;
    invalidation: string;
    nearest_support: string | null;
    nearest_resistance: string | null;
  };
  breakout: {
    direction: string;
    status: string;
    confidence: number;
    breakout_level: string | null;
    breakout_pressure: number;
    breakdown_pressure: number;
    false_breakout_risk: number;
    breakout_quality: number;
    supporting: string[];
    conflicts: string[];
    reason: string;
  };
  short_horizon: {
    strategy: string;
    instrument: string;
    direction: string;
    status: string;
    confidence: number;
    horizon_minutes: number;
    entry_zone: string[];
    stop_loss: string;
    target_zone: string[];
    false_breakout_risk: number;
    reason: string;
  };
  continuation: {
    strategy: string;
    instrument: string;
    direction: string;
    status: string;
    confidence: number;
    max_holding_minutes: number;
    reason: string;
    invalidation: string;
  };
  ai: {
    status: string;
    short_horizon: {
      decision: string;
      confidence: number;
      reasoning: string[];
      conflicts: string[];
      invalidation_conditions: string[];
    };
    continuation: {
      decision: string;
      confidence: number;
      reasoning: string[];
      conflicts: string[];
      invalidation_conditions: string[];
    };
    overall: unknown;
  };
  risk: {
    strategy: string;
    portfolio: string;
    exposure: string;
    margin: string;
    correlation: string;
    reason: string | null;
  };
  signal: {
    created_at_utc: number;
    ttl_ms: number | null;
    expires_at_utc: number;
    ai?: { status: string };
    validation_status: string;
    risk_status: string;
    fsm_state: string;
    is_expired: boolean;
    signal_id?: string;
  } | null;
  data_health: {
    feed: string;
    feed_reason: string | null;
    data_health: string;
    clock_sync: string;
    sequence: string;
    contract: string;
    snapshot: string;
    synchronization: string;
    last_event_age_ms: number | null;
    spot_source?: string;
    used_cache?: boolean;
  };
  capabilities: string[];
  instrument_specific: { is_crypto: boolean; fields: string[] };
  details?: {
    spot: { price: number | null; source: string; age_ms: number | null; used_cache: boolean; status: string };
    vwap: { value: number | null; relation: string; source: string | null; status: string; reason: string | null };
    volume: { volume_change: number | null; state: string; quote_volume: number | null; status: string; reason: string | null };
    options: {
      pcr: number | null;
      total_call_oi: number | null;
      total_put_oi: number | null;
      pcr_volume: number | null;
      status: string;
      reason: string | null;
    };
    volatility: { volatility_change: number | null; regime: string; status: string; reason: string | null };
    futures: { status: string; reason: string | null };
    liquidity: { state: string };
    atr: number | null;
    multi_timeframe: Record<string, string> | null;
    funding: { rate: number } | null;
    levels_source: string | null;
    breadth: string;
    cross_market: { status: string; detail: Record<string, unknown> };
    breadth_detail?: {
      advancing: number | null;
      declining: number | null;
      unchanged: number | null;
      advance_decline_ratio: number | null;
      sentiment: string | null;
      sentiment_score: number | null;
      status: string;
      reason: string | null;
    };
    provenance?: {
      errors?: Record<string, string>;
      cache_hits?: string[];
      vwap_source?: string | null;
      levels_source?: string | null;
      options_status?: string;
      meta_fresh?: boolean;
      spot_source?: string;
    };
  };
}
