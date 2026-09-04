// AI Deep Insight Module Types — v2 spec frontend implementation

export type DeepInsightRegime = 'TREND' | 'RANGE' | 'BREAKOUT' | 'REVERSAL' | 'HIGH_VOLATILITY' | 'LOW_VOLATILITY' | 'UNKNOWN';
export type DeepInsightDirection = 'BULLISH' | 'BEARISH' | 'NEUTRAL';
export type DeepInsightVolatility = 'LOW' | 'NORMAL' | 'HIGH';
export type DeepInsightSetupType = 'BREAKOUT' | 'CONTINUATION' | 'REVERSAL' | 'MEAN_REVERSION' | 'SCALPING' | 'MOMENTUM' | 'PULLBACK' | 'GAP_FILL' | 'VOLATILITY_CONTRACTION';
export type DeepInsightDecision = 'LONG' | 'SHORT' | 'NO_TRADE';
export type DeepInsightSignalStateType = 'ANALYZING' | 'ACTIVE' | 'VALIDATING' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'SUPERSEDED' | 'AI_UNAVAILABLE';
export type DeepInsightSignalStatus = DeepInsightSignalStateType;
export type DeepInsightValidationStatus = 'ACCEPT' | 'REJECT' | 'PASS';
export type DeepInsightSampleQuality = 'GOOD' | 'FAIR' | 'POOR';

export interface DeepInsightTimeframeEntry {
  timeframe: string;
  direction: DeepInsightDirection;
  strength: number;
  structure: string;
}

export interface DeepInsightMarketLevels {
  current_price: number;
  vwap: number;
  support: number;
  resistance: number;
  vwap_relation: 'Above' | 'Below' | 'At';
}

export interface DeepInsightMomentum {
  status: string;
  value: number;
}

export interface DeepInsightVolume {
  relative_value: number;
  status: 'High' | 'Normal' | 'Low';
}

export interface DeepInsightMarket {
  regime: DeepInsightRegime;
  direction: DeepInsightDirection;
  regime_strength: number;
  volatility: DeepInsightVolatility;
  levels: DeepInsightMarketLevels;
  momentum: DeepInsightMomentum;
  volume: DeepInsightVolume;
}

export interface DeepInsightOptionsEvidence {
  bias: DeepInsightDirection;
  pcr: number;
  put_support: number;
  call_resistance: number;
  oi_trend: 'Increasing' | 'Decreasing' | 'Stable';
  iv: string;
  interpretation: string;
}

export interface DeepInsightHistoricalEvidence {
  similar_states: number;
  continuation: number;
  failure: number;
  reversal: number;
  median_move: number;
  median_duration: string;
  sample_quality: DeepInsightSampleQuality;
}

export interface DeepInsightSetup {
  setup_type: DeepInsightSetupType;
  entry_zone: string;
  stop_loss: number;
  target: string;
  risk_reward: number;
}

export interface DeepInsightSignalState {
  state: DeepInsightSignalStateType;
  age: number;
  ttl: number;
  ttl_remaining: number;
}

export interface DeepInsightValidation {
  status: DeepInsightValidationStatus;
  rejection_reason: string | null;
}

export interface DeepInsightProvider {
  name: string;
  model: string;
  latency_ms: number;
}

export interface DeepInsightDataQuality {
  completeness: number;
  status: 'Complete' | 'Partial' | 'Incomplete';
}

export interface DeepInsightAiView {
  bias: DeepInsightDecision;
  confidence: number;
  calibrated_confidence: number;
  setup_type: DeepInsightSetupType;
  summary: string;
}

export interface DeepInsightTechnicalEvidence {
  positive: string[];
  supporting: string[];
}

export interface DeepInsightRisks {
  positive_factors: string[];
  main_risks: string[];
}

export interface DeepInsightPayload {
  symbol: string;
  timestamp: string;
  market: DeepInsightMarket;
  regime: DeepInsightRegime;
  multi_timeframe: DeepInsightTimeframeEntry[];
  ai_view: DeepInsightAiView | Record<string, never>;
  technical_evidence: DeepInsightTechnicalEvidence | Record<string, never>;
  options_evidence: DeepInsightOptionsEvidence;
  historical_evidence: DeepInsightHistoricalEvidence;
  setup: DeepInsightSetup;
  risks: DeepInsightRisks | Record<string, never>;
  invalidation: string[];
  signal_state: DeepInsightSignalState;
  data_quality: DeepInsightDataQuality;
  validation: DeepInsightValidation;
  provider: DeepInsightProvider;
  error: string | null;
}

export interface DeepInsightApiResponse {
  data: DeepInsightPayload;
  error: string | null;
  meta: {
    provider: string;
    timestamp: string;
    status: string;
  };
}
