'use client';

import { memo, useState, useEffect, useMemo, useRef } from 'react';
import { fmtNum } from '@/components/ui/desk';
import { fmtTimeMs } from '@/components/signals/signalsNormalize';
import { playScalpAudio } from '@/components/scalp/scalpAudio';
import { Volume2, VolumeX, RefreshCw } from 'lucide-react';
import {
  SIGNAL_STATUSES,
  type SignalStatus,
  toSignalStatus,
  parseSignalTime,
  calcRiskReward,
  parseAutoExecuted,
  parseSignalList,
  shouldRefreshSignalsOnEvent,
  shouldRefreshVerdictOnSignalEvent,
  formatTtlSeconds,
  formatDistanceLabel,
  useActiveSignals,
  type StandardActiveSignal as WarRoomSignal,
} from '@/hooks/useActiveSignals';

export {
  SIGNAL_STATUSES,
  type SignalStatus,
  toSignalStatus,
  parseSignalTime,
  calcRiskReward,
  parseAutoExecuted,
  parseSignalList,
  shouldRefreshSignalsOnEvent,
  shouldRefreshVerdictOnSignalEvent,
  formatTtlSeconds,
  formatDistanceLabel,
  type WarRoomSignal,
};

interface SignalFeedPanelProps {
  instrument?: string;
  onLatestSignal?: (signal: WarRoomSignal | null) => void;
  /** Open the dossier for a row (wired to SignalDetailDrawer by the coordinator). */
  onSelect?: (signal: WarRoomSignal) => void;
  /** Raw SSE event passthrough so the coordinator can refresh verdict without a 2nd EventSource. */
  onSignalEvent?: (evt: string, data: unknown) => void;
}

function isDegradedQuality(q: string | null): boolean {
  return q === 'DEGRADED' || q === 'OFFLINE' || q === 'FALLBACK' || q === 'STALE';
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

export const SignalFeedPanel = memo(function SignalFeedPanel({
  instrument,
  onLatestSignal,
  onSelect,
  onSignalEvent,
}: SignalFeedPanelProps) {
  const [filter, setFilter] = useState<'ALL' | 'SCALP' | 'INTRADAY' | 'SWING'>('ALL');
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const prevIdsRef = useRef<Set<string>>(new Set());
  const soundEnabledRef = useRef(soundEnabled);
  useEffect(() => {
    soundEnabledRef.current = soundEnabled;
  }, [soundEnabled]);

  const cleanUnderlying = (instrument || 'NIFTY').replace(' 50', '').trim().toUpperCase();
  const queryUnderlying =
    cleanUnderlying === 'BANKNIFTY' || cleanUnderlying === 'SENSEX' ? cleanUnderlying : 'NIFTY';

  const {
    signals,
    loading,
    error: fetchError,
    refresh: fetchSignals,
  } = useActiveSignals({
    instrument: queryUnderlying,
    requireContract: true,
    requireTimestamp: true,
    onEvent: onSignalEvent,
  });

  // Sound chime on newly arrived signals
  useEffect(() => {
    try {
      const prev = prevIdsRef.current;
      if (prev.size > 0 && soundEnabledRef.current && signals.length > 0) {
        const hasNew = signals.some((s) => !prev.has(s.id));
        if (hasNew) playScalpAudio('enter');
      }
      prevIdsRef.current = new Set(signals.map((s) => s.id));
    } catch {
      // Audio must never break feed
    }
  }, [signals]);

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
        <button
          type="button"
          aria-label={soundEnabled ? 'Mute scalp alerts' : 'Unmute scalp alerts'}
          title={soundEnabled ? 'Scalp chime active — click to mute' : 'Scalp chime muted — click to enable'}
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
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 2,
                  padding: '10px 14px',
                  cursor: 'pointer',
                  borderBottom: i < filteredSignals.length - 1 ? '1px solid var(--ds-border-subtle)' : 0,
                  background: sig.isAutoExecuted ? 'var(--ds-accent-wash)' : undefined,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      minWidth: 44,
                      color: isBuy ? 'var(--ds-bull-strong)' : 'var(--ds-bear-strong)',
                    }}
                  >
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
                  <span className="num" style={{ fontSize: 13 }}>
                    E {fmtNum(sig.entry, 1)}
                  </span>
                  <span className="num" style={{ fontSize: 13, color: 'var(--ds-bull-strong)' }}>
                    T {fmtNum(sig.target1, 1)}
                  </span>
                  <span className="num" style={{ fontSize: 13, color: 'var(--ds-bear-strong)' }}>
                    SL {fmtNum(sig.stopLoss, 1)}
                  </span>
                  <span className="num" style={{ fontSize: 13 }}>
                    1:{fmtNum(rr, 1)}
                  </span>
                  <span className="num" style={{ fontSize: 13, fontWeight: 600 }}>
                    {sig.confidence}%
                  </span>
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
                    style={{
                      fontSize: 12,
                      color: 'var(--ds-ink-3)',
                      width: 16,
                      textAlign: 'center',
                      transition: 'transform 150ms ease',
                    }}
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
                    <span className="chip chip--warn" style={{ fontSize: 10 }}>
                      {quality.toLowerCase()}
                    </span>
                  ) : (
                    <span>{quality.toLowerCase()}</span>
                  )}
                </div>
                {expanded ? (
                  <div style={{ fontSize: 12, color: 'var(--ds-text-secondary)', paddingTop: 4 }}>
                    <span>T2 {sig.target2 ? fmtNum(sig.target2, 1) : '—'}</span>
                    {' · '}
                    <span>
                      {sig.isAutoExecuted ? 'auto' : 'manual'} · {sig.status}
                    </span>
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
