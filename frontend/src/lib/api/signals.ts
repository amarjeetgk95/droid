import type { ApiCore } from './client';

/* Client-side level coherence (trigger vs SL vs target per direction).
   Mirrors backend manual_signal_service._validate_levels ordering so the UI
   fails fast instead of waiting for a 400. Partial levels are allowed —
   only fully-specified incoherent triples are rejected. No caching. */

export type LevelCoherenceInput = {
  direction?: string | null;
  trigger?: number | null;
  stopLoss?: number | null;
  target1?: number | null;
  target2?: number | null;
};

/** Direction families the manual pipeline recognises. */
export type DirectionClass = 'CALL' | 'PUT';

/**
 * Classify a direction token into its option family.
 *
 * PUT is checked first on purpose: `LONG_PUT` contains `LONG`, so a CALL-first
 * matcher captured every LONG_PUT as a call and rejected PUT setups client-side
 * before any HTTP request (bug: "CALL levels incoherent" on PUT signals).
 */
export function classifyDirection(direction?: string | null): DirectionClass {
  const dir = String(direction ?? '').toUpperCase();
  if (dir.includes('PUT') || dir.includes('BEAR') || dir.includes('SHORT') || dir.includes('SELL')) {
    return 'PUT';
  }
  return 'CALL';
}

export function checkLevelCoherence(input: LevelCoherenceInput): {
  coherent: boolean;
  reason: string | null;
} {
  const num = (v: unknown): number | null => {
    if (v === null || v === undefined || v === '') return null;
    const n = typeof v === 'number' ? v : Number(v);
    return typeof n === 'number' && Number.isFinite(n) ? n : null;
  };
  const trigger = num(input.trigger);
  const sl = num(input.stopLoss);
  const t1 = num(input.target1);
  const t2 = num(input.target2);
  // Incomplete level sets cannot be judged incoherent client-side.
  if (trigger === null || sl === null || t1 === null || t2 === null) {
    return { coherent: true, reason: null };
  }
  if (classifyDirection(input.direction) === 'PUT') {
    const ok = sl > trigger && t1 < trigger && t2 < t1;
    return ok
      ? { coherent: true, reason: null }
      : { coherent: false, reason: 'PUT levels incoherent: need SL > trigger > T1 > T2.' };
  }
  // Default to CALL ordering (backend does the same for LONG_CALL).
  const ok = sl < trigger && t1 > trigger && t2 > t1;
  return ok
    ? { coherent: true, reason: null }
    : { coherent: false, reason: 'CALL levels incoherent: need SL < trigger < T1 < T2.' };
}

/**
 * Live-index spot corridors (mirrors backend
 * `manual_signal_service.INDEX_PLAUSIBLE_RANGES`). Cross-instrument values —
 * e.g. a leftover BANKNIFTY 51,280 submitted for SENSEX — are rejected before
 * the request instead of being accepted into a doomed signal.
 */
export const INDEX_CORRIDORS: Record<string, readonly [number, number]> = {
  NIFTY: [22000, 35000],
  BANKNIFTY: [40000, 75000],
  SENSEX: [70000, 120000],
};

export type LevelCorridorInput = {
  trigger?: number | null;
  stopLoss?: number | null;
  target1?: number | null;
  target2?: number | null;
};

/**
 * Check provided levels against the instrument's plausible corridor.
 * Unknown instruments pass (the backend still validates); partial level sets
 * are checked field-by-field — any provided out-of-range value fails.
 */
export function checkInstrumentCorridor(
  underlying: string,
  levels: LevelCorridorInput,
): { ok: boolean; reason: string | null } {
  const range = INDEX_CORRIDORS[String(underlying ?? '').toUpperCase()];
  if (!range) return { ok: true, reason: null };
  const [min, max] = range;
  const fields: Array<[keyof LevelCorridorInput, string, number | null | undefined]> = [
    ['trigger', 'Trigger', levels.trigger],
    ['stopLoss', 'Stop loss', levels.stopLoss],
    ['target1', 'Target 1', levels.target1],
    ['target2', 'Target 2', levels.target2],
  ];
  const invalid: string[] = [];
  for (const [key, label, raw] of fields) {
    void key;
    if (raw === null || raw === undefined) continue;
    const n = Number(raw);
    if (!Number.isFinite(n) || n < min || n > max) {
      invalid.push(`${label} ${Number.isFinite(n) ? n : String(raw)}`);
    }
  }
  if (invalid.length > 0) {
    return {
      ok: false,
      reason: `${invalid.join(', ')} outside the ${String(underlying).toUpperCase()} corridor [${min}, ${max}].`,
    };
  }
  return { ok: true, reason: null };
}

/** Strategy entry as published by `GET /api/v1/signals/engines`. */
export interface SignalEngineStrategy {
  id: string;
  label?: string;
  description?: string;
}

/** Candidate levels as published by `POST /api/v1/signals/auto-detect`. */
export interface AutoDetectCandidate {
  underlying?: string;
  strategy?: string;
  direction?: string;
  timeframe?: string;
  spot_price?: number | string | null;
  trigger?: number | string | null;
  trigger_level?: number | string | null;
  stop_loss?: number | string | null;
  target_1?: number | string | null;
  target_2?: number | string | null;
  entry_min?: number | string | null;
  entry_max?: number | string | null;
  confidence?: number | null;
  overall_confidence?: number | null;
  technical_score?: number | null;
  mtf_score?: number | null;
  fno_score?: number | null;
  regime_score?: number | null;
  ai_score?: number | null;
  confluence_factors?: string[];
  rationale?: string[];
  [key: string]: unknown;
}

export interface AutoDetectResponse {
  detected: boolean;
  candidate: AutoDetectCandidate | null;
  message: string;
}

/**
 * One row of the authoritative audit ledger, as served by
 * `GET /api/v1/signals/audit`. Mirrors `backend/app/signals/audit_ledger.py`
 * `AuditTradeRecord`: planned levels, paper fill, exit economics (`exit_price`,
 * `actual_fill_price`, `actual_pnl_inr`, `total_pnl_inr`), live MTM, mark
 * provenance (`mark_source`, `economics_unavailable`) and the unified
 * `status`/`fsm_state` domain pair. `created_at_str`/`exited_at_utc` carry the
 * audit's IST display timestamp and raw exit epoch.
 */
export interface AuditTradeRecord {
  audit_id: string;
  signal_id: string;
  underlying: string;
  strategy: string;
  direction: string;
  timeframe: string;
  // Contract specs
  option_symbol?: string | null;
  option_type?: string | null;
  option_strike?: number | null;
  expiry?: string | null;
  lot_size: number;
  lots: number;
  quantity: number;
  // Planned signal levels
  spot_price_at_creation: number;
  trigger_price: number;
  entry_min: number;
  entry_max: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
  risk_points: number;
  risk_reward_t1: number;
  risk_reward_t2: number;
  confidence: number;
  is_scalp: boolean;
  signal_type: string;
  // Paper execution details
  paper_order_id?: string | null;
  paper_side?: string | null;
  actual_fill_price?: number | null;
  executed_at_utc?: number | null;
  slippage_points?: number | null;
  margin_used?: number | null;
  // Exit & square-off details
  exit_price?: number | null;
  exited_at_utc?: number | null;
  exit_reason?: string | null;
  holding_time_seconds?: number | null;
  holding_time_str?: string | null;
  // Actual profit & loss (audited)
  actual_pnl_inr?: number | null;
  actual_pnl_points?: number | null;
  actual_pnl_pct?: number | null;
  theoretical_pnl_points?: number | null;
  theoretical_pnl_inr?: number | null;
  // Live mark-to-market
  current_price?: number | null;
  unrealized_pnl_inr?: number | null;
  unrealized_pnl_points?: number | null;
  unrealized_pnl_pct?: number | null;
  total_pnl_inr?: number | null;
  live_duration_seconds?: number | null;
  live_duration_str?: string | null;
  // Mark provenance / fail-closed economics
  mark_source?: string | null;
  mark_age_ms?: number | null;
  mark_note?: string | null;
  economics_unavailable: boolean;
  // Unified status (ledger display) + canonical FSM state
  status: string;
  fsm_state?: string | null;
  outcome_label?: string | null;
  is_winner?: boolean | null;
  source?: string | null;
  chain_revalidated: boolean;
  // Timestamps
  created_at_utc: number;
  created_at_str: string;
  executed_at_str?: string | null;
  updated_at_utc: number;
}

/** Per-strategy / per-underlying aggregate inside {@link AuditSummary}. */
export interface AuditBreakdownRow {
  total: number;
  wins: number;
  losses: number;
  net_pnl: number;
  win_rate: number;
}

/**
 * Ledger-wide aggregates from `AuditTradeLedger.get_summary_metrics()` —
 * `total_signals_audited` plus the win-rate, P&L, exposure and profit-factor
 * fields the desk renders.
 */
export interface AuditSummary {
  total_signals_audited: number;
  open_trades: number;
  closed_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  net_realized_pnl_inr: number;
  net_unrealized_pnl_inr: number;
  total_pnl_inr: number;
  live_winning_trades: number;
  live_losing_trades: number;
  total_active_exposure_inr: number;
  gross_profit_inr: number;
  gross_loss_inr: number;
  profit_factor: number;
  max_win_inr: number;
  max_loss_inr: number;
  avg_trade_pnl_inr: number;
  avg_holding_time_seconds: number;
  strategy_breakdown: Record<string, AuditBreakdownRow>;
  underlying_breakdown: Record<string, AuditBreakdownRow>;
  realtime_sync_ts: number;
}

export function createSignalsApi(core: ApiCore) {
  return {
    async autoDetectSignal(payload: { underlying: string; strategy?: string; timeframe?: string }) {
      return core.request<AutoDetectResponse>(`/api/v1/signals/auto-detect`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async bulkDeleteSignals(payload: {
      signal_ids?: string[];
      before_ms?: number;
      underlying?: string;
      strategy?: string;
      status?: string;
      delete_all?: boolean;
      confirm_all?: boolean;
    }) {
      return core.request<{ status: string; message: string; deleted_count: number; deleted_ids: string[]; requested_count: number }>(
        `/api/v1/signals/bulk-delete`,
        { method: 'POST', body: JSON.stringify(payload) },
      );
    },

    async deleteSignal(signalId: string) {
      return core.request<{ status: string; message: string; fsm_deleted: boolean; audit_deleted: boolean }>(
        `/api/v1/signals/${encodeURIComponent(signalId)}`,
        { method: 'DELETE' },
      );
    },

    async executeSignalPaper(
      signalId: string,
      lots?: number,
      riskPercent?: number,
      opts?: { allowClosedMarket?: boolean },
    ) {
      return core.request<{ success: boolean; signal_id: string; quantity: number; lots: number; fill_price: number; order_id: string; message: string }>(
        `/api/v1/signals/${encodeURIComponent(signalId)}/execute-paper`,
        {
          method: 'POST',
          // allow_closed_market is an explicit operator confirm flag: the
          // backend still enforces the session guard unless it opts in.
          body: JSON.stringify({
            lots,
            risk_percent: riskPercent,
            ...(opts?.allowClosedMarket ? { allow_closed_market: true } : {}),
          }),
        },
      );
    },

    /**
     * Authoritative manual signal generation.
     *
     * `opts.idempotencyKey` is forwarded as the `Idempotency-Key` header: a
     * retried request returns the original signal instead of registering a
     * duplicate. Callers should keep the key stable across retries of the
     * same payload (see SignalBuilder's confirm step).
     */
    async generateSignal(payload: Record<string, any>, opts?: { idempotencyKey?: string }) {
      // Client-side level coherence pre-check (trigger vs SL vs target per
      // direction). The backend re-validates authoritatively; this fails fast
      // in the UI with the same ordering rule instead of a 400 round-trip.
      const coherence = checkLevelCoherence({
        direction: (payload.direction ?? payload.bias ?? '') as string,
        trigger: (payload.trigger ?? payload.trigger_level ?? payload.trigger_price ?? null) as number | null,
        stopLoss: (payload.stop_loss ?? payload.sl ?? payload.stop ?? null) as number | null,
        target1: (payload.target_1 ?? payload.target1 ?? payload.t1 ?? null) as number | null,
        target2: (payload.target_2 ?? payload.target2 ?? payload.t2 ?? null) as number | null,
      });
      if (!coherence.coherent) {
        throw new Error(coherence.reason ?? 'Incoherent levels');
      }
      const idempotencyKey = opts?.idempotencyKey?.trim();
      const headers: Record<string, string> = {};
      if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
      return core.request<{
        success: boolean;
        signal: any;
        paper_order: any;
        paper_status?: string;
        paper_error?: string | null;
        telegram: { enqueued: number; status?: string; error?: string };
        sse?: Record<string, unknown>;
        sizing?: Record<string, unknown> | null;
        deduplicated?: boolean;
        idempotency_key?: string;
      }>(
        `/api/v1/signals/generate`,
        {
          method: 'POST',
          body: JSON.stringify(payload),
          ...(idempotencyKey ? { headers } : {}),
        },
      );
    },

    async getSignal(signalId: string) {
      return core.request<any>(`/api/v1/signals/${encodeURIComponent(signalId)}`);
    },

    async getSignalDeepDive(signalId: string) {
      return core.request<any>(`/api/v1/signals/${encodeURIComponent(signalId)}/deep-dive`);
    },

    async getSingleSignalAudit(signalId: string) {
      return core.request<any>(`/api/v1/signals/${encodeURIComponent(signalId)}/audit`);
    },

    async getSignalEngines() {
      return core.request<{
        approved_universe: string[];
        broker: string;
        strategies: Array<SignalEngineStrategy | string>;
      }>(`/api/v1/signals/engines`);
    },

    async getSignalsActive(params?: { instrument?: string; status?: string; strategy?: string; desk?: string; is_scalp?: boolean }) {
      const qs = new URLSearchParams();
      if (params?.instrument) qs.set('instrument', params.instrument);
      if (params?.status) qs.set('status', params.status);
      if (params?.strategy) qs.set('strategy', params.strategy);
      if (params?.desk) qs.set('desk', params.desk);
      if (params?.is_scalp !== undefined) qs.set('is_scalp', String(params.is_scalp));
      const q = qs.toString() ? `?${qs.toString()}` : '';
      return core.request<{ signals: any[]; count: number; timestamp_ms: number }>(`/api/v1/signals/active${q}`);
    },

    async getSignalsAudit(params?: { underlying?: string; strategy?: string; status?: string; limit?: number }) {
      const qs = new URLSearchParams();
      if (params?.underlying) qs.set('underlying', params.underlying);
      if (params?.strategy) qs.set('strategy', params.strategy);
      if (params?.status) qs.set('status', params.status);
      if (params?.limit) qs.set('limit', String(params.limit));
      const q = qs.toString() ? `?${qs.toString()}` : '';
      return core.request<{
        trades: AuditTradeRecord[];
        count: number;
        summary: AuditSummary;
        feed_health?: Record<string, unknown>;
        timestamp_ms: number;
      }>(`/api/v1/signals/audit${q}`);
    },

    async sanitizeSignalsAudit() {
      return core.request<{ status: string; db_restored_repaired: number; memory_sanitized: number; summary: AuditSummary; timestamp_ms: number }>(
        `/api/v1/signals/audit/sanitize`,
        { method: 'POST' }
      );
    },

    async getSignalsHistory(limit = 20) {
      return core.request<{ records: any[] }>(`/api/v1/signals/history?limit=${limit}`);
    },

    async getSignalsPerformance() {
      return core.request<{
        total_signals: number;
        active_signals: number;
        completed_signals: number;
        winning_signals: number;
        losing_signals: number;
        win_rate_pct: number | null;
        profit_factor: number | null;
        average_rr: number | null;
        expectancy_r: number | null;
        target_1_hits: number;
        target_2_hits: number;
        stop_loss_hits: number;
        strategy_breakdown: Record<string, any>;
        underlying_breakdown: Record<string, any>;
      }>(`/api/v1/signals/performance`);
    },

    async getSignalsScanner(desk?: string) {
      const qs = desk ? `?desk=${desk}` : '';
      return core.request<{ scanned_underlyings: string[]; total_candidates: number; new_signals: any[]; active_signals: any[]; timestamp_ms: number }>(
        `/api/v1/signals/scanner${qs}`
      );
    },

    async getSignalsStatus() {
      return core.request<{
        active_count: number;
        confirmed_count: number;
        armed_count: number;
        diagnostics: Record<string, unknown>;
        timestamp_ms: number;
      }>(`/api/v1/signals/status`);
    },

    /**
     * Preview the Telegram rendering of a payload. Never persisted, never
     * market-validated. Accepts an AbortSignal so keystroke-driven callers can
     * cancel superseded requests.
     */
    async previewSignal(payload: Record<string, any>, opts?: { signal?: AbortSignal }) {
      return core.request<{
        preview: string;
        event: any;
        event_type: string;
        instrument: string;
        disclaimer?: string;
        persisted?: boolean;
        market_validated?: boolean;
      }>(`/api/v1/signals/preview`, {
        method: 'POST',
        body: JSON.stringify(payload),
        ...(opts?.signal ? { signal: opts.signal } : {}),
      });
    },

    async setPaperWalletCapital(capital: number) {
      return core.request<{ status: string; data: any; capital: number; available_margin: number }>(
        `/api/v1/signals/paper-wallet`,
        {
          method: 'POST',
          body: JSON.stringify({ capital }),
        },
      );
    },

    async getPortfolioStrategies() {
      return core.request<{
        scalp_desk: string[];
        intraday_desk: string[];
        all_active_strategies: string[];
        strategy_count: number;
      }>(`/api/v1/signals/portfolio-strategies`);
    },

    async getSignalsKillSwitch() {
      return core.request<{
        active: boolean;
        triggered_at?: string;
        reason?: string;
        by?: string;
      }>(`/api/v1/signals/kill-switch`);
    },

    async toggleSignalsKillSwitch(active: boolean, reason = 'Operator manual control') {
      return core.request<Record<string, unknown>>(`/api/v1/signals/kill-switch`, {
        method: 'POST',
        body: JSON.stringify({ active, reason }),
      });
    },

    async getSignalsFeedHealth() {
      return core.request<{
        states: Record<string, string>;
        overall_status?: string;
        [key: string]: unknown;
      }>(`/api/v1/signals/feed-health`);
    },

    async voidAuditTrades(signalIds: string[], reason = 'VOID_CORRUPT_HISTORY') {
      return core.request<{
        voided_count: number;
        voided_ids: string[];
        message: string;
      }>(`/api/v1/signals/audit/void`, {
        method: 'POST',
        body: JSON.stringify({ signal_ids: signalIds, reason }),
      });
    },
  };
}

export type SignalsApi = ReturnType<typeof createSignalsApi>;
