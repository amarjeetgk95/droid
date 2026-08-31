'use client';
import { useEffect, useState } from 'react';

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

export function MarketIntelligencePanel({ instrument = 'NIFTY' }: MiPanelProps) {
  const [data, setData] = useState<MiData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(instrument);

  useEffect(() => { setSelected(instrument); }, [instrument]);

  useEffect(() => {
    let cancelled = false;
    async function fetchMi() {
      try {
        const base = (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/+$/, '');
        const url = base
          ? `${base}/api/v1/institutional/dashboard/market-intelligence?instrument_id=${selected}`
          : `/api/v1/institutional/dashboard/market-intelligence?instrument_id=${selected}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error('fetch failed');
        const json = await res.json();
        // unwrap ApiResponse {data: ...} if present, else direct
        const payload = json.data ?? json;
        if (!cancelled) setData(payload);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    setLoading(true);
    fetchMi();
    const id = setInterval(fetchMi, 8000);
    return () => { cancelled = true; clearInterval(id); };
  }, [selected]);

  if (loading) return <div className="bg-card border rounded p-4 h-80 animate-pulse">Loading Market Intelligence…</div>;
  if (!data) return <div className="bg-card border rounded p-4 text-sm text-muted-foreground">Market Intelligence unavailable</div>;

  const badgeColor = (status: string) => {
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
        <div className="flex justify-between"><span className="text-muted-foreground">Price Action</span><span className="font-medium">{data.price_action?.structure} / {data.price_action?.trend}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Bullish Score</span><span className="font-mono font-bold">{data.bullish_score}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Bearish Score</span><span className="font-mono">{data.bearish_score}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Breakout Pressure</span><span className="font-mono text-emerald-600">{data.breakout_pressure}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">False Breakout Risk</span><span className={`font-mono ${data.false_breakout_risk > 60 ? 'text-red-600' : ''}`}>{data.false_breakout_risk}</span></div>
      </div>
      <div className="border-t pt-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold">10-MINUTE SETUP</span>
          <span className={`text-xs px-2 py-0.5 rounded font-bold ${badgeColor(data.short_horizon.status)}`}>{data.short_horizon.direction} — {data.short_horizon.status}</span>
        </div>
        <div className="text-xs text-muted-foreground">Confidence: {data.short_horizon.confidence}%</div>
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold">LONG CONTINUATION</span>
          <span className={`text-xs px-2 py-0.5 rounded font-bold ${badgeColor(data.continuation.status)}`}>{data.continuation.direction} — {data.continuation.status}</span>
        </div>
        <div className="text-xs text-muted-foreground">Confidence: {data.continuation.confidence}%</div>
        <div className="text-[11px] text-muted-foreground mt-2">Maximum Holding: {data.max_holding} ({data.continuation.max_holding_minutes} min)</div>
      </div>
    </div>
  );
}
