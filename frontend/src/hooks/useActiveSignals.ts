'use client';

import { useCallback, useEffect, useMemo, useRef, useState, useContext } from 'react';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { usePolling } from '@/hooks/usePolling';
import { SignalStreamContext } from '@/context/SignalStreamContext';
import type { SignalsStreamEvent } from './useSignalsStream';
import { fmtNum } from '@/components/ui/desk';

export const SIGNAL_STATUSES = [
  'ACTIVE',
  'TRIGGERED',
  'TARGET_REACHED',
  'STOPPED_OUT',
  'EXPIRED',
] as const;

export type SignalStatus = (typeof SIGNAL_STATUSES)[number];

/**
 * Standardized FSM status mapping:
 * DETECTED, VALIDATED, ARMED, CONFIRMED, TRIGGERED, TARGET_*_HIT, STOP_LOSS_HIT, EXPIRED, INVALIDATED
 */
export const FSM_STATUS_MAP: Record<string, SignalStatus> = {
  DETECTED: 'ACTIVE',
  VALIDATED: 'ACTIVE',
  ARMED: 'ACTIVE',
  CONFIRMED: 'ACTIVE',
  TRIGGERED: 'TRIGGERED',
  TARGET_1_HIT: 'TARGET_REACHED',
  TARGET_2_HIT: 'TARGET_REACHED',
  TARGET_REACHED: 'TARGET_REACHED',
  STOP_LOSS_HIT: 'STOPPED_OUT',
  STOPPED_OUT: 'STOPPED_OUT',
  TIME_STOP_HIT: 'EXPIRED',
  RUNNER_TIME_STOP_HIT: 'EXPIRED',
  EXPIRED: 'EXPIRED',
  INVALIDATED: 'EXPIRED',
};

/**
 * Coerce a backend state into the known badge set.
 * Keeps badge union closed for unknown tokens.
 */
export function toSignalStatus(raw: unknown): SignalStatus {
  const upper = String(raw ?? '').toUpperCase();
  if (!upper) return 'ACTIVE';
  if (FSM_STATUS_MAP[upper]) return FSM_STATUS_MAP[upper];
  return (SIGNAL_STATUSES as readonly string[]).includes(upper)
    ? (upper as SignalStatus)
    : 'ACTIVE';
}

function toMsEpoch(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v > 1e12 ? Math.round(v) : Math.round(v * 1000);
  }
  return null;
}

/**
 * Parse signal time with strict fail-closed precedence:
 * timestamp_ms -> created_at_utc -> timestamp -> created_at (ISO string).
 * Never fabricates Date.now() when called directly.
 */
export function parseSignalTime(s: any, _idx?: number): number | null {
  const fromMs = toMsEpoch(s?.timestamp_ms);
  if (fromMs !== null) return fromMs;
  const fromUtc = toMsEpoch(s?.created_at_utc);
  if (fromUtc !== null) return fromUtc;
  const fromTs = toMsEpoch(s?.timestamp);
  if (fromTs !== null) return fromTs;
  if (s?.created_at) {
    const t = new Date(s.created_at).getTime();
    if (Number.isFinite(t)) return t;
  }
  return null;
}

/**
 * Calculates risk-reward ratio without division-by-zero or infinite values.
 * Returns capped ratio <= 99.
 */
export function calcRiskReward(entry: unknown, sl: unknown, t1: unknown): number {
  const e = Number(entry);
  const stop = Number(sl);
  const target = Number(t1);
  if (!Number.isFinite(e) || !Number.isFinite(stop) || !Number.isFinite(target)) return 1;
  const risk = Math.abs(e - stop);
  const reward = Math.abs(target - e);
  if (risk === 0 || !Number.isFinite(risk) || !Number.isFinite(reward)) return 1;
  const rr = reward / risk;
  if (!Number.isFinite(rr)) return 1;
  return Math.min(99, Number(rr.toFixed(1)));
}

/**
 * Returns true if auto executed or paper order is placed.
 */
export function parseAutoExecuted(s: any): boolean {
  if (Boolean(s?.paper_order_id ?? s?.is_auto_executed ?? s?.isAutoExecuted ?? false)) return true;
  const po = s?.paper_order;
  return typeof po === 'object' && po !== null && !Array.isArray(po);
}

function pickPositiveNum(...vals: unknown[]): number | null {
  for (const v of vals) {
    const n = toNumber(v, { rejectBlankString: true });
    if (n !== null && n > 0) return n;
  }
  return null;
}

function toNullableNum(v: unknown): number | null {
  return toNumber(v, { rejectBlankString: true });
}

function toNullableQuality(v: unknown): string | null {
  if (typeof v !== 'string') return null;
  const s = v.trim().toUpperCase();
  return s ? s : null;
}

export function formatTtlSeconds(v: number | null): string {
  if (v === null) return '—';
  const s = Math.round(v);
  if (s <= 0) return 'expired';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function formatDistanceLabel(pts: number | null, pct: number | null): string | null {
  if (pts === null && pct === null) return null;
  if (pts !== null && pts === 0) return 'at trigger';
  const parts: string[] = [];
  if (pts !== null) parts.push(`${fmtNum(pts, 1)} pts`);
  if (pct !== null) parts.push(`${fmtNum(pct, 2)}%`);
  return `${parts.join(' · ')} to trigger`;
}

export const SIGNAL_SSE_REFRESH_EVENTS = new Set([
  'signal_created',
  'signal_deleted',
  'signals_bulk_deleted',
  'signal_confirmed',
  'signal_triggered',
  'signal_outcome',
  'signal_staged_exit',
  'signal_breakeven',
  'paper_execution',
  'scanner_update',
]);

export function shouldRefreshSignalsOnEvent(evt: string): boolean {
  if (!evt) return false;
  if (evt === 'FEED_STATUS' || evt === 'audit_pnl_update') return false;
  if (SIGNAL_SSE_REFRESH_EVENTS.has(evt)) return true;
  return evt.startsWith('signal_') || evt.startsWith('fsm');
}

export function shouldRefreshVerdictOnSignalEvent(evt: string): boolean {
  return (
    evt === 'signal_created' ||
    evt === 'signal_confirmed' ||
    evt === 'signal_triggered' ||
    evt === 'signal_outcome' ||
    evt === 'paper_execution'
  );
}

/**
 * Standard unified active signal row representing both War Room and Command Center models.
 */
export interface StandardActiveSignal {
  id: string;
  signal_id: string;
  timestamp: number;
  createdAtStr: string | null;
  created_at_str: string | null;
  direction: 'BUY' | 'SELL';
  rawDirection: string;
  instrument: string;
  underlying: string;
  contract?: string;
  strategy: string;
  entry: number;
  trigger: number | null;
  stopLoss: number;
  stop_loss: number | null;
  target1: number;
  target_1: number | null;
  target2?: number;
  target_2: number | null;
  confidence: number;
  status: SignalStatus;
  fsmState: string;
  fsm_state: string;
  timeframe: string | null;
  isAutoExecuted: boolean;
  deskType: 'SCALP' | 'INTRADAY' | 'SWING';
  distancePts: number | null;
  distancePct: number | null;
  distance_to_trigger_pts: number | null;
  ttlSeconds: number | null;
  ttl_remaining_seconds: number | null;
  dataQuality: string | null;
  data_quality: string | null;
  rationale: string[];
  riskReward: number;
  risk_reward_t1: number | null;
  raw: Record<string, unknown>;
}

export interface ParseSignalListOptions {
  requireContract?: boolean;
  requireTimestamp?: boolean;
}

export function parseSignalList(
  rawList: unknown[],
  queryUnderlying = '',
  options?: ParseSignalListOptions,
): StandardActiveSignal[] {
  if (!Array.isArray(rawList)) return [];
  const requireContract = options?.requireContract ?? true;
  const requireTimestamp = options?.requireTimestamp ?? true;
  const parsed: StandardActiveSignal[] = [];

  for (let idx = 0; idx < rawList.length; idx++) {
    const s: any = rawList[idx];
    if (s === null || typeof s !== 'object' || Array.isArray(s)) continue;

    const entry = pickPositiveNum(s?.entry_price, s?.trigger, s?.entry_min, s?.entry);
    const sl = pickPositiveNum(s?.current_stop_loss, s?.stop_loss, s?.sl);
    const t1 = pickPositiveNum(s?.target_1, s?.target, s?.target1, s?.t1);
    if (entry === null || sl === null || t1 === null) continue;

    let ts = parseSignalTime(s, idx);
    if (ts === null) {
      if (requireTimestamp) continue;
      ts = 0;
    }

    const side = String(s?.direction || s?.side || '').toUpperCase();
    if (!side) continue;
    const dir: 'BUY' | 'SELL' =
      side.includes('SELL') || side.includes('SHORT') || side.includes('PUT') ? 'SELL' : 'BUY';

    const confNum = toNullableNum(s?.confidence);
    if (confNum === null) continue;
    const confRaw = confNum > 1 ? confNum : confNum * 100;

    const t2 = pickPositiveNum(s?.target_2, s?.target2, s?.t2);
    const stratRaw = String(s?.strategy ?? s?.strategy_name ?? s?.strategy_id ?? '').trim();
    if (!stratRaw) continue;
    const strat = stratRaw.replace(/_/g, ' ');

    const typeRaw = String(s?.signal_type ?? s?.desk ?? '').toUpperCase();
    const isScalp = Boolean(s?.is_scalp) || typeRaw === 'SCALP' || strat.toLowerCase().includes('scalp');
    const isSwing = Boolean(s?.is_swing) || typeRaw === 'SWING' || strat.toLowerCase().includes('swing') || strat.toLowerCase().includes('vcp');
    const deskType: 'SCALP' | 'INTRADAY' | 'SWING' = isScalp ? 'SCALP' : isSwing ? 'SWING' : 'INTRADAY';

    const id = String(s?.signal_id ?? s?.id ?? '');
    if (!id) continue;

    const contractObj = s?.option_contract;
    const brokerSymbol =
      contractObj !== null && typeof contractObj === 'object' && !Array.isArray(contractObj)
        ? (contractObj as Record<string, unknown>).broker_symbol
        : null;
    const contract = brokerSymbol ?? s?.option_symbol ?? s?.contract ?? s?.broker_symbol;
    if (requireContract && (contract === null || contract === undefined || String(contract).trim() === '')) {
      continue;
    }

    const contractStr = contract ? String(contract).trim() : undefined;
    const rawFsm = String(s?.fsm_state ?? s?.status ?? s?.state ?? 'ACTIVE').toUpperCase();
    const fsmStatus = toSignalStatus(rawFsm);

    const distancePts = toNullableNum(s?.distance_to_trigger_pts ?? s?.distance_pts);
    const distancePct = toNullableNum(s?.distance_to_trigger_pct ?? s?.distance_pct);
    const ttlSeconds = toNullableNum(s?.ttl_remaining_seconds ?? s?.ttl_seconds ?? s?.ttl);
    const dataQuality = toNullableQuality(s?.data_quality ?? s?.quality);

    const trigger = toNullableNum(s?.trigger ?? s?.trigger_level ?? s?.trigger_price);
    const rationale = Array.isArray(s?.rationale)
      ? s.rationale.filter((r: unknown): r is string => typeof r === 'string').slice(0, 4)
      : [];
    const rr = calcRiskReward(entry, sl, t1);
    const createdAtStr = typeof s?.created_at_str === 'string' ? s.created_at_str : null;

    parsed.push({
      id,
      signal_id: id,
      timestamp: ts,
      createdAtStr,
      created_at_str: createdAtStr,
      direction: dir,
      rawDirection: side,
      instrument: s?.underlying ?? s?.instrument ?? queryUnderlying,
      underlying: s?.underlying ?? s?.instrument ?? queryUnderlying,
      contract: contractStr,
      strategy: stratRaw,
      entry,
      trigger,
      stopLoss: sl,
      stop_loss: sl,
      target1: t1,
      target_1: t1,
      target2: t2 ?? undefined,
      target_2: t2 ?? null,
      confidence: Math.round(confRaw),
      status: fsmStatus,
      fsmState: rawFsm,
      fsm_state: rawFsm,
      timeframe: typeof s?.timeframe === 'string' ? s.timeframe : null,
      isAutoExecuted: parseAutoExecuted(s),
      deskType,
      distancePts,
      distancePct,
      distance_to_trigger_pts: distancePts,
      ttlSeconds,
      ttl_remaining_seconds: ttlSeconds,
      dataQuality,
      data_quality: dataQuality,
      rationale,
      riskReward: rr,
      risk_reward_t1: rr,
      raw: s,
    });
  }
  return parsed;
}

export interface UseActiveSignalsOptions {
  instrument?: string;
  pollIntervalMs?: number;
  marketClosed?: boolean;
  desk?: string;
  strategy?: string;
  status?: string;
  isScalp?: boolean;
  enabled?: boolean;
  requireContract?: boolean;
  requireTimestamp?: boolean;
  onEvent?: (evt: string, data: unknown) => void;
}

export function useActiveSignals(opts: UseActiveSignalsOptions = {}) {
  const {
    instrument = '',
    pollIntervalMs,
    marketClosed = false,
    desk,
    strategy,
    status,
    isScalp,
    enabled = true,
    requireContract,
    requireTimestamp,
    onEvent,
  } = opts;

  const [signals, setSignals] = useState<StandardActiveSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAt, setLastAt] = useState<Date | null>(null);

  const requestSeqRef = useRef(0);
  const loadedRef = useRef(false);
  const hasDataRef = useRef(false);
  const lastHandledEventRef = useRef<SignalsStreamEvent | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  // Consume SSE stream context if wrapped in provider
  const streamCtx = useContext(SignalStreamContext);
  const sseConnected = streamCtx?.connected ?? false;
  const lastEvent = streamCtx?.lastEvent ?? null;

  const fetchSignals = useCallback(
    async (options?: { quiet?: boolean }) => {
      if (!enabled) return;
      const quiet = options?.quiet ?? false;
      const seq = ++requestSeqRef.current;
      if (!loadedRef.current) setLoading(true);
      else if (!quiet) setRefreshing(true);

      try {
        const queryParams: Record<string, any> = {};
        if (instrument && instrument !== 'ALL') queryParams.instrument = instrument;
        if (status) queryParams.status = status;
        if (strategy) queryParams.strategy = strategy;
        if (desk) queryParams.desk = desk;
        if (isScalp !== undefined) queryParams.is_scalp = isScalp;

        const res = await api.getSignalsActive(queryParams);

        if (seq !== requestSeqRef.current) return;
        const rows = Array.isArray(res?.signals) ? res.signals : [];
        const parsed = parseSignalList(rows, instrument, {
          requireContract: requireContract ?? false,
          requireTimestamp: requireTimestamp ?? false,
        });
        // Descending timestamp sort
        parsed.sort((a, b) => b.timestamp - a.timestamp);
        setSignals(parsed);
        setError(null);
        setLastAt(new Date());
        hasDataRef.current = true;
      } catch (err) {
        if (seq !== requestSeqRef.current) return;
        setError(err instanceof Error ? err.message : 'Active signals unavailable');
      } finally {
        if (seq === requestSeqRef.current) {
          loadedRef.current = true;
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [enabled, instrument, status, strategy, desk, isScalp, requireContract, requireTimestamp],
  );

  // SSE event dispatch
  useEffect(() => {
    if (!lastEvent || lastEvent === lastHandledEventRef.current) return;
    lastHandledEventRef.current = lastEvent;
    if (onEventRef.current) {
      try {
        onEventRef.current(lastEvent.type, lastEvent.data);
      } catch {
        // Consumer handler errors must never crash the hook
      }
    }
    if (shouldRefreshSignalsOnEvent(lastEvent.type)) {
      void fetchSignals({ quiet: true });
    }
  }, [lastEvent, fetchSignals]);

  // Initial & periodic polling via usePolling
  const effectivePollMs = useMemo(() => {
    if (pollIntervalMs && pollIntervalMs > 0) return pollIntervalMs;
    return sseConnected ? 15000 : 8000;
  }, [pollIntervalMs, sseConnected]);

  const pollCallback = useCallback(async () => {
    if (marketClosed && hasDataRef.current) return;
    await fetchSignals({ quiet: true });
  }, [marketClosed, fetchSignals]);

  usePolling(pollCallback, effectivePollMs, enabled);

  return {
    signals,
    loading,
    refreshing,
    error,
    lastAt,
    sseConnected,
    refresh: fetchSignals,
  };
}
