// AI Deep Insight Module Types
// Per v2 spec frontend implementation

export type DeepInsightRegime = 'TREND' | 'RANGE' | 'BREAKOUT' | 'REVERSAL' | 'HIGH_VOLATILITY' | 'LOW_VOLATILITY' | 'UNKNOWN';
export type DeepInsightDirection = 'BULLISH' | 'BEARISH' | 'NEUTRAL';
export type DeepInsightVolatility = 'LOW' | 'NORMAL' | 'HIGH';
export type DeepInsightSetupType = 'BREAKOUT' | 'CONTINUATION' | 'REVERSAL' | 'MEAN_REVERSION' | 'SCALPING';
export type DeepInsightDecision = 'LONG' | 'SHORT' | 'NO_TRADE';
export type DeepInsightSignalState = 'ANALYZING' | 'ACTIVE' | 'VALIDATING' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'SUPERSEDED' | 'AI_UNAVAILABLE';
export type DeepInsightValidationStatus = 'ACCEPT' | 'REJECT';
export type DeepInsightSampleQuality = 'GOOD' | 'FAIR' | 'POOR';

export interface DeepInsightTimeframe {
  timeframe: string;
  direction: DeepInsightDirection;
  strength: number;
  structure: string;
}

export interface DeepInsightMarketLevels {
  currentPrice: number;
  vwap: number;
  support: number;
  resistance: number;
  vwapRelation: 'Above' | 'Below' | 'At';
}

export interface DeepInsightMomentum {
  status: string;
  value: number;
  relation: string;
}

export interface DeepInsightVolume {
  relativeValue: number;
  comparison: string;
  status: 'High' | 'Normal' | 'Low';
}

export interface DeepInsightOptions {
  bias: DeepInsightDirection;
  pcr: number;
  putSupport: number;
  callResistance: number;
  oiTrend: 'Increasing' | 'Decreasing' | 'Stable';
  iv: string;
  interpretation: string;
}

export interface DeepInsightHistorical {
  similarStates: number;
  continuation: number;
  failure: number;
  reversal: number;
  medianMove: number;
  medianDuration: string;
  sampleQuality: DeepInsightSampleQuality;
}

export interface DeepInsightRisk {
  mainRisks: string[];
  invalidation: string[];
}

export interface DeepInsightEvidence {
  positive: string[];
  supporting: string[];
}

export interface DeepInsightSetup {
  entryZone: string;
  stopLoss: number;
  target: string;
  riskReward: number;
  setupType: DeepInsightSetupType;
}

export interface DeepInsightValidation {
  decision: DeepInsightValidationStatus;
  rejectionReason: string | null;
  rejectionDetail: string | null;
}

export interface DeepInsightProvider {
  name: string;
  model: string;
  latencyMs: number;
}

export interface DeepInsightDataQuality {
  completeness: number;
  status: 'Complete' | 'Partial' | 'Incomplete';
}

export interface DeepInsightSignal {
  signalId: string;
  symbol: string;
  timestamp: string;
  state: DeepInsightSignalState;
  age: number;
  ttl: number;
  ttlRemaining: number;
  regime: DeepInsightRegime;
  direction: DeepInsightDirection;
  volatility: DeepInsightVolatility;
  aiBias: DeepInsightDecision;
  confidence: number;
  calibratedConfidence: number;
  setupType: DeepInsightSetupType;
  timeframe: string;
}

export interface DeepInsightMarket {
  summary: string;
  regime: DeepInsightRegime;
  direction: DeepInsightDirection;
  regimeStrength: number;
  volatility: DeepInsightVolatility;
  levels: DeepInsightMarketLevels;
  momentum: DeepInsightMomentum;
  volume: DeepInsightVolume;
}

export interface DeepInsightExecution {
  decision: 'PASS' | 'REJECT';
  reasonCode: string | null;
  reasonDetail: string | null;
}

export interface DeepInsightState {
  status: 'idle' | 'loading' | 'success' | 'error' | 'stale' | 'expired' | 'unavailable';
  market: DeepInsightMarket | null;
  signal: DeepInsightSignal | null;
  multiTimeframe: DeepInsightTimeframe[];
  options: DeepInsightOptions | null;
  historical: DeepInsightHistorical | null;
  evidence: DeepInsightEvidence | null;
  risk: DeepInsightRisk | null;
  setup: DeepInsightSetup | null;
  validation: DeepInsightValidation | null;
  execution: DeepInsightExecution | null;
  provider: DeepInsightProvider | null;
  dataQuality: DeepInsightDataQuality | null;
  lastUpdated: string | null;
  error: string | null;
  staleMessage: string | null;
}

export interface DeepInsightApiResponse {
  data: {
    signal: AISignalApi;
    execution: ExecutionDecisionApi;
  };
  error: string | null;
  meta: {
    provider: string;
    timestamp: string;
    status: string;
  };
}

export interface AISignalApi {
  signal_id: string;
  symbol: string;
  timestamp: string;
  decision: DeepInsightDecision;
  setup_type: DeepInsightSetupType;
  regime: DeepInsightRegime;
  direction: DeepInsightDirection;
  raw_confidence: number;
  calibrated_confidence: number;
  entry: number;
  stop_loss: number;
  target: number;
  ttl_seconds: number;
  expires_at: string | null;
  validation_result: DeepInsightValidationStatus;
  rejection_reason_code: string | null;
  rejection_detail: string | null;
  provider: string;
  model: string;
  latency_ms: number;
  reasons: string[];
  invalidation: string[];
}

export interface ExecutionDecisionApi {
  decision: 'PASS' | 'REJECT';
  reason_code: string | null;
  reason_detail: string | null;
  signal_id: string;
  order_request?: {
    signal_id: string;
    symbol: string;
    side: string;
    entry: number;
    stop_loss: number;
    target: number;
    quantity: number;
  };
}
