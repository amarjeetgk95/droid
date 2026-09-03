'use client';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

type MiPanelProps = { instrument?: string };

interface MiData {
  instrument: string;
  regime: string;
  price_action: { structure: string; trend: string; momentum: string; location: string };
  bullish_score: number;
  bearish_score: number;
  breakout_pressure: number;
  false_breakout_risk: number;
  short_horizon: { direction: string; status: string; confidence: number };
  continuation: { direction: string; status: string; confidence: number; max_holding_minutes: number };
  max_holding: string;
}

export function MarketIntelligencePanel({ instrument = 'NIFTY', refreshKey }: MiPanelProps & { refreshKey?: number }) {
  const [data, setData] = useState<MiData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(instrument);

  useEffect(() => { setSelected(instrument); }, [instrument]);

  useEffect(() => {
    let cancelled = false;
    async function fetchMi() {
      try {
        const res = await api.getInstitutionalMIDashboard(selected);
        const payload = res?.data ?? res;
        if (!cancelled && payload) setData(payload);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    setLoading(true);
    fetchMi();
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      const jittered = 10000 * (0.8 + Math.random() * 0.4);
      timeout = setTimeout(() => {
        if (!document.hidden && !cancelled) void fetchMi();
        schedule();
      }, jittered);
    };
    schedule();
    const onVis = () => { if (!document.hidden && !cancelled) void fetchMi(); };
    document.addEventListener('visibilitychange', onVis);
    return () => { cancelled = true; if (timeout) clearTimeout(timeout); document.removeEventListener('visibilitychange', onVis); };
  }, [selected, refreshKey]);

  if (loading) return <div className="bg-card border rounded p-4 h-80 animate-pulse">Loading Market Intelligence…</div>;
  if (!data) return <div className="bg-card border rounded p-4 text-sm text-muted-foreground">Market Intelligence unavailable</div>;

  const badgeColor = (status?: string) => {
    if (status === 'CONFIRMED') return 'bg-emerald-500 text-white';
    if (status === 'WATCH') return 'bg-amber-400 text-black';
    if (status === 'POSSIBLE') return 'bg-sky-500 text-white';
    return 'bg-muted text-muted-foreground';
  };

  return (
    <div className="bg-card border border-border rounded-lg p-4 space-y-3" data-testid="mi-panel">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-sm tracking-widest uppercase">Market Intelligence</h3>
        <select value={selected} onChange={e => setSelected(e.target.value)} className="text-xs bg-secondary rounded px-2 py-1 border">
          <option value="NIFTY">NIFTY</option>
          <option value="BANKNIFTY">BANKNIFTY</option>
          <option value="SENSEX">SENSEX</option>
          <option value="BTCUSD">BTCUSD</option>
        </select>
      </div>
      <div className="text-xs space-y-1">
        <div className="flex justify-between"><span className="text-muted-foreground">Regime</span><span className="font-medium">{data.regime || '—'}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Price Action</span><span className="font-medium">{data.price_action?.structure || '—'} / {data.price_action?.trend || '—'}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Bullish Score</span><span className="font-mono font-bold">{data.bullish_score ?? '—'}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Bearish Score</span><span className="font-mono">{data.bearish_score ?? '—'}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Breakout Pressure</span><span className="font-mono text-emerald-600">{data.breakout_pressure ?? '—'}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">False Breakout Risk</span><span className={`font-mono ${(data.false_breakout_risk ?? 0) > 60 ? 'text-red-600' : ''}`}>{data.false_breakout_risk ?? '—'}</span></div>
      </div>
      <div className="border-t pt-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold">10-MINUTE SETUP</span>
          <span className={`text-xs px-2 py-0.5 rounded font-bold ${badgeColor(data.short_horizon?.status)}`}>
            {data.short_horizon?.direction || 'NEUTRAL'} — {data.short_horizon?.status || 'WATCH'}
          </span>
        </div>
        <div className="text-xs text-muted-foreground">Confidence: {data.short_horizon?.confidence ?? 0}%</div>
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold">LONG CONTINUATION</span>
          <span className={`text-xs px-2 py-0.5 rounded font-bold ${badgeColor(data.continuation?.status)}`}>
            {data.continuation?.direction || 'NEUTRAL'} — {data.continuation?.status || 'WATCH'}
          </span>
        </div>
        <div className="text-xs text-muted-foreground">Confidence: {data.continuation?.confidence ?? 0}%</div>
        <div className="text-[11px] text-muted-foreground mt-2">
          Maximum Holding: {data.max_holding || '< 2 Hours'} {data.continuation?.max_holding_minutes ? `(${data.continuation.max_holding_minutes} min)` : ''}
        </div>
      </div>
    </div>
  );
}
