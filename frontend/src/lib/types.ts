export type DataStatus = 'LIVE' | 'DEGRADED' | 'STALE' | 'OFFLINE' | 'DISCONNECTED' | 'ERROR' | 'CLOSED' | 'INVALID';
export type MarketSession = 'PRE_OPEN' | 'OPEN' | 'CLOSED' | 'POST_CLOSE';
export type Sentiment = 'VERY_BEARISH' | 'BEARISH' | 'NEUTRAL' | 'BULLISH' | 'VERY_BULLISH';

export interface NormalizedQuote {
  symbol: string;
  display_name: string;
  timestamp: string;
  ltp: number;
  open: number;
  high: number;
  low: number;
  previous_close: number;
  change: number;
  change_percent: number;
  volume: number;
  open_interest: number | null;
  status: DataStatus;
  provider: string;
}

export interface NormalizedCandle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap: number | null;
}

export interface IndexCard {
  symbol: string;
  display_name: string;
  ltp: number;
  change: number;
  change_percent: number;
  open: number;
  high: number;
  low: number;
  previous_close: number;
  volume: number;
  open_interest: number | null;
  sparkline: number[];
  status: DataStatus;
  timestamp: string | null;
  provider: string;
}

export interface SectorBreadth {
  name: string;
  change_percent: number;
  advancing: number;
  declining: number;
  unchanged: number;
}

export interface MarketBreadthData {
  advancing: number;
  declining: number;
  unchanged: number;
  advance_decline_ratio: number;
  sectors: SectorBreadth[];
  sentiment: Sentiment;
  sentiment_score: number;
  status: DataStatus;
  timestamp: string | null;
}

export interface MarketHealthStatus {
  status: 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY';
  is_healthy?: boolean;
  provider: string;
  mode: 'OFFLINE' | 'LIVE';
  last_update: string | null;
  data_age_seconds: number | null;
  latency_ms: number | null;
  active_instruments: number;
  reconnect_count: number;
  subscriptions: number;
  buffer_depth: number;
  dropped_events: number;
  circuit_breaker_state: string;
  last_heartbeat: string | null;
  message: string;
}

export interface TickEvent {
  timestamp: string;
  symbol: string;
  instrument_token: string;
  ltp: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume: number;
  open_interest?: number | null;
  bid?: number | null;
  ask?: number | null;
  sequence_number?: number | null;
  provider: string;
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
}

export interface ContractMaster {
  instrument_token: string;
  exchange: string;
  symbol: string;
  underlying: string;
  contract_type: 'INDEX_OPTION' | 'STOCK_OPTION' | 'INDEX_FUTURE' | 'STOCK_FUTURE' | 'INDEX_SPOT' | 'EQUITY_SPOT';
  option_type?: 'CE' | 'PE' | null;
  option_style: 'EUROPEAN' | 'AMERICAN';
  strike?: number | null;
  expiry?: string | null;
  expiry_type: 'WEEKLY' | 'MONTHLY' | 'QUARTERLY' | 'FAR';
  lot_size: number;
  tick_size: number;
  settlement_type: 'CASH_SETTLED' | 'PHYSICAL_DELIVERY';
  pricing_style: 'FUTURES_BLACK76' | 'SPOT_BLACK_SCHOLES';
  contract_status: 'ACTIVE' | 'EXPIRED' | 'SUSPENDED';
  effective_from: string;
  effective_until?: string | null;
  provider: string;
}

export interface ExpiryResolution {
  underlying: string;
  current_expiry: string | null;
  next_expiry: string | null;
  weekly_expiries: string[];
  monthly_expiries: string[];
  all_expiries: string[];
}

export interface MarketStatusResponse {
  session: MarketSession;
  market_time: string;
  is_trading_day: boolean;
  data_status: DataStatus;
  provider: string;
}

export interface OptionGreeks {
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  rho: number;
  iv: number | null;
  theoretical_price: number;
  intrinsic_value: number;
  time_value: number;
}

export interface OptionSide {
  symbol: string;
  instrument_token?: string | null;
  ltp: number;
  change: number;
  change_percent: number;
  volume: number;
  open_interest: number;
  oi_change: number;
  bid?: number | null;
  ask?: number | null;
  is_itm: boolean;
  greeks?: OptionGreeks | null;
}

export interface OptionChainStrikeRow {
  strike: number;
  is_atm: boolean;
  call?: OptionSide | null;
  put?: OptionSide | null;
}

export interface OptionsAnalytics {
  symbol: string;
  spot_price: number;
  futures_price: number;
  expiry: string;
  atm_strike: number;
  atm_iv: number | null;
  pcr_oi: number;
  pcr_volume: number;
  max_pain_strike: number;
  total_call_oi: number;
  total_put_oi: number;
  total_call_volume: number;
  total_put_volume: number;
  iv_skew?: number | null;
  time_to_expiry_days: number;
  risk_free_rate: number;
  rate_source: string;
}

export interface OptionChainResponse {
  underlying: string;
  spot_price: number;
  futures_price: number;
  expiry: string;
  expiries: string[];
  analytics: OptionsAnalytics;
  strikes: OptionChainStrikeRow[];
}

export interface MaxPainResult {
  symbol: string;
  expiry: string;
  max_pain_strike: number;
  total_loss_at_max_pain: number;
  strikes: number[];
  payouts: number[];
}

export interface InstitutionalStrikeFlow {
  strike: number;
  is_atm: boolean;
  call_oi: number;
  put_oi: number;
  call_oi_change: number;
  put_oi_change: number;
  call_volume: number;
  put_volume: number;
  call_ltp: number;
  put_ltp: number;
  call_buildup: 'LONG_BUILDUP' | 'SHORT_BUILDUP' | 'SHORT_COVERING' | 'LONG_UNWINDING' | 'NEUTRAL';
  put_buildup: 'LONG_BUILDUP' | 'SHORT_BUILDUP' | 'SHORT_COVERING' | 'LONG_UNWINDING' | 'NEUTRAL';
  net_flow: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
}

export interface InstitutionalFlowResponse {
  symbol: string;
  expiry: string;
  spot_price: number;
  atm_strike: number;
  pcr_oi: number;
  pcr_volume: number;
  max_pain_strike: number;
  call_wall_strike: number;
  put_floor_strike: number;
  institutional_sentiment: 'STRONG_BULLISH' | 'BULLISH' | 'NEUTRAL' | 'BEARISH' | 'STRONG_BEARISH';
  institutional_score: number;
  total_call_oi: number;
  total_put_oi: number;
  total_call_volume: number;
  total_put_volume: number;
  strike_flows: InstitutionalStrikeFlow[];
}

export interface TechnicalIndicators {
  rsi_14: number;
  adx_14: number;
  plus_di: number;
  minus_di: number;
  atr_14: number;
  supertrend_value: number;
  supertrend_direction: 'BULLISH' | 'BEARISH';
  bollinger_upper: number;
  bollinger_middle: number;
  bollinger_lower: number;
  bollinger_bandwidth: number;
  bollinger_pct_b: number;
  ema_20?: number | null;
  ema_50?: number | null;
  sma_200?: number | null;
}

export interface PivotSetModel {
  pivot: number;
  r1: number;
  r2: number;
  r3: number;
  r4?: number | null;
  s1: number;
  s2: number;
  s3: number;
  s4?: number | null;
}

export interface KeyLevelsModel {
  classic_pivots: PivotSetModel;
  fibonacci_pivots: PivotSetModel;
  camarilla_pivots: PivotSetModel;
  prior_day_high: number;
  prior_day_low: number;
  prior_day_close: number;
  day_open: number;
  poc: number;
  vah: number;
  val: number;
  nearest_resistance: number;
  nearest_support: number;
  distance_to_resistance_pts: number;
  distance_to_support_pts: number;
}

export interface VixRegimeInfo {
  vix_value: number;
  change: number;
  change_percent: number;
  regime_category: 'LOW_VOLATILITY' | 'NORMAL_VOLATILITY' | 'ELEVATED_VOLATILITY' | 'EXTREME_VOLATILITY';
  interpretation: string;
  recommended_option_strategy: string;
  historical_percentile: number;
}

export interface MarketRegimeOverview {
  symbol: string;
  spot_price: number;
  regime_state: 'TRENDING_BULLISH' | 'TRENDING_BEARISH' | 'RANGEBOUND_LOW_VOL' | 'RANGEBOUND_HIGH_VOL' | 'VOLATILE_EXPANSION' | 'COMPRESSION_SQUEEZE';
  confidence_score: number;
  summary_headline: string;
  institutional_rationale: string;
  indicators: TechnicalIndicators;
  key_levels: KeyLevelsModel;
  vix_regime: VixRegimeInfo;
}

export interface AIInsightResponse {
  symbol: string;
  timestamp: string;
  market_bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'VOLATILE';
  confidence: number;
  executive_summary: string;
  simple_takeaway?: string;
  options_interpretation: string;
  futures_flow_analysis: string;
  regime_and_levels: string;
  recommended_strategy_framework: string;
  risk_management_notes: string;
  disclaimer: string;
  provider_used: string;
}

export interface AIHistoryItem {
  id: string;
  symbol: string;
  timestamp: string;
  market_bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'VOLATILE';
  confidence: number;
  executive_summary: string;
}

export type AIChatRole = 'system' | 'user' | 'assistant' | 'tool';

export interface AIChatMessage {
  role: AIChatRole;
  content: string;
  reasoning_content?: string | null;
  tool_calls?: any[] | null;
  tool_call_id?: string | null;
  name?: string | null;
}

export interface AIChatRequest {
  messages: AIChatMessage[];
  symbol?: string;
  provider?: string;
  model?: string | null;
  temperature?: number;
  context_page?: string | null;
  enable_tools?: boolean;
  allow_paid?: boolean | null;
  openrouter_api_key?: string | null;
  gemini_api_key?: string | null;
  openai_api_key?: string | null;
  ollama_base_url?: string | null;
  ollama_model?: string | null;
}

export interface AIChatStreamChunk {
  type: 'content' | 'reasoning' | 'tool_call' | 'tool_result' | 'done' | 'error';
  delta?: string;
  reasoning_delta?: string;
  tool_call?: {
    id?: string;
    type?: string;
    function?: {
      name: string;
      arguments: string;
    };
  } | null;
  tool_result?: {
    name: string;
    arguments: string;
    result: any;
  } | null;
  finish_reason?: string | null;
  provider_used?: string | null;
  model_used?: string | null;
}

export interface AIOptionLeg {
  strike: number;
  option_type: 'CE' | 'PE';
  action: 'BUY' | 'SELL';
  expiry?: string | null;
  estimated_premium: number;
  delta?: number | null;
  theta?: number | null;
}

export interface AIOptionsStrategyRecommendation {
  symbol: string;
  strategy_name: string;
  market_outlook: string;
  legs: AIOptionLeg[];
  max_profit_pts: string;
  max_loss_pts: string;
  risk_reward_ratio: string;
  breakevens: number[];
  net_debit_credit_pts: number;
  net_delta: number;
  net_theta: number;
  rationale: string;
  entry_rules: string[];
  exit_rules: string[];
  risk_management: string;
  timestamp: string;
  provider_used: string;
}

export interface AIOptionsStrategyRequest {
  symbol?: string;
  outlook?: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'HIGH_VOLATILITY' | 'LOW_VOLATILITY' | 'DIRECTIONAL_RANGE';
  custom_query?: string | null;
  target_dte?: number | null;
  max_risk_tolerance?: 'LOW' | 'MODERATE' | 'AGGRESSIVE';
  provider?: string;
  model?: string | null;
  allow_paid?: boolean | null;
  openrouter_api_key?: string | null;
  gemini_api_key?: string | null;
}

export interface AITradeValidationRequest {
  symbol?: string;
  timeframe?: string;
  direction?: 'BUY' | 'SELL';
  entry_price: number;
  stop_loss: number;
  target_price: number;
  thesis_notes?: string | null;
  provider?: string;
  model?: string | null;
  allow_paid?: boolean | null;
  openrouter_api_key?: string | null;
  gemini_api_key?: string | null;
}

export interface AITradeValidationResponse {
  symbol: string;
  decision: 'CONFIRM' | 'REJECT' | 'WATCH' | 'UNCERTAIN';
  score: number;
  risk_reward_calculated: number;
  technical_alignment: string;
  derivatives_alignment: string;
  volatility_regime_check: string;
  invalidation_conditions: string[];
  warning_traps: string[];
  executive_verdict: string;
  timestamp: string;
  provider_used: string;
}

export interface AIDailyBriefingResponse {
  symbol: string;
  session_type: 'PRE_MARKET' | 'POST_MARKET' | 'INTRADAY_UPDATE';
  timestamp: string;
  executive_summary: string;
  key_levels_to_watch: {
    spot: number;
    pivot: number;
    r1: number;
    s1: number;
    poc: number;
    vah: number;
    val: number;
  };
  options_pin_and_pivots: string;
  fii_dii_implication: string;
  actionable_playbook: string[];
  provider_used: string;
}

export interface OpenRouterModel {
  id: string;
  name: string;
  is_free: boolean;
  context_length: number;
  input_price: number;
  output_price: number;
  pricing: Record<string, unknown>;
  supports_tools: boolean;
  supports_vision: boolean;
  supports_structured_outputs?: boolean;
  description: string;
  category: 'Finance' | 'Reasoning' | 'General' | 'Coding' | 'Vision' | 'Fast' | 'Research' | 'Unknown' | string;
  trading_rank: number;
  recommended_for_trading: boolean;
  badges: string[];
  architecture?: Record<string, unknown>;
  created?: string;
}

export interface OpenRouterCatalogResponse {
  provider: string;
  updated_at: string;
  free_only: boolean;
  pricing_filter: string;
  models: OpenRouterModel[];
  default_model: OpenRouterModel | null;
  total_count: number;
  free_count: number;
  paid_count: number;
  using_cached: boolean;
  cache_error?: string;
  cache_age_seconds: number;
}

export interface DetectedPatternModel {
  pattern_type: string;
  name: string;
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  confidence: number;
  timeframe: string;
  trigger_price: number;
  invalidation_level: number;
  target_level: number;
  description: string;
}

export interface HistoricalShiftPoint {
  date: string;
  pcr_oi: number;
  pcr_volume: number;
  max_pain_strike: number;
  atm_iv: number;
  futures_basis: number;
  spot_close: number;
}

export interface HistoricalShiftsResponse {
  symbol: string;
  shifts: HistoricalShiftPoint[];
}

export interface DaySeasonality {
  day_name: string;
  avg_return_pct: number;
  win_rate_pct: number;
  avg_range_pts: number;
  volatility_pct: number;
}

export interface SeasonalityResponse {
  symbol: string;
  days: DaySeasonality[];
  best_day_for_buyers: string;
  best_day_for_sellers: string;
}

export interface WatchlistItem {
  symbol: string;
  display_name: string;
  ltp: number;
  change: number;
  change_percent: number;
  volume: number;
  open_interest?: number | null;
  active_pattern?: string | null;
  regime_state?: string | null;
}

export interface PatternHitRate {
  symbol: string;
  pattern_type: string;
  pattern_name: string;
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  timeframe: string;
  sample_count: number;
  avg_return_1d?: number | null;
  stddev_return_1d?: number | null;
  avg_return_3d?: number | null;
  avg_return_5d?: number | null;
  hit_target_rate?: number | null;
  directional_accuracy?: number | null;
  first_detection?: string | null;
  last_detection?: string | null;
}

export interface PatternHitRateResponse {
  symbol: string;
  hit_rates: PatternHitRate[];
  total_patterns_tracked: number;
  total_labeled_outcomes: number;
}

export interface PatternOutcomeRecord {
  id: string;
  symbol: string;
  pattern_type: string;
  pattern_name: string;
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  confidence: number;
  timeframe: string;
  trigger_price: number;
  invalidation_level: number;
  target_level: number;
  detection_timestamp: string;
  regime_state?: string | null;
  outcome_1d?: number | null;
  outcome_3d?: number | null;
  outcome_5d?: number | null;
  hit_target_before_invalidation?: boolean | null;
  outcome_labeled_at?: string | null;
  outcome_source?: string | null;
}

export interface BacktestPayload {
  strategy_id: string;
  underlying: string;
  initial_capital: number;
  num_days: number;
  stop_loss_pct: number;
  target_pct: number;
  slippage_pct: number;
  include_costs: boolean;
}

export interface OrderPayload {
  symbol: string;
  underlying: string;
  side: 'BUY' | 'SELL';
  order_type?: 'MARKET' | 'LIMIT' | 'SL_MARKET' | 'SL_LIMIT';
  product?: 'INTRADAY' | 'CARRYFORWARD';
  quantity: number;
  price: number;
  trigger_price?: number | null;
}

export interface BasketOrderPayload {
  name: string;
  orders: OrderPayload[];
}

export interface VirtualOrder {
  order_id: string;
  timestamp: string;
  symbol: string;
  underlying: string;
  side: 'BUY' | 'SELL';
  order_type: 'MARKET' | 'LIMIT' | 'SL_MARKET' | 'SL_LIMIT';
  product: 'INTRADAY' | 'CARRYFORWARD';
  quantity: number;
  price: number;
  trigger_price?: number | null;
  status: 'PENDING' | 'FILLED' | 'CANCELLED' | 'REJECTED';
  fill_price?: number | null;
  rejection_reason?: string | null;
}

export interface VirtualPosition {
  position_id: string;
  symbol: string;
  underlying: string;
  instrument_type: string;
  side: 'BUY' | 'SELL';
  product: 'INTRADAY' | 'CARRYFORWARD';
  quantity: number;
  average_price: number;
  ltp: number;
  unrealized_pnl: number;
  realized_pnl: number;
  used_margin: number;
  is_open: boolean;
}

export interface PortfolioSummary {
  virtual_capital: number;
  available_margin: number;
  used_margin: number;
  margin_utilization_pct: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
  total_portfolio_pnl: number;
  open_positions_count: number;
}

export interface MLFeatureContribution {
  feature_name: string;
  value: number;
  contribution: number;
  description: string;
}

export interface MLPredictionResponse {
  symbol: string;
  timestamp: string;
  spot_price: number;
  bullish_pct: number;
  neutral_pct: number;
  bearish_pct: number;
  trend_strength: number;
  confidence_score: number;
  predicted_bias: 'BULLISH' | 'NEUTRAL' | 'BEARISH';
  market_regime: string;
  top_features: MLFeatureContribution[];
  model_version: string;
}

export interface ClientCategoryPosition {
  category: 'FII' | 'DII' | 'PRO' | 'CLIENT';
  index_futures_long: number;
  index_futures_short: number;
  index_futures_net: number;
  long_short_ratio: number;
  index_call_long: number;
  index_put_long: number;
  sentiment: 'BULLISH' | 'MILD_BULLISH' | 'NEUTRAL' | 'MILD_BEARISH' | 'BEARISH';
}

export interface CashMarketFlow {
  category: 'FII' | 'DII';
  buy_value_crores: number;
  sell_value_crores: number;
  net_value_crores: number;
  date: string;
}

export interface FIIDIIOverviewResponse {
  timestamp: string;
  fii_long_short_ratio: number;
  fii_futures_net_contracts: number;
  dii_futures_net_contracts: number;
  client_futures_net_contracts: number;
  pro_futures_net_contracts: number;
  fii_cash_net_crores: number;
  dii_cash_net_crores: number;
  institutional_sentiment: 'STRONG_BULLISH' | 'MILD_BULLISH' | 'NEUTRAL' | 'MILD_BEARISH' | 'STRONG_BEARISH';
  breakdown_by_category: ClientCategoryPosition[];
  recent_cash_flows: CashMarketFlow[];
}

export interface ApiMeta {
  provider: string;
  timestamp: string;
  status: DataStatus;
}

export interface ApiResponse<T> {
  data: T;
  error: string | null;
  meta: ApiMeta;
}

// ============================================================
// Phase 2: Supabase/PostgreSQL types
// ============================================================

export interface ProfileResponse {
  id: string;
  display_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserSettingsResponse {
  id: string;
  user_id: string;
  theme: string;
  default_symbol: string;
  default_timeframe: string;
  default_expiry: string | null;
  preferred_market_provider: string;
  preferred_ai_provider: string;
  preferred_ai_model: string | null;
  notification_enabled: boolean;
  // RECTIFY: full AppSettings blob persisted in Supabase as JSONB — Supabase is source of truth
  app_settings?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface UserSettingsUpdate {
  theme?: string;
  default_symbol?: string;
  default_timeframe?: string;
  default_expiry?: string | null;
  preferred_market_provider?: string;
  preferred_ai_provider?: string;
  preferred_ai_model?: string | null;
  notification_enabled?: boolean;
  // Full AppSettings JSON — frontend sends entire settings object here
  app_settings?: Record<string, unknown> | null;
}

export interface WatchlistResponse {
  id: string;
  user_id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface WatchlistItemResponse {
  id: string;
  watchlist_id: string;
  instrument_id: number | null;
  symbol: string;
  display_order: number;
  created_at: string;
}

export interface InstrumentResponse {
  id: number;
  symbol: string;
  display_name: string;
  exchange: string;
  instrument_type: string;
  underlying: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ExpiryResponse {
  id: string;
  instrument_id: number | null;
  expiry_date: string;
  expiry_datetime: string | null;
  expiry_type: string;
  is_active: boolean;
  metadata_source: string | null;
  effective_from: string | null;
  effective_until: string | null;
  created_at: string;
  updated_at: string;
}

// ----------------------------------------------------
// Cryptocurrency & Binance API Module Models
// ----------------------------------------------------

export type OrderBookSequenceStatus = 'SYNCING' | 'ACTIVE' | 'GAP_DETECTED' | 'STALE' | 'DISCONNECTED';
export type BasisStatus = 'CONTANGO' | 'BACKWARDATION' | 'NEUTRAL';
export type RelativeStrengthStatus = 'ETH_OUTPERFORMING' | 'BTC_OUTPERFORMING' | 'NEUTRAL';

export interface CryptoTicker {
  symbol: string;
  asset?: string;
  display_name: string;
  base_asset?: string;
  quote_asset?: string;
  market_type?: string;
  price: number;
  bid_price?: number | null;
  ask_price?: number | null;
  bid_size?: number | null;
  ask_size?: number | null;
  change_24h: number;
  change_percent_24h: number;
  high_24h: number;
  low_24h: number;
  volume_24h_quote: number;
  volume_24h_base: number;
  weighted_avg_price?: number;
  vwap?: number | null;
  trade_count?: number | null;
  spread?: number | null;
  spread_percent?: number | null;
  basis_pts?: number | null;
  high_low_spread_pct?: number | null;
  sparkline: number[];
  status: DataStatus;
  provider: string;
  last_updated: string;
  received_timestamp?: string;
  data_age_ms?: number;
}

export interface CryptoOrderBookLevel {
  price: number;
  quantity: number;
  total?: number;
  notional?: number;
  cumulative_quantity?: number;
  cumulative_notional?: number;
}

export interface CryptoOrderBook {
  symbol: string;
  market_type?: string;
  bids: CryptoOrderBookLevel[];
  asks: CryptoOrderBookLevel[];
  best_bid?: number;
  best_ask?: number;
  mid_price?: number;
  spread: number;
  spread_percent: number;
  bid_depth_total?: number;
  ask_depth_total?: number;
  depth_imbalance?: number;
  depth_imbalance_pct?: number;
  snapshot_id?: number | null;
  last_update_id?: number | null;
  sequence_status?: OrderBookSequenceStatus;
  data_age_ms?: number;
  status?: DataStatus;
  timestamp: string;
  provider: string;
}

export interface CryptoDerivatives {
  symbol: string;
  mark_price: number;
  index_price: number;
  spot_price?: number | null;
  basis?: number;
  basis_percent?: number;
  basis_status?: BasisStatus;
  estimated_settle_price?: number;
  funding_rate: number;
  funding_rate_percent: number;
  annualized_funding_rate?: number;
  next_funding_time: string;
  countdown_seconds: number;
  open_interest_usd: number;
  open_interest_coins: number;
  long_short_ratio: number;
  long_percentage: number;
  short_percentage: number;
  top_traders_long_short_ratio?: number | null;
  provider: string;
  status?: DataStatus;
  timestamp: string;
}

export interface CryptoPairComparison {
  eth_btc_ratio: number;
  eth_btc_change_24h: number;
  eth_btc_change_percent_24h: number;
  btc_price: number;
  btc_change_percent_24h: number;
  eth_price: number;
  eth_change_percent_24h: number;
  performance_spread_24h: number;
  relative_strength: RelativeStrengthStatus;
  relative_volume_ratio: number;
  status: DataStatus;
  timestamp: string;
}

export interface CryptoMarketOverview {
  fear_greed_score: number;
  fear_greed_label: string;
  btc_dominance_pct: number;
  eth_dominance_pct?: number;
  total_market_cap_usd: number;
  total_volume_24h_usd: number;
  combined_volume_24h_usd?: number;
  eth_btc_ratio?: number;
  tracked_pairs_count: number;
  top_assets?: CryptoTicker[];
  top_gainers: CryptoTicker[];
  top_losers: CryptoTicker[];
  status?: DataStatus;
  timestamp: string;
  provider: string;
}

export interface CryptoHealthResponse {
  btc: Record<string, string>;
  eth: Record<string, string>;
  websocket: string;
  last_update_ms: number;
  overall_status: string;
}

export type CryptoSignalDirection = 'LONG' | 'SHORT';
export type CryptoSignalStatus = 'ACTIVE' | 'TRIGGERED' | 'TARGET_HIT' | 'STOPPED_OUT' | 'EXPIRED';

export interface CryptoSignal {
  id: string;
  symbol: string;
  asset: string;
  direction: CryptoSignalDirection;
  strategy: string;
  strategy_name: string;
  entry_price: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
  current_price: number;
  risk_reward_ratio: number;
  confidence: number;
  timeframe: string;
  status: CryptoSignalStatus;
  confluence_factors: string[];
  rationale: string;
  timestamp: string;
}

export interface CryptoSignalsResponse {
  signals: CryptoSignal[];
  total_active: number;
  btc_signals: number;
  eth_signals: number;
  timestamp: string;
}


// ============================================================
// Historical Pattern Intelligence (HPI)
// ============================================================
export interface HpiDerivative {
  symbol: string;
  display_name: string;
  asset_class: 'INDEX' | 'CRYPTO';
  exchange: string;
  data_categories: string[];
}

export interface HpiUniverse {
  derivatives: HpiDerivative[];
  sampling_intervals: string[];
  storage_budget: { target_mb: number; warning_mb: number; hard_ceiling_mb: number };
  delete_range_types: string[];
}

export interface HpiSelectionEntry {
  symbol: string;
  enabled: boolean;
  data_categories: string[];
}

export interface HpiSelectionState {
  entries: HpiSelectionEntry[];
  updated_at: string;
}

export interface HpiPolicy {
  policy_id: string;
  instrument: string;
  derivative_category: string;
  feature_group: string;
  start_date: string | null;
  end_date: string | null;
  retention_days: number;
  sampling_interval: string;
  enabled: boolean;
  auto_delete_enabled: boolean;
  protected: boolean;
  storage_priority: number;
  created_at: string;
  updated_at: string;
}

export interface HpiCategoryStats {
  category: string;
  label: string;
  enabled: boolean;
  records: number;
  storage_mb: number;
  oldest: string | null;
  newest: string | null;
  auto_delete_enabled: boolean;
  protected: boolean;
  retention_days: number | null;
}

export interface HpiDatasetCard {
  symbol: string;
  display_name: string;
  enabled: boolean;
  data_categories_enabled: string[];
  historical_period_months: number | null;
  sampling_interval: string | null;
  records_stored: number;
  storage_used_mb: number;
  oldest_record: string | null;
  newest_record: string | null;
  protected: boolean;
  auto_delete_status: 'ON' | 'OFF' | 'PARTIAL';
  category_stats: HpiCategoryStats[];
}

export interface HpiStorageReport {
  current_storage_mb: number;
  target_mb: number;
  warning_mb: number;
  hard_ceiling_mb: number;
  status: 'WITHIN_TARGET' | 'WARNING' | 'EXCEEDS_HARD';
  datasets: HpiDatasetCard[];
}

export interface HpiCategoryEstimate {
  symbol: string;
  category: string;
  label: string;
  estimated_records: number;
  estimated_mb: number;
  sampling_interval: string;
}

export interface HpiImportPreview {
  current_storage_mb: number;
  requested_addition_mb: number;
  projected_storage_mb: number;
  status: string;
  blocked: boolean;
  alternatives: string[];
  breakdown: HpiCategoryEstimate[];
  symbol: string;
  sampling_interval: string;
  period_start: string;
  period_end: string;
  warnings: string[];
}

export interface HpiImportResult {
  symbol: string;
  imported_categories: string[];
  records_imported: number;
  storage_added_mb: number;
  total_storage_mb: number;
  status: string;
  sampling_interval: string;
  period_start: string;
  period_end: string;
}

export interface HpiDeletePreview {
  symbol: string;
  categories: string[];
  range_type: string;
  range_start: string;
  range_end: string;
  total_records: number;
  total_storage_mb: number;
  per_category: { category: string; label: string; records: number; storage_mb: number }[];
  analytical_impact: string[];
  price_technical_impact: string;
  protected_categories: string[];
  confirmation_token: string;
}

export interface HpiAuditEntry {
  deletion_id: string;
  user_id: string;
  derivative: string;
  dataset: string;
  start_date: string;
  end_date: string;
  records_deleted: number;
  storage_released_mb: number;
  timestamp: string;
  reason: string;
}

export interface HpiCoverageReport {
  symbol: string;
  derivative_enabled: boolean;
  overall: 'FULL' | 'PARTIAL' | 'MISSING' | 'DISABLED' | 'EMPTY';
  historical_coverage_months: number;
  datasets: {
    category: string;
    label: string;
    status: string;
    coverage_months: number;
    records: number;
    oldest: string | null;
    newest: string | null;
    deleted_ranges: string[][];
  }[];
  missing_datasets: string[];
  deleted_ranges: string[];
}

export interface HpiAnalysis {
  symbol: string;
  timeframe: string;
  historical_coverage_months: number;
  historical_coverage_label: string;
  similar_setups: number;
  confidence: number;
  warnings: string[];
  derivative_coverage: string;
  missing_dataset: string | null;
  coverage_report: HpiCoverageReport;
  setups: {
    signature: string;
    similar_count: number;
    bullish_pct: number;
    neutral_pct: number;
    bearish_pct: number;
    avg_forward_move_pct: number;
    similarity: number;
  }[];
  note: string | null;
}


// ============================================================================
// Telegram Integration
// ============================================================================

export interface TelegramPreferences {
  events: Record<string, boolean>;
  instruments: Record<string, boolean>;
  timeframes: Record<string, boolean>;
  breakout: boolean;
  breakdown: boolean;
}

export interface TelegramAuditRecord {
  notification_id: string;
  signal_id: string;
  event_type: string;
  telegram_chat_id: string;
  message_type: string;
  created_at_utc: number;
  sent_at_utc: number | null;
  delivery_status: string;
  attempt_count: number;
  error: string | null;
}
