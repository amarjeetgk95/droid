'use client';

import { memo, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { api } from '@/lib/api';
import { useSignalStream } from '@/context/SignalStreamContext';
import type { SignalsStreamEvent } from '@/hooks/useSignalsStream';
import { fmtNum } from '@/components/ui/desk';
import { fmtTimeMs } from '@/components/signals/signalsNormalize';
import { playScalpAudio } from '@/components/scalp/scalpAudio';
import { Volume2, VolumeX, RefreshCw } from 'lucide-react';

export interface WarRoomSignal {
  id: string;
  timestamp: number;
  direction: 'BUY' | 'SELL';
  instrument: string;
  contract?: string;
  strategy: string;
  entry: number;
  stopLoss: number;
  target1: number;
  target2?: number;
  confidence: number;
  status: SignalStatus;
  isAutoExecuted?: boolean;
  deskType: 'SCALP' | 'INTRADAY' | 'SWING';
  /** Live distance to trigger from GET /active (null when the quote leg degraded). */
  distancePts?: number | null;
  distancePct?: number | null;
  /** Seconds until signal TTL expiry (null when the backend omits it). */
  ttlSeconds?: number | null;
  /** Backend feed quality: LIVE | DEGRADED | OFFLINE (null when absent). */
  dataQuality?: string | null;
}

export const SIGNAL_STATUSES = [
  'ACTIVE',
  'TRIGGERED',
  'TARGET_REACHED',
  'STOPPED_OUT',
  'EXPIRED',
] as const;

export type SignalStatus = (typeof SIGNAL_STATUSES)[number];

/**
 * Backend FSM state → feed badge status. `/signals/active` emits `fsm_state`
 * (DETECTED/VALIDATED/ARMED/CONFIRMED/TRIGGERED/TARGET_*_HIT/STOP_LOSS_HIT/
 * TIME_STOP_HIT/EXPIRED/INVALIDATED), not the legacy `status` field, so every
 * row previously badge-flattened to ACTIVE.
 */
const FSM_STATUS_MAP: Record<string, SignalStatus> = {
  DETECTED: 'ACTIVE',
  VALIDATED: 'ACTIVE',
  ARMED: 'ACTIVE',
  CONFIRMED: 'ACTIVE',
  TRIGGERED: 'TRIGGERED',
  TARGET_1_HIT: 'TARGET_REACHED',
  TARGET_2_HIT: 'TARGET_REACHED',
  STOP_LOSS_HIT: 'STOPPED_OUT',
  TIME_STOP_HIT: 'EXPIRED',
  RUNNER_TIME_STOP_HIT: 'EXPIRED',
  EXPIRED: 'EXPIRED',
  INVALIDATED: 'EXPIRED',
};

/**
 * Coerce a backend state into the known set. `fsm_state` wins over the legacy
 * `status`; an absent state keeps the historical ACTIVE default (DETECTED),
 * while an unrecognised token must not leak a `string` into the union.
 */
export function toSignalStatus(raw: unknown): SignalStatus {
  const upper = String(raw ?? '').toUpperCase();
  if (!upper) return 'ACTIVE';
  if (FSM_STATUS_MAP[upper]) return FSM_STATUS_MAP[upper];
  return (SIGNAL_STATUSES as readonly string[]).includes(upper)
    ? (upper as SignalStatus)
    : 'ACTIVE';
}

interface SignalFeedPanelProps {
  instrument?: string;
  onLatestSignal?: (signal: WarRoomSignal | null) => void;
  /** Open the dossier for a row (wired to SignalDossierDrawer by the coordinator). */
  onSelect?: (signal: WarRoomSignal) => void;
  /** Raw SSE event passthrough so the coordinator can refresh verdict without a 2nd EventSource. */
  onSignalEvent?: (evt: string, data: unknown) => void;
}

function toMsEpoch(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v > 1e12 ? Math.round(v) : Math.round(v * 1000);
  }
  return null;
}

export function parseSignalTime(s: any, _idx?: number): number | null {
  const fromMs = toMsEpoch(s?.timestamp_ms);
  if (fromMs !== null) return fromMs;
  // Backend SignalInstance serialises `created_at_utc` (ms epoch).
  const fromUtc = toMsEpoch(s?.created_at_utc);
  if (fromUtc !== null) return fromUtc;
  const fromTs = toMsEpoch(s?.timestamp);
  if (fromTs !== null) return fromTs;
  if (s?.created_at) {
    const t = new Date(s.created_at).getTime();
    if (Number.isFinite(t)) return t;
  }
  // No timestamp on the payload — never invent one. Caller skips the row.
  return null;
}

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

export function parseAutoExecuted(s: any): boolean {
  if (Boolean(s?.paper_order_id ?? s?.is_auto_executed ?? s?.isAutoExecuted ?? false)) return true;
  // Backend `SignalInstance.paper_order` is a dict once the engine executed.
  const po = s?.paper_order;
  return typeof po === 'object' && po !== null && !Array.isArray(po);
}

/** Positive finite number from number|numeric-string; null otherwise. */
function pickPositiveNum(...vals: unknown[]): number | null {
  for (const v of vals) {
    const n = typeof v === 'string' && v.trim() !== '' ? Number(v) : (v as number);
    if (typeof n === 'number' && Number.isFinite(n) && n > 0) return n;
  }
  return null;
}

/** Fail-soft numeric coercion for feed-truth extras (distance/TTL). Never drops a row. */
function toNullableNum(v: unknown): number | null {
  const n = typeof v === 'string' && v.trim() !== '' ? Number(v) : (v as number);
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

/** Feed quality token, upper-cased for tone checks (null when the backend omits it). */
function toNullableQuality(v: unknown): string | null {
  if (typeof v !== 'string') return null;
  const s = v.trim().toUpperCase();
  return s ? s : null;
}

function isDegradedQuality(q: string | null): boolean {
  return q === 'DEGRADED' || q === 'OFFLINE' || q === 'FALLBACK' || q === 'STALE';
}

function formatTtlSeconds(v: number | null): string {
  if (v === null) return '—';
  const s = Math.round(v);
  if (s <= 0) return 'expired';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

function formatDistanceLabel(pts: number | null, pct: number | null): string | null {
  if (pts === null && pct === null) return null;
  if (pts !== null && pts === 0) return 'at trigger';
  const parts: string[] = [];
  if (pts !== null) parts.push(`${fmtNum(pts, 1)} pts`);
  if (pct !== null) parts.push(`${fmtNum(pct, 2)}%`);
  return `${parts.join(' · ')} to trigger`;
}

function timeAgo(ts: number): string {
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (s < 10) return 'just now';
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

const STATUS_BADGE: Record<SignalStatus, string> = {
  ACTIVE: 'b-info',
  TRIGGERED: 'b-warn',
  TARGET_REACHED: 'b-bull',
  STOPPED_OUT: 'b-bear',
  EXPIRED: 'b-neut',
};

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

/**
 * Pure predicate so WarRoomDesk + tests share one definition of
 * "this SSE event should refresh the signal list".
 * FEED_STATUS / audit_pnl_update are telemetry — never a list refresh.
 */
export function shouldRefreshSignalsOnEvent(evt: string): boolean {
  if (!evt) return false;
  if (evt === 'FEED_STATUS' || evt === 'audit_pnl_update') return false;
  if (SIGNAL_SSE_REFRESH_EVENTS.has(evt)) return true;
  return evt.startsWith('signal_') || evt.startsWith('fsm');
}

/** P0 lifecycle events that should also nudge the verdict (throttled by caller). */
export function shouldRefreshVerdictOnSignalEvent(evt: string): boolean {
  return (
    evt === 'signal_created' ||
    evt === 'signal_confirmed' ||
    evt === 'signal_triggered' ||
    evt === 'signal_outcome' ||
    evt === 'paper_execution'
  );
}

export function parseSignalList(rawList: unknown[], queryUnderlying: string): WarRoomSignal[] {
  if (!Array.isArray(rawList)) return [];
  const parsed: WarRoomSignal[] = [];
  for (let idx = 0; idx < rawList.length; idx++) {
    const s: any = rawList[idx];
    if (s === null || typeof s !== 'object' || Array.isArray(s)) continue;
    // Fail-closed: entry / stop / target are required. `entry_price` is the
    // executed fill and is nullable before trigger; `trigger` is the
    // pre-trigger level the backend publishes, so it is the entry fallback.
    // Never derive levels from spot multiples — that invents edge.
    const entry = pickPositiveNum(s?.entry_price, s?.trigger, s?.entry_min, s?.entry);
    const sl = pickPositiveNum(s?.current_stop_loss, s?.stop_loss, s?.sl);
    const t1 = pickPositiveNum(s?.target_1, s?.target, s?.target1, s?.t1);
    if (entry === null || sl === null || t1 === null) continue;
    const ts = parseSignalTime(s, idx);
    // No timestamp = no row. Never backfill with Date.now().
    if (ts === null) continue;
    const side = String(s?.direction || s?.side || '').toUpperCase();
    if (!side) continue;
    const dir: 'BUY' | 'SELL' =
      side.includes('SELL') || side.includes('SHORT') || side.includes('PUT') ? 'SELL' : 'BUY';
    const confNum = toNullableNum(s?.confidence);
    if (confNum === null) continue;
    const confRaw = confNum > 1 ? confNum : confNum * 100;
    const t2 = pickPositiveNum(s?.target_2, s?.target2, s?.t2);
    const stratRaw = String(s?.strategy ?? s?.strategy_name ?? '').trim();
    if (!stratRaw) continue;
    const strat = stratRaw.replace(/_/g, ' ');
    const typeRaw = String(s?.signal_type ?? s?.desk ?? '').toUpperCase();
    const isScalp = Boolean(s?.is_scalp) || typeRaw === 'SCALP' || strat.toLowerCase().includes('scalp');
    const isSwing = Boolean(s?.is_swing) || typeRaw === 'SWING' || strat.toLowerCase().includes('swing') || strat.toLowerCase().includes('vcp');
    const id = s?.signal_id ?? s?.id;
    if (!id) continue;
    // Backend `option_contract` is a dict; the broker symbol is the tradable id.
    const contractObj = s?.option_contract;
    const brokerSymbol =
      contractObj !== null && typeof contractObj === 'object' && !Array.isArray(contractObj)
        ? (contractObj as Record<string, unknown>).broker_symbol
        : null;
    const contract = brokerSymbol ?? s?.option_symbol ?? s?.contract ?? s?.broker_symbol;
    if (contract === null || contract === undefined || String(contract).trim() === '') continue;
    parsed.push({
      id: String(id),
      timestamp: ts,
      direction: dir,
      instrument: s?.underlying ?? s?.instrument ?? queryUnderlying,
      contract: String(contract).trim(),
      strategy: strat,
      entry,
      stopLoss: sl,
      target1: t1,
      target2: t2 ?? undefined,
      confidence: Math.max(0, Math.min(100, Math.round(confRaw))),
      status: toSignalStatus(s?.fsm_state ?? s?.status ?? s?.state),
      isAutoExecuted: parseAutoExecuted(s),
      deskType: isScalp ? 'SCALP' : isSwing ? 'SWING' : 'INTRADAY',
      // Feed-truth extras (backend signals.py ~207-221). Fail-soft: missing
      // distance/TTL/quality renders as muted placeholders, never drops the row.
      distancePts: toNullableNum(s?.distance_to_trigger_pts ?? s?.distance_pts),
      distancePct: toNullableNum(s?.distance_to_trigger_pct ?? s?.distance_pct),
      ttlSeconds: toNullableNum(s?.ttl_remaining_seconds ?? s?.ttl_seconds),
      dataQuality: toNullableQuality(s?.data_quality),
    });
  }
  return parsed;
}

/**
 * Calm Kite-minimal signal list (Mock A): plain divider rows,
 * no boxes-in-boxes, no badges — quiet type + honest preview note.
 */
/** Poll cadence: SSE-connected is a backstop, disconnected is the primary feed. */
const SSE_POLL_MS = 15000;
const FALLBACK_POLL_MS = 8000;

export const SignalFeedPanel = memo(function SignalFeedPanel({ instrument, onLatestSignal, onSelect, onSignalEvent }: SignalFeedPanelProps) {
  const [filter, setFilter] = useState<'ALL' | 'SCALP' | 'INTRADAY' | 'SWING'>('ALL');
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [signals, setSignals] = useState<WarRoomSignal[]>([]);
  const [droppedCount, setDroppedCount] = useState(0);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [lastFetchTime, setLastFetchTime] = useState<number>(Date.now());
  const lastSseRefetchRef = useRef(0);
  const prevIdsRef = useRef<Set<string>>(new Set());
  const soundEnabledRef = useRef(soundEnabled);
  const onSignalEventRef = useRef(onSignalEvent);
  const lastHandledEventRef = useRef<SignalsStreamEvent | null>(null);
  useEffect(() => {
    soundEnabledRef.current = soundEnabled;
  }, [soundEnabled]);
  useEffect(() => {
    onSignalEventRef.current = onSignalEvent;
  }, [onSignalEvent]);

  const fetchSignals = useCallback(async (opts?: { quiet?: boolean }) => {
    const quiet = opts?.quiet ?? false;
    const cleanUnderlying = (instrument || 'NIFTY').replace(' 50', '').trim().toUpperCase();
    const queryUnderlying = cleanUnderlying === 'BANKNIFTY' || cleanUnderlying === 'SENSEX' ? cleanUnderlying : 'NIFTY';

    try {
      if (!quiet) setLoading(true);
      setFetchError(null);
      const res = await api.getSignalsActive({ instrument: queryUnderlying });
      const rawList = Array.isArray(res?.signals) ? res.signals : [];
      const parsed = parseSignalList(rawList, queryUnderlying);
      setDroppedCount(Math.max(0, rawList.length - parsed.length));
      // New-signal chime: only when we already had a baseline (no chime on first load).
      try {
        const prev = prevIdsRef.current;
        if (prev.size > 0 && soundEnabledRef.current && parsed.length > 0) {
          const hasNew = parsed.some((s) => !prev.has(s.id));
          if (hasNew) playScalpAudio('enter');
        }
        prevIdsRef.current = new Set(parsed.map((s) => s.id));
      } catch {
        // Audio must never break the feed.
      }
      setSignals(parsed);
      setLastFetchTime(Date.now());
    } catch (err) {
      // Keep previously loaded signals across transient network drops.
      // Do not wipe list; mark offline banner in header so operator knows state.
      setFetchError(err instanceof Error ? err.message : 'signals unavailable');
    } finally {
      setLoading(false);
    }
  }, [instrument]);

  const sseRefresh = useCallback(() => {
    if (typeof document !== 'undefined' && document.hidden) return;
    const nowMs = Date.now();
    // Throttle SSE bursts (scanner P2 can be chatty) to max 1 refetch / 2s.
    if (nowMs - lastSseRefetchRef.current < 2000) return;
    lastSseRefetchRef.current = nowMs;
    void fetchSignals({ quiet: true });
  }, [fetchSignals]);

  const handleStreamEvent = useCallback((evt: string, data: unknown) => {
    try {
      onSignalEventRef.current?.(evt, data);
    } catch {
      // Coordinator errors must never kill the feed.
    }
    if (shouldRefreshSignalsOnEvent(evt)) sseRefresh();
  }, [sseRefresh]);

  // Phase 0: one shared EventSource lives in SignalStreamProvider; consume its
  // buffered events instead of opening a second subscription via the raw hook.
  const { connected: sseConnected, lastEvent } = useSignalStream();
  useEffect(() => {
    if (!lastEvent || lastEvent === lastHandledEventRef.current) return;
    lastHandledEventRef.current = lastEvent;
    handleStreamEvent(lastEvent.type, lastEvent.data);
  }, [lastEvent, handleStreamEvent]);

  // SSE-first feed with adaptive poll fallback: 15s when SSE is connected,
  // and 8s when disconnected so feed stays real-time even during SSE disconnects.
  const pollMs = sseConnected ? SSE_POLL_MS : FALLBACK_POLL_MS;

  useEffect(() => {
    void fetchSignals();
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void fetchSignals({ quiet: true });
    }, pollMs);
    return () => clearInterval(interval);
  }, [fetchSignals, pollMs]);

  const filteredSignals = useMemo(() => {
    if (filter === 'ALL') return signals;
    return signals.filter((s) => s.deskType === filter);
  }, [signals, filter]);

  useEffect(() => {
    if (onLatestSignal) {
      onLatestSignal(signals.length > 0 ? signals[0] : null);
    }
  }, [signals, onLatestSignal]);

  return (
    <section aria-label="Signals">
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 4, flexWrap: 'wrap' }}>
        <h2 style={{ fontSize: 14, fontWeight: 700, margin: 0 }}>Signals</h2>
        <span style={{ fontSize: 12, color: 'var(--ds-text-secondary)' }}>
          {filteredSignals.length} active{fetchError ? ` · offline — ${fetchError}` : ''}
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: 'var(--ds-text-secondary)' }}>
          {loading && signals.length === 0 ? 'syncing…' : timeAgo(lastFetchTime)}
          {sseConnected ? ' · live via SSE' : ` · poll ${Math.round(pollMs / 1000)}s`}
        </span>
        <button
          type="button"
          title={soundEnabled ? 'Audio chime on' : 'Audio chime off'}
          onClick={() => {
            const next = !soundEnabled;
            setSoundEnabled(next);
            if (next) playScalpAudio('enter');
          }}
          className="btn icon-btn"
          style={{ width: 28, height: 28 }}
        >
          {soundEnabled ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
        </button>
        <button
          type="button"
          onClick={() => void fetchSignals()}
          disabled={loading}
          title="Refresh feed"
          className="btn icon-btn"
          style={{ width: 28, height: 28 }}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="seg" role="tablist" aria-label="Desk filter" style={{ marginBottom: 8 }}>
        {(['ALL', 'SCALP', 'INTRADAY', 'SWING'] as const).map((f) => (
          <button
            key={f}
            type="button"
            role="tab"
            aria-selected={filter === f}
            data-active={filter === f}
            onClick={() => setFilter(f)}
            className="seg-btn"
            style={{ fontSize: 11, padding: '3px 9px' }}
          >
            {f}
          </button>
        ))}
      </div>

      {droppedCount > 0 ? (
        <p role="status" className="notice notice--warn" style={{ fontSize: 11.5, margin: '0 0 8px' }}>
          {droppedCount} signal row{droppedCount === 1 ? '' : 's'} dropped — malformed (missing levels, contract, state or timestamp).
        </p>
      ) : null}

      <div className="card">
        {loading && signals.length === 0 ? (
          <div style={{ padding: 8 }} aria-label="Loading signals">
            {[64, 64, 64].map((h, i) => (
              <div key={i} className="skel" style={{ height: h, margin: 6 }} />
            ))}
          </div>
        ) : filteredSignals.length === 0 && fetchError ? (
          <div className="sig-empty" role="alert">
            <p style={{ fontWeight: 600, fontSize: 13 }}>Signal feed unavailable</p>
            <p style={{ fontSize: 12, color: 'var(--ds-bear-strong)' }}>{fetchError}</p>
          </div>
        ) : filteredSignals.length === 0 ? (
          <div className="sig-empty">
            <p style={{ fontWeight: 600, fontSize: 13 }}>No edge right now</p>
            <p style={{ fontSize: 12 }}>Engine scanning every tick — nothing meets this filter.</p>
          </div>
        ) : (
          filteredSignals.map((sig, i) => {
            const isBuy = sig.direction === 'BUY';
            const rr = calcRiskReward(sig.entry, sig.stopLoss, sig.target1);
            const expanded = expandedId === sig.id;
            const distLabel = formatDistanceLabel(sig.distancePts ?? null, sig.distancePct ?? null);
            const ttlLabel = formatTtlSeconds(sig.ttlSeconds ?? null);
            const quality = sig.dataQuality ?? 'UNKNOWN';
            const degraded = isDegradedQuality(sig.dataQuality ?? null);
            return (
              <div
                key={sig.id}
                role="button"
                tabIndex={0}
                onClick={() => setExpandedId(expanded ? null : sig.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setExpandedId(expanded ? null : sig.id);
                  }
                }}
                style={{
                  display: 'flex', flexDirection: 'column', gap: 2,
                  padding: '10px 14px', cursor: 'pointer',
                  borderBottom: i < filteredSignals.length - 1 ? '1px solid var(--ds-border-subtle)' : 0,
                  background: sig.isAutoExecuted ? 'var(--ds-accent-wash)' : undefined,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 12, fontWeight: 600, minWidth: 44, color: isBuy ? 'var(--ds-bull-strong)' : 'var(--ds-bear-strong)' }}>
                    {isBuy ? '▲ BUY' : '▼ SELL'}
                  </span>
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: 'block', fontSize: 14, fontWeight: 600 }}>{sig.contract}</span>
                    <span style={{ display: 'block', fontSize: 12, color: 'var(--ds-text-secondary)' }}>
                      {sig.strategy} · {timeAgo(sig.timestamp)} · {sig.deskType.toLowerCase()}
                      {sig.isAutoExecuted ? (
                        <span
                          title="Auto-executed by engine"
                          style={{
                            marginLeft: 6,
                            padding: '0 5px',
                            borderRadius: 'var(--radius-xs)',
                            border: '1px solid var(--ds-accent-line)',
                            background: 'var(--ds-accent-wash)',
                            color: 'var(--ds-accent)',
                            fontWeight: 600,
                            fontSize: 10,
                            letterSpacing: '0.04em',
                            textTransform: 'uppercase',
                          }}
                        >
                          Auto
                        </span>
                      ) : null}
                    </span>
                  </span>
                  <span style={{ flex: 1 }} />
                  <span className={`badge badge-sm ${STATUS_BADGE[sig.status]}`}>{sig.status.replace(/_/g, ' ')}</span>
                  <span className="num" style={{ fontSize: 13 }}>E {fmtNum(sig.entry, 1)}</span>
                  <span className="num" style={{ fontSize: 13, color: 'var(--ds-bull-strong)' }}>T {fmtNum(sig.target1, 1)}</span>
                  <span className="num" style={{ fontSize: 13, color: 'var(--ds-bear-strong)' }}>SL {fmtNum(sig.stopLoss, 1)}</span>
                  <span className="num" style={{ fontSize: 13 }}>1:{fmtNum(rr, 1)}</span>
                  <span className="num" style={{ fontSize: 13, fontWeight: 600 }}>{sig.confidence}%</span>
                  {onSelect ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect(sig);
                      }}
                      className="btn"
                      style={{ fontSize: 11, padding: '2px 8px' }}
                      aria-label={`Open dossier for ${sig.contract}`}
                    >
                      Dossier
                    </button>
                  ) : null}
                  <span
                    className="num"
                    style={{ fontSize: 12, color: 'var(--ds-ink-3)', width: 16, textAlign: 'center', transition: 'transform 150ms ease' }}
                    aria-hidden="true"
                  >
                    {expanded ? '▾' : '▸'}
                  </span>
                </div>
                <div className="num" style={{ fontSize: 11.5, color: 'var(--ds-text-secondary)' }}>
                  {distLabel ?? 'distance —'}
                  {' · '}
                  <span>ttl {ttlLabel}</span>
                  {' · '}
                  {degraded ? (
                    <span className="chip chip--warn" style={{ fontSize: 10 }}>{quality.toLowerCase()}</span>
                  ) : (
                    <span>{quality.toLowerCase()}</span>
                  )}
                </div>
                {expanded ? (
                  <div style={{ fontSize: 12, color: 'var(--ds-text-secondary)', paddingTop: 4 }}>
                    <span>T2 {sig.target2 ? fmtNum(sig.target2, 1) : '—'}</span>
                    {' · '}
                    <span>{sig.isAutoExecuted ? 'auto' : 'manual'} · {sig.status}</span>
                    {' · '}
                    <span>{fmtTimeMs(sig.timestamp)}</span>
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </section>
  );
});
