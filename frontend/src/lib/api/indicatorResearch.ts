import type { ApiCore } from './client';

/* ── Metadata ───────────────────────────────────────────────────────────── */

export type ParameterType = 'integer' | 'number' | 'boolean' | 'choice' | 'string';

export type ParameterSpec = {
  name: string;
  type: ParameterType;
  default: number | string | boolean;
  min: number | null;
  max: number | null;
  step: number | null;
  label: string;
  description: string | null;
  options?: string[] | null;
};

export type OutputSpec = {
  name: string;
  role: 'line' | 'histogram' | 'area' | 'marker' | 'band_upper' | 'band_lower' | 'band_middle';
  pane: 'price' | 'separate' | 'none';
  label: string;
  description: string | null;
};

export type IndicatorMetadata = {
  id: string;
  name: string;
  category: string;
  description: string;
  output_type: 'oscillator' | 'overlay' | 'multi_output' | 'signal_only';
  parameters: ParameterSpec[];
  outputs: OutputSpec[];
  requires: string[];
  formula_summary: string;
  version: string;
  tags: string[];
  reference: string | null;
  default_rules: RuleSet | null;
};

export type OperatorDoc = {
  name: string;
  label: string;
  description: string;
  operands: number;
  takes_range: boolean;
};

export type CategoryInfo = { id: string; label: string; count: number };

export type IndicatorCatalog = {
  count: number;
  indicators: IndicatorMetadata[];
  categories: CategoryInfo[];
  operators: OperatorDoc[];
  price_columns: string[];
  instruments: string[];
  timeframes: string[];
  research_only: boolean;
  message: string;
};

/* ── Structured rules ───────────────────────────────────────────────────── */

export type RuleOperand =
  | string
  | number
  | boolean
  | [number, number]
  | { feature: string }
  | { value: number | boolean };

export type RuleCondition = {
  left: RuleOperand;
  operator: string;
  right?: RuleOperand;
  bars?: number;
  enabled?: boolean;
  label?: string | null;
};

export type RuleGroup = {
  operator: 'AND' | 'OR' | 'NOT';
  conditions: Array<RuleCondition | RuleGroup>;
};

export type RuleSet = {
  long?: RuleGroup | null;
  short?: RuleGroup | null;
  use_indicator_defaults?: boolean;
};

export type RuleProblems = {
  available_features?: string[];
  long: string[];
  short: string[];
  source?: string;
  long_summary?: string;
  short_summary?: string;
};

/* ── Requests ───────────────────────────────────────────────────────────── */

export type IndicatorSpecInput = { indicator_id: string; params: Record<string, unknown> };

export type DataSelection = {
  instrument: string;
  timeframe: string;
  start?: string | null;
  end?: string | null;
  version?: string | null;
  max_bars?: number | null;
};

export type ExecutionSettingsInput = {
  entry_fill?: 'next_open' | 'signal_close';
  size_mode?: 'fixed_fraction' | 'fixed_units';
  initial_capital?: number;
  allocation_pct?: number;
  fixed_units?: number;
  leverage?: number;
};

export type ExitSettingsInput = {
  stop_mode?: 'none' | 'percent' | 'atr' | 'points';
  stop_value?: number;
  target_mode?: 'none' | 'percent' | 'atr' | 'points';
  target_value?: number;
  max_bars_held?: number | null;
  exit_on_opposite?: boolean;
  allow_long?: boolean;
  allow_short?: boolean;
  exit_at_session_close?: boolean;
};

export type CostSettingsInput = {
  slippage_bps?: number;
  brokerage_bps?: number;
  exchange_bps?: number;
  sebi_bps?: number;
  gst_on_fees_pct?: number;
  stt_sell_bps?: number;
  stamp_buy_bps?: number;
};

export type BacktestSettingsInput = {
  execution?: ExecutionSettingsInput;
  exits?: ExitSettingsInput;
  costs?: CostSettingsInput;
};

export type ResearchRequest = {
  data: DataSelection;
  indicators: IndicatorSpecInput[];
  rules?: RuleSet;
};

export type BacktestRequest = ResearchRequest & {
  settings?: BacktestSettingsInput;
  verify_causality?: boolean;
  include_trades?: boolean;
  include_equity_curve?: boolean;
  max_equity_points?: number;
};

export type PreviewRequest = ResearchRequest & {
  preview_bars?: number;
  settings?: BacktestSettingsInput;
};

export type OptimizeRequest = ResearchRequest & {
  settings?: BacktestSettingsInput;
  objective?: string;
  search_mode?: 'grid' | 'random';
  seed?: number;
  max_combinations?: number;
  min_trades?: number;
  parameter_overrides?: Record<string, Array<number | string>>;
};

export type SelectivityRequest = ResearchRequest & {
  feature: string;
  operator?: string;
  thresholds: number[];
  direction?: 'long' | 'short';
  settings?: BacktestSettingsInput;
  secondary_rule?: RuleGroup | null;
  forward_horizon?: number;
  min_trades?: number;
};

export type RobustnessRequest = ResearchRequest & {
  settings?: BacktestSettingsInput;
  perturbation_pcts?: number[];
  cost_multipliers?: number[];
};

export type AblationRequest = ResearchRequest & {
  settings?: BacktestSettingsInput;
  objective?: string;
};

export type WalkForwardRequest = OptimizeRequest & { folds?: number; purge_bars?: number };

export type CompareRequest = {
  data: DataSelection;
  indicator_ids: string[];
  rules?: RuleSet;
  use_default_rules?: boolean;
  settings?: BacktestSettingsInput;
  objective?: string;
};

export type CompareRulesRequest = {
  data: DataSelection;
  indicator_id: string;
  rule_sets: Array<RuleSet & { label?: string }>;
  settings?: BacktestSettingsInput;
  objective?: string;
};

export type PredictionRequest = ResearchRequest & {
  horizons?: number[];
  settings?: BacktestSettingsInput;
};

/* ── Responses ──────────────────────────────────────────────────────────── */

export type IsolationReport = {
  isolated: boolean;
  forbidden_import_prefixes: string[];
  violations: { imports: string[]; calls: string[] };
  guarantees: string[];
};

export type DatasetEntry = {
  instrument: string;
  dataset_symbol: string;
  timeframe: string;
  available: boolean;
  source: string;
  versions_on_disk?: string[];
  dataset_id: string | null;
  status: string | null;
  total_candles: number;
  earliest_available_ts: string | null;
  latest_available_ts: string | null;
  quality_score: number | null;
};

export type ResearchCatalog = {
  ok: boolean;
  instruments: string[];
  timeframes: string[];
  entries: DatasetEntry[];
  catalogue_reachable: boolean;
  note: string;
  reference_costs: Record<string, number | string>;
  zero_costs: Record<string, number | string>;
  execution_models: Array<{ id: string; label: string; description: string }>;
  stop_modes: string[];
  objectives: string[];
  research_only: boolean;
  message: string;
};

export type CandleSeriesInfo = {
  instrument: string;
  dataset_symbol: string;
  timeframe: string;
  available: boolean;
  availability: 'available' | 'dataset_missing' | 'empty_range' | 'provider_error';
  reason: string | null;
  source: string;
  version: string | null;
  requested_start: string | null;
  requested_end: string | null;
  data_start: string | null;
  data_end: string | null;
  bars: number;
  truncated: boolean;
  warnings: string[];
};

export type PreviewCandle = {
  index: number;
  time: string | null;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

export type PaneMap = Record<
  string,
  { output_type: string; outputs: Record<string, { role: string; pane: string }> }
>;

export type PreviewResponse = {
  ok: boolean;
  error?: string | null;
  data: CandleSeriesInfo;
  candles: PreviewCandle[];
  outputs: Record<string, Array<number | null>>;
  indicators: Array<{
    indicator_id: string;
    version: string;
    name: string;
    category: string;
    role: string;
    params: Record<string, unknown>;
    outputs: string[];
  }>;
  warmup_bars: number;
  pane_map: PaneMap;
  signals: { long: number[]; short: number[] };
  rule_summary: { long: string; short: string; source: string };
  rule_problems: RuleProblems;
  window: { start_index: number; end_index: number; step: number; bars: number };
  warnings: string[];
  research_only: boolean;
  message: string;
};

export type Metrics = {
  n_trades: number | null;
  n_wins: number | null;
  n_losses: number | null;
  n_breakeven: number | null;
  win_rate_pct: number | null;
  initial_capital: number | null;
  final_equity: number | null;
  net_profit: number | null;
  total_return_pct: number | null;
  gross_profit_before_costs: number | null;
  total_costs: number | null;
  cost_drag_pct: number | null;
  gross_profit: number | null;
  gross_loss: number | null;
  profit_factor: number | null;
  expectancy_per_trade: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  payoff_ratio: number | null;
  largest_win: number | null;
  largest_loss: number | null;
  avg_bars_held: number | null;
  median_bars_held: number | null;
  exposure_pct: number | null;
  max_drawdown_pct: number | null;
  max_drawdown_abs: number | null;
  max_drawdown_duration_bars: number | null;
  sharpe_annualized: number | null;
  sortino_annualized: number | null;
  annualized_return_pct: number | null;
  calmar: number | null;
  max_consecutive_wins: number | null;
  max_consecutive_losses: number | null;
  avg_mae_pct: number | null;
  avg_mfe_pct: number | null;
  mfe_mae_ratio: number | null;
  long_trades: number | null;
  short_trades: number | null;
  bars: number | null;
  undefined_metrics: string[];
  annualization_assumption?: Record<string, unknown>;
};

export type Trade = {
  trade_id: number;
  side: 'LONG' | 'SHORT';
  signal_index: number;
  signal_time: string | null;
  entry_index: number;
  entry_time: string | null;
  entry_price: number;
  entry_reference_price: number;
  exit_index: number | null;
  exit_time: string | null;
  exit_price: number | null;
  exit_reason: string | null;
  quantity: number;
  bars_held: number;
  gross_pnl: number;
  costs: number;
  net_pnl: number;
  return_pct: number;
  mae_pct: number;
  mfe_pct: number;
  stop_price: number | null;
  target_price: number | null;
  equity_after: number;
  regime: string | null;
  time_bucket: string | null;
  holding_bucket: string | null;
};

export type EquityPoint = {
  index: number;
  time: string | null;
  equity: number;
  drawdown_pct: number;
  in_position: boolean;
};

export type ValidationReport = {
  no_lookahead: boolean;
  repaint_free: boolean;
  tested: boolean;
  badge: string;
  scope: string | null;
  samples_checked: number[];
  checks_run: number;
  structural: { passed: boolean; issues: string[] };
  causality: Record<string, unknown>;
  issues: string[];
};

export type GroupedStats = Record<
  string,
  {
    n_trades: number;
    win_rate_pct: number | null;
    net_pnl: number | null;
    avg_net_pnl: number | null;
    profit_factor: number | null;
    avg_bars_held: number | null;
    total_costs: number | null;
    avg_mae_pct: number | null;
    avg_mfe_pct: number | null;
    low_sample: boolean;
  }
>;

export type BacktestResponse = {
  ok: boolean;
  error?: string | null;
  data: CandleSeriesInfo;
  bars?: number;
  indicator_id?: string | null;
  indicator_version?: string | null;
  params?: Record<string, unknown>;
  output_names?: string[];
  settings?: Record<string, unknown>;
  signal_rule_summary?: { long: string; short: string };
  metrics?: Metrics;
  trades?: Trade[];
  trade_count?: number;
  equity_curve?: EquityPoint[];
  equity_curve_thinned?: { original_points: number; returned_points: number; step: number };
  signals?: { long: number[]; short: number[] };
  by_regime?: GroupedStats;
  by_time_of_day?: GroupedStats;
  by_side?: GroupedStats;
  cost_summary?: Record<string, unknown>;
  validation?: ValidationReport;
  assumptions?: string[];
  generated_at?: string;
  feature_build?: Record<string, unknown>;
  rule_source?: string;
  rule_problems?: RuleProblems;
  warnings?: string[];
  order_flow_provenance?: 'REAL' | 'PROXY' | 'UNAVAILABLE' | string;
  order_flow_records_count?: number;
  research_only: boolean;
  message: string;
};

export type OptimizeRow = {
  params: Record<string, number | string>;
  ok: boolean;
  trade_count: number;
  net_profit: number | null;
  total_return_pct: number | null;
  win_rate_pct: number | null;
  profit_factor: number | null;
  max_drawdown_pct: number | null;
  sharpe_annualized: number | null;
  total_costs: number | null;
  insufficient_trades: boolean;
};

export type OptimizeResponse = {
  ok: boolean;
  error?: string | null;
  data: CandleSeriesInfo;
  indicator_id: string;
  objective: string;
  objective_direction: string;
  parameter_space: Record<string, Array<number | string>>;
  combinations_total: number;
  combinations_evaluated: number;
  search_mode?: string;
  multiple_testing_penalty?: number;
  expected_max_null_sharpe?: number;
  deflated_sharpe_ratio?: number;
  parameter_space_size?: number;
  truncated: boolean;
  min_trades: number;
  rows: OptimizeRow[];
  best: OptimizeRow | null;
  in_sample_only: boolean;
  causality_verified: boolean;
  warnings: string[];
  research_only: boolean;
  message: string;
};

export type WalkForwardFold = {
  fold: number;
  train_range: [number, number];
  test_range: [number, number];
  train_bars: number;
  test_bars: number;
  purge_bars: number;
  skipped: boolean;
  skip_reason?: string;
  selected_params?: Record<string, number | string>;
  test_trades?: number;
  test_error?: string | null;
};

export type WalkForwardResponse = {
  ok: boolean;
  error?: string | null;
  data: CandleSeriesInfo;
  indicator_id: string;
  objective: string;
  folds: number;
  folds_completed: number;
  purge_bars: number;
  combinations_per_fold: number;
  parameter_space: Record<string, Array<number | string>>;
  fold_reports: WalkForwardFold[];
  pooled: {
    test_trades: number;
    test_net_profit: number;
    mean_train_objective: number | null;
    mean_test_objective: number | null;
  };
  in_sample_optimism: number | null;
  leakage_audit: Record<string, unknown>;
  warnings: string[];
  research_only: boolean;
  message: string;
};

export type CompareRow = {
  indicator_id: string;
  name?: string;
  category?: string;
  output_type?: string;
  comparable: boolean;
  reason?: string | null;
  rule_source?: string;
  long_rule?: string;
  short_rule?: string;
  trade_count?: number;
  net_profit?: number | null;
  total_return_pct?: number | null;
  win_rate_pct?: number | null;
  profit_factor?: number | null;
  max_drawdown_pct?: number | null;
  sharpe_annualized?: number | null;
  no_lookahead?: boolean | null;
};

export type CompareResponse = {
  ok: boolean;
  error?: string | null;
  data: CandleSeriesInfo;
  objective: string;
  rows: CompareRow[];
  comparable_count: number;
  warnings: string[];
  in_sample_only: boolean;
  note: string;
  research_only: boolean;
  message: string;
};

export type CompareRulesResponse = {
  ok: boolean;
  error?: string | null;
  data: CandleSeriesInfo;
  indicator_id: string;
  objective: string;
  rows: Array<Record<string, unknown> & { label: string; comparable: boolean; reason?: string | null }>;
  spread: { min: number | null; max: number | null; spread: number | null; n: number };
  note: string;
  research_only: boolean;
  message: string;
};

export type ForwardReturnStats = {
  n: number;
  mean_pct: number | null;
  median_pct: number | null;
  stdev_pct: number | null;
  t_stat: number | null;
  p_value_two_sided: number | null;
  positive_rate_pct: number | null;
  is_significant_5pct: boolean;
  low_sample?: boolean;
};

export type HorizonStudy = {
  horizon_bars: number;
  signal: ForwardReturnStats;
  unconditional: ForwardReturnStats;
  excess_mean_pct: number | null;
  excess_positive: boolean;
  overlapping_windows: boolean;
  note: string | null;
};

export type PredictionStudy = {
  instrument?: string;
  timeframe?: string;
  date_range?: Record<string, string | null>;
  signal_definition: string;
  direction?: string;
  n_signals: number;
  n_bars?: number;
  costs_applied?: boolean;
  sample_status?: string;
  horizons: Record<string, HorizonStudy>;
  contexts_required?: string[];
  by_time_of_day?: Record<string, ForwardReturnStats>;
  disclaimer?: string;
  note?: string;
};

export type PredictResponse = {
  ok: boolean;
  error?: string | null;
  data: CandleSeriesInfo;
  rule_summaries: { long: string; short: string };
  studies: { long: PredictionStudy; short: PredictionStudy };
  disclaimer: string;
  research_only: boolean;
  message: string;
};

/* ── Canonical Presets ─────────────────────────────────────────────────── */

export type ResearchPreset = {
  id: string;
  name: string;
  description: string;
  instrument: string;
  timeframe: string;
  order_flow_required: boolean;
  indicators: Array<{
    indicator_id: string;
    params: Record<string, unknown>;
    role: 'primary' | 'overlay';
  }>;
  rules: RuleSet;
  settings: Record<string, unknown>;
};

/* ── Selectivity Analysis ──────────────────────────────────────────────── */

export type SelectivityRow = {
  threshold: number;
  n_signals: number;
  sample_tier: 'SUFFICIENT' | 'MARGINAL' | 'INSUFFICIENT';
  win_rate_pct: number | null;
  profit_factor: number | null;
  total_return_pct: number | null;
  sharpe_annualized: number | null;
  mean_forward_return_pct: number | null;
  excess_return_pct: number | null;
  positive_rate_pct: number | null;
};

export type SelectivityResponse = {
  ok: boolean;
  error?: string | null;
  data: CandleSeriesInfo;
  feature: string;
  operator: string;
  direction: string;
  thresholds: number[];
  rows: SelectivityRow[];
  is_monotonic: boolean;
  optimal_threshold: number | null;
  warnings: string[];
  research_only: boolean;
  message: string;
};

/* ── Robustness & Perturbation ─────────────────────────────────────────── */

export type PerturbationResult = {
  param_name: string;
  original_value: unknown;
  perturbed_value: unknown;
  perturbation_pct: number;
  sharpe_annualized: number | null;
  net_profit: number | null;
  win_rate_pct: number | null;
  trade_count: number;
  sharpe_change_pct: number | null;
};

export type CostStressResult = {
  multiplier: number;
  net_profit: number | null;
  profit_factor: number | null;
  sharpe_annualized: number | null;
  survives: boolean;
};

export type RobustnessResponse = {
  ok: boolean;
  error?: string | null;
  data: CandleSeriesInfo;
  base_metrics: Record<string, number | null>;
  perturbations: PerturbationResult[];
  cost_stress_tests: CostStressResult[];
  stability_score: number;
  cliff_risk_detected: boolean;
  fragile_parameters: string[];
  warnings: string[];
  research_only: boolean;
  message: string;
};

/* ── Multi-Indicator Ablation ──────────────────────────────────────────── */

export type AblationRow = {
  removed_indicator: string;
  remaining_indicators: string[];
  trade_count: number;
  net_profit: number | null;
  win_rate_pct: number | null;
  sharpe_annualized: number | null;
  delta_sharpe: number | null;
  delta_return_pct: number | null;
  is_redundant: boolean;
};

export type AblationResponse = {
  ok: boolean;
  error?: string | null;
  data: CandleSeriesInfo;
  baseline_metrics: Record<string, number | null>;
  rows: AblationRow[];
  redundant_indicators: string[];
  recommendations: string[];
  warnings: string[];
  research_only: boolean;
  message: string;
};

export type ExperimentSummary = {
  id: string;
  name: string | null;
  notes: string | null;
  tags: string[];
  instrument: string | null;
  timeframe: string | null;
  date_range: Record<string, string | null> | null;
  indicator_id: string | null;
  indicator_params: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
  result_summary: Record<string, unknown>;
  validation: Record<string, unknown>;
};

export interface IndicatorResearchApi {
  getIndicatorCatalog(): Promise<IndicatorCatalog>;
  getIndicator(id: string): Promise<{
    ok: boolean;
    metadata: IndicatorMetadata;
    default_rules: RuleSet | null;
    parameter_space: Record<string, Array<number | string>>;
    available_features: string[];
  }>;
  getResearchCatalog(): Promise<ResearchCatalog>;
  getResearchIsolation(): Promise<IsolationReport>;
  listResearchPresets(): Promise<{ ok: boolean; presets: ResearchPreset[] }>;
  getResearchPreset(id: string): Promise<{ ok: boolean; preset: ResearchPreset }>;
  previewFeatures(payload: PreviewRequest): Promise<PreviewResponse>;
  runResearchBacktest(payload: BacktestRequest): Promise<BacktestResponse>;
  runResearchSelectivity(payload: SelectivityRequest): Promise<SelectivityResponse>;
  runResearchRobustness(payload: RobustnessRequest): Promise<RobustnessResponse>;
  runResearchAblation(payload: AblationRequest): Promise<AblationResponse>;
  runResearchOptimize(payload: OptimizeRequest): Promise<OptimizeResponse>;
  runResearchWalkForward(payload: WalkForwardRequest): Promise<WalkForwardResponse>;
  runResearchCompare(payload: CompareRequest): Promise<CompareResponse>;
  runResearchCompareRules(payload: CompareRulesRequest): Promise<CompareRulesResponse>;
  runResearchPredict(payload: PredictionRequest): Promise<PredictResponse>;
  listResearchExperiments(limit?: number): Promise<{ ok: boolean; count: number; experiments: ExperimentSummary[] }>;
  getResearchExperiment(id: string): Promise<{ ok: boolean; experiment: ExperimentSummary & { config: Record<string, unknown> } }>;
  saveResearchExperiment(payload: {
    name?: string | null;
    notes?: string | null;
    tags?: string[];
    config: Record<string, unknown>;
    result_summary?: Record<string, unknown>;
    validation?: Record<string, unknown>;
    data_provenance?: Record<string, unknown>;
  }): Promise<{ ok: boolean; experiment: ExperimentSummary }>;
  renameResearchExperiment(id: string, payload: { name?: string | null; notes?: string | null }): Promise<{ ok: boolean; experiment: ExperimentSummary }>;
  deleteResearchExperiment(id: string): Promise<{ ok: boolean; deleted: string }>;
  getResearchExperimentExportUrl(id: string, format: 'json' | 'csv'): string;
}

const BASE = '/api/v1/indicator-research';

export function createIndicatorResearchApi(core: ApiCore): IndicatorResearchApi {
  return {
    getIndicatorCatalog() {
      return core.request<IndicatorCatalog>(`${BASE}/indicators`);
    },
    getIndicator(id) {
      return core.request(`${BASE}/indicators/${encodeURIComponent(id)}`);
    },
    getResearchCatalog() {
      return core.request<ResearchCatalog>(`${BASE}/catalog`);
    },
    getResearchIsolation() {
      return core.request<IsolationReport>(`${BASE}/isolation`);
    },
    listResearchPresets() {
      return core.request<{ ok: boolean; presets: ResearchPreset[] }>(`${BASE}/presets`);
    },
    getResearchPreset(id) {
      return core.request<{ ok: boolean; preset: ResearchPreset }>(`${BASE}/presets/${encodeURIComponent(id)}`);
    },
    previewFeatures(payload) {
      // A full backtest-grade series plus every indicator output can take a
      // while on 1m data; the default 60s client timeout is too tight.
      return core.request<PreviewResponse>(`${BASE}/features`, {
        method: 'POST',
        body: JSON.stringify(payload),
        timeoutMs: 120_000,
      });
    },
    runResearchBacktest(payload) {
      return core.request<BacktestResponse>(`${BASE}/backtest`, {
        method: 'POST',
        body: JSON.stringify(payload),
        timeoutMs: 180_000,
      });
    },
    runResearchSelectivity(payload) {
      return core.request<SelectivityResponse>(`${BASE}/selectivity`, {
        method: 'POST',
        body: JSON.stringify(payload),
        timeoutMs: 180_000,
      });
    },
    runResearchRobustness(payload) {
      return core.request<RobustnessResponse>(`${BASE}/robustness`, {
        method: 'POST',
        body: JSON.stringify(payload),
        timeoutMs: 300_000,
        retry: 0,
      });
    },
    runResearchAblation(payload) {
      return core.request<AblationResponse>(`${BASE}/ablation`, {
        method: 'POST',
        body: JSON.stringify(payload),
        timeoutMs: 300_000,
        retry: 0,
      });
    },
    runResearchOptimize(payload) {
      return core.request<OptimizeResponse>(`${BASE}/optimize`, {
        method: 'POST',
        body: JSON.stringify(payload),
        timeoutMs: 300_000,
        retry: 0,
      });
    },
    runResearchWalkForward(payload) {
      return core.request<WalkForwardResponse>(`${BASE}/walkforward`, {
        method: 'POST',
        body: JSON.stringify(payload),
        timeoutMs: 300_000,
        retry: 0,
      });
    },
    runResearchCompare(payload) {
      return core.request<CompareResponse>(`${BASE}/compare`, {
        method: 'POST',
        body: JSON.stringify(payload),
        timeoutMs: 300_000,
        retry: 0,
      });
    },
    runResearchCompareRules(payload) {
      return core.request<CompareRulesResponse>(`${BASE}/compare-rules`, {
        method: 'POST',
        body: JSON.stringify(payload),
        timeoutMs: 300_000,
        retry: 0,
      });
    },
    runResearchPredict(payload) {
      return core.request<PredictResponse>(`${BASE}/predict`, {
        method: 'POST',
        body: JSON.stringify(payload),
        timeoutMs: 180_000,
      });
    },
    listResearchExperiments(limit = 100) {
      return core.request(`${BASE}/experiments?limit=${limit}`);
    },
    getResearchExperiment(id) {
      return core.request(`${BASE}/experiments/${encodeURIComponent(id)}`);
    },
    saveResearchExperiment(payload) {
      return core.request(`${BASE}/experiments`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    renameResearchExperiment(id, payload) {
      return core.request(`${BASE}/experiments/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
    },
    deleteResearchExperiment(id) {
      return core.request(`${BASE}/experiments/${encodeURIComponent(id)}`, { method: 'DELETE' });
    },
    getResearchExperimentExportUrl(id, format) {
      return `${core.getBaseUrl()}${BASE}/experiments/${encodeURIComponent(id)}/export?format=${format}`;
    },
  };
}
