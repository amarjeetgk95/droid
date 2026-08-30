// Data status values
export type DataStatus = 'LIVE' | 'STALE' | 'DEMO' | 'DISCONNECTED' | 'ERROR';
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
  provider: string;
  mode: 'DEMO' | 'LIVE';
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

export interface FuturesContractItem {
  symbol: string;
  instrument_token?: string | null;
  expiry: string;
  tenor: 'NEAR' | 'NEXT' | 'FAR';
  ltp: number;
  change: number;
  change_percent: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  open_interest: number;
  oi_change: number;
  oi_change_percent: number;
  basis: number;
  basis_percent: number;
  cost_of_carry_percent: number;
  fair_value: number;
  fair_value_spread: number;
  days_to_expiry: number;
}

export interface TermStructureCurve {
  underlying: string;
  spot_price: number;
  curve_state: 'CONTANGO' | 'BACKWARDATION' | 'FLAT';
  contracts: FuturesContractItem[];
  calendar_spread_next_near: number;
  calendar_spread_far_next: number;
}

export interface OIBuildupItem {
  symbol: string;
  underlying: string;
  ltp: number;
  price_change: number;
  price_change_percent: number;
  open_interest: number;
  oi_change: number;
  oi_change_percent: number;
  buildup_type: 'LONG_BUILDUP' | 'SHORT_BUILDUP' | 'LONG_UNWINDING' | 'SHORT_COVERING';
  interpretation: string;
  strength: 'STRONG' | 'MODERATE' | 'WEAK';
}

export interface RolloverMetrics {
  underlying: string;
  expiry: string;
  rollover_percent: number;
  rollover_spread: number;
  three_month_avg_rollover: number;
  rollover_pace: 'AHEAD' | 'IN_LINE' | 'BEHIND';
  total_futures_oi: number;
}

export interface FuturesOverview {
  underlying: string;
  spot_price: number;
  term_structure: TermStructureCurve;
  buildup: OIBuildupItem;
  rollover: RolloverMetrics;
  all_tracked_buildups: OIBuildupItem[];
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

export interface StrategyLegModel {
  id: string;
  option_type: 'CE' | 'PE';
  side: 'BUY' | 'SELL';
  strike: number;
  quantity: number;
  price: number;
  iv: number;
  expiry: string;
  lot_size: number;
}

export interface StrategyPayload {
  underlying: string;
  legs: StrategyLegModel[];
  spot_price?: number | null;
  expiry?: string | null;
}

export interface PayoffPointModel {
  spot_price: number;
  expiry_pnl: number;
  t0_pnl: number;
}

export interface StrategyPayoffResult {
  underlying: string;
  spot_price: number;
  net_premium: number;
  premium_type: 'DEBIT' | 'CREDIT';
  max_profit?: number | null;
  max_loss?: number | null;
  breakevens: number[];
  risk_reward_ratio?: number | null;
  pop_percent: number;
  net_delta: number;
  net_gamma: number;
  net_theta: number;
  net_vega: number;
  payoff_curve: PayoffPointModel[];
  legs: StrategyLegModel[];
}

export interface StrategyTemplate {
  id: string;
  name: string;
  category: 'DIRECTIONAL' | 'NON_DIRECTIONAL' | 'VOLATILITY' | 'ASYMMETRIC';
  outlook: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'HIGH_VOLATILITY';
  description: string;
  legs_description: string[];
}

export interface ScannedStrategy {
  id: string;
  name: string;
  underlying: string;
  category: 'DIRECTIONAL' | 'NON_DIRECTIONAL' | 'VOLATILITY' | 'ASYMMETRIC';
  outlook: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'HIGH_VOLATILITY';
  net_premium: number;
  premium_type: 'DEBIT' | 'CREDIT';
  max_profit?: number | null;
  max_loss?: number | null;
  pop_percent: number;
  risk_reward_ratio?: number | null;
  breakevens: number[];
  legs: StrategyLegModel[];
}

export interface AIInsightResponse {
  symbol: string;
  timestamp: string;
  market_bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'VOLATILE';
  confidence: number;
  executive_summary: string;
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

export interface BacktestTradeModel {
  trade_id: string;
  entry_date: string;
  exit_date: string;
  strategy_name: string;
  underlying: string;
  legs_description: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  gross_pnl: number;
  total_charges: number;
  net_pnl: number;
  status: string;
}

export interface EquityPointModel {
  timestamp: string;
  equity: number;
  drawdown_pct: number;
  net_pnl: number;
}

export interface MonthlyPnlModel {
  month_year: string;
  net_pnl: number;
  trades_count: number;
  win_rate_pct: number;
}

export interface BacktestResult {
  initial_capital: number;
  final_equity: number;
  total_net_pnl: number;
  net_roi_percent: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_percent: number;
  profit_factor: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_amount: number;
  max_drawdown_percent: number;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  equity_curve: EquityPointModel[];
  monthly_pnl: MonthlyPnlModel[];
  trades: BacktestTradeModel[];
}

export interface BacktestPreset {
  id: string;
  name: string;
  description: string;
  category: string;
  default_underlying: string;
  default_stop_loss_pct: number;
  default_target_pct: number;
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

export interface AlertPayload {
  name: string;
  symbol: string;
  alert_type: 'PRICE_LEVEL' | 'PCR_THRESHOLD' | 'MAX_PAIN_SHIFT' | 'VOLATILITY_SQUEEZE' | 'SUPERTREND_FLIP' | 'OI_BUILDUP';
  condition: 'GREATER_THAN' | 'LESS_THAN' | 'CROSSES_ABOVE' | 'CROSSES_BELOW' | 'EQUALS';
  threshold: number;
  channel?: 'IN_APP' | 'WEBHOOK' | 'TELEGRAM' | 'EMAIL';
  webhook_url?: string | null;
}

export interface AlertRule {
  id: string;
  name: string;
  symbol: string;
  alert_type: 'PRICE_LEVEL' | 'PCR_THRESHOLD' | 'MAX_PAIN_SHIFT' | 'VOLATILITY_SQUEEZE' | 'SUPERTREND_FLIP' | 'OI_BUILDUP';
  condition: 'GREATER_THAN' | 'LESS_THAN' | 'CROSSES_ABOVE' | 'CROSSES_BELOW' | 'EQUALS';
  threshold: number;
  channel: 'IN_APP' | 'WEBHOOK' | 'TELEGRAM' | 'EMAIL';
  webhook_url?: string | null;
  is_active: boolean;
  last_triggered?: string | null;
  created_at: string;
}

export interface AlertTriggerLog {
  id: string;
  alert_id: string;
  alert_name: string;
  symbol: string;
  timestamp: string;
  triggered_value: number;
  threshold_value: number;
  message: string;
  channel_dispatched: string;
}

export interface SystemTelemetry {
  status: 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY';
  uptime_seconds: number;
  memory_usage_mb: number;
  active_workers: Record<string, string>;
  stream_latency_ms: number;
  active_alert_rules_count: number;
  total_alerts_triggered: number;
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

export interface CryptoTicker {
  symbol: string;
  display_name: string;
  base_asset: string;
  quote_asset: string;
  price: number;
  change_24h: number;
  change_percent_24h: number;
  high_24h: number;
  low_24h: number;
  volume_24h_quote: number;
  volume_24h_base: number;
  weighted_avg_price?: number;
  sparkline: number[];
  status: DataStatus;
  provider: string;
  last_updated: string;
}

export interface CryptoOrderBookLevel {
  price: number;
  quantity: number;
  total: number;
}

export interface CryptoOrderBook {
  symbol: string;
  bids: CryptoOrderBookLevel[];
  asks: CryptoOrderBookLevel[];
  spread: number;
  spread_percent: number;
  timestamp: string;
  provider: string;
}

export interface CryptoDerivatives {
  symbol: string;
  mark_price: number;
  index_price: number;
  estimated_settle_price?: number;
  funding_rate: number;
  funding_rate_percent: number;
  next_funding_time: string;
  open_interest_usd: number;
  open_interest_coins: number;
  long_short_ratio: number;
  long_percentage: number;
  short_percentage: number;
  countdown_seconds: number;
  provider: string;
  timestamp: string;
}

export interface CryptoMarketOverview {
  fear_greed_score: number;
  fear_greed_label: string;
  btc_dominance_pct: number;
  total_market_cap_usd: number;
  total_volume_24h_usd: number;
  tracked_pairs_count: number;
  top_gainers: CryptoTicker[];
  top_losers: CryptoTicker[];
  timestamp: string;
  provider: string;
}

