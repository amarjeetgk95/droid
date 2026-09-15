'use client';

import { memo, useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '@/lib/api';
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
  status: 'ACTIVE' | 'TRIGGERED' | 'TARGET_REACHED' | 'STOPPED_OUT' | 'EXPIRED';
  isAutoExecuted?: boolean;
  deskType: 'SCALP' | 'INTRADAY' | 'SWING';
}

interface SignalFeedPanelProps {
  instrument?: string;
}

function toMsEpoch(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v > 1e12 ? Math.round(v) : Math.round(v * 1000);
  }
  return null;
}

export function parseSignalTime(s: any, idx: number): number {
  const fromMs = toMsEpoch(s?.timestamp_ms);
  if (fromMs !== null) return fromMs;
  const fromTs = toMsEpoch(s?.timestamp);
  if (fromTs !== null) return fromTs;
  if (s?.created_at) {
    const t = new Date(s.created_at).getTime();
    if (Number.isFinite(t)) return t;
  }
  return Date.now() - idx * 60000;
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
  return Boolean(s?.paper_order_id ?? s?.is_auto_executed ?? s?.isAutoExecuted ?? false);
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

/**
 * Calm Kite-minimal signal list (Mock A): plain divider rows,
 * no boxes-in-boxes, no badges — quiet type + honest preview note.
 */
export const SignalFeedPanel = memo(function SignalFeedPanel({ instrument }: SignalFeedPanelProps) {
  const [filter, setFilter] = useState<'ALL' | 'SCALP' | 'INTRADAY' | 'SWING'>('ALL');
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [signals, setSignals] = useState<WarRoomSignal[]>([]);
  const [isDemo, setIsDemo] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [lastFetchTime, setLastFetchTime] = useState<number>(Date.now());

  const fetchSignals = useCallback(async () => {
    const cleanUnderlying = (instrument || 'NIFTY').replace(' 50', '').trim().toUpperCase();
    const queryUnderlying = cleanUnderlying === 'BANKNIFTY' || cleanUnderlying === 'SENSEX' ? cleanUnderlying : 'NIFTY';
    const spotBase = queryUnderlying === 'BANKNIFTY' ? 56170 : queryUnderlying === 'SENSEX' ? 74620 : 23320;

    const generateFallbacks = (): WarRoomSignal[] => [
      {
        id: `sig-orb-${queryUnderlying}`,
        timestamp: Date.now() - 120000,
        direction: 'BUY',
        instrument: queryUnderlying,
        contract: `${queryUnderlying} ATM CE`,
        strategy: 'ORB Breakout + Momentum',
        entry: spotBase,
        stopLoss: spotBase - (queryUnderlying === 'BANKNIFTY' ? 120 : 45),
        target1: spotBase + (queryUnderlying === 'BANKNIFTY' ? 220 : 85),
        target2: spotBase + (queryUnderlying === 'BANKNIFTY' ? 350 : 140),
        confidence: 88,
        status: 'ACTIVE',
        isAutoExecuted: true,
        deskType: 'INTRADAY',
      },
      {
        id: `sig-vwap-${queryUnderlying}`,
        timestamp: Date.now() - 360000,
        direction: 'BUY',
        instrument: queryUnderlying,
        contract: `${queryUnderlying} ATM CE`,
        strategy: 'VWAP Scalp Bounce',
        entry: spotBase - (queryUnderlying === 'BANKNIFTY' ? 30 : 15),
        stopLoss: spotBase - (queryUnderlying === 'BANKNIFTY' ? 80 : 35),
        target1: spotBase + (queryUnderlying === 'BANKNIFTY' ? 110 : 40),
        confidence: 82,
        status: 'TRIGGERED',
        isAutoExecuted: true,
        deskType: 'SCALP',
      },
    ];

    try {
      setLoading(true);
      const res = await api.getSignalsActive({ instrument: queryUnderlying });
      const rawList = res?.signals ?? [];

      const parsed: WarRoomSignal[] = rawList.map((s: any, idx: number) => {
        const side = String(s.direction || s.side || 'BUY').toUpperCase();
        const dir: 'BUY' | 'SELL' = side.includes('SELL') || side.includes('SHORT') || side.includes('PUT') ? 'SELL' : 'BUY';
        const conf = typeof s.confidence === 'number' ? (s.confidence > 1 ? s.confidence : s.confidence * 100) : 75;
        const entry = Number(s.entry_price || s.entry || s.trigger_price || spotBase);
        const sl = Number(s.stop_loss || s.sl || (dir === 'BUY' ? entry * 0.995 : entry * 1.005));
        const t1 = Number(s.target_1 || s.target || (dir === 'BUY' ? entry * 1.008 : entry * 0.992));
        const t2 = s.target_2 ? Number(s.target_2) : (dir === 'BUY' ? entry * 1.015 : entry * 0.985);

        const strat = String(s.strategy || s.strategy_name || 'Regime Trend').replace(/_/g, ' ');
        const isScalp = Boolean(s.is_scalp || strat.toLowerCase().includes('scalp'));
        const isSwing = Boolean(s.is_swing || strat.toLowerCase().includes('swing') || strat.toLowerCase().includes('vcp'));

        return {
          id: s.id || s.signal_id || `sig-${idx}-${Date.now()}`,
          timestamp: parseSignalTime(s, idx),
          direction: dir,
          instrument: s.underlying || s.instrument || queryUnderlying,
          contract: s.option_symbol || s.contract || (dir === 'BUY' ? `${s.underlying || queryUnderlying} CE` : `${s.underlying || queryUnderlying} PE`),
          strategy: strat,
          entry,
          stopLoss: sl,
          target1: t1,
          target2: t2,
          confidence: Math.max(0, Math.min(100, Math.round(conf))),
          status: (s.status || 'ACTIVE').toUpperCase(),
          isAutoExecuted: parseAutoExecuted(s),
          deskType: isScalp ? 'SCALP' : isSwing ? 'SWING' : 'INTRADAY',
        };
      });

      if (parsed.length === 0) {
        setSignals(generateFallbacks());
        setIsDemo(true);
      } else {
        setSignals(parsed);
        setIsDemo(false);
      }

      setLastFetchTime(Date.now());
    } catch (err) {
      console.warn('Backend active signals fallback engaged:', err);
      setSignals(generateFallbacks());
      setIsDemo(true);
      setLastFetchTime(Date.now());
    } finally {
      setLoading(false);
    }
  }, [instrument]);

  useEffect(() => {
    void fetchSignals();
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void fetchSignals();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchSignals]);

  const filteredSignals = useMemo(() => {
    if (filter === 'ALL') return signals;
    return signals.filter((s) => s.deskType === filter);
  }, [signals, filter]);

  return (
    <section aria-label="Signals">
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 4, flexWrap: 'wrap' }}>
        <h2 style={{ fontSize: 14, fontWeight: 700, margin: 0 }}>Signals</h2>
        <span style={{ fontSize: 12, color: 'var(--ds-text-secondary)' }}>
          {filteredSignals.length} active{isDemo ? ' · offline preview' : ''}
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: 'var(--ds-text-secondary)' }}>
          {loading ? 'syncing…' : timeAgo(lastFetchTime)}
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

      <div className="card">
        {loading && signals.length === 0 ? (
          <div style={{ padding: 8 }} aria-label="Loading signals">
            {[64, 64, 64].map((h, i) => (
              <div key={i} className="skel" style={{ height: h, margin: 6 }} />
            ))}
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
                  padding: '14px 18px', cursor: 'pointer',
                  borderBottom: i < filteredSignals.length - 1 ? '1px solid var(--ds-border-subtle)' : 0,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 12, fontWeight: 700, minWidth: 44, color: isBuy ? 'var(--ds-bull-strong)' : 'var(--ds-bear-strong)' }}>
                    {isBuy ? '▲ BUY' : '▼ SELL'}
                  </span>
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: 'block', fontSize: 14, fontWeight: 600 }}>{sig.contract}</span>
                    <span style={{ display: 'block', fontSize: 12, color: 'var(--ds-text-secondary)' }}>
                      {sig.strategy} · {timeAgo(sig.timestamp)} · {sig.deskType.toLowerCase()}
                    </span>
                  </span>
                  <span style={{ flex: 1 }} />
                  <span className="num" style={{ fontSize: 13 }}>E {fmtNum(sig.entry, 1)}</span>
                  <span className="num" style={{ fontSize: 13, color: 'var(--ds-bull-strong)' }}>T {fmtNum(sig.target1, 1)}</span>
                  <span className="num" style={{ fontSize: 13, color: 'var(--ds-bear-strong)' }}>SL {fmtNum(sig.stopLoss, 1)}</span>
                  <span className="num" style={{ fontSize: 13 }}>1:{fmtNum(rr, 1)}</span>
                  <span className="num" style={{ fontSize: 13, fontWeight: 700 }}>{sig.confidence}%</span>
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
