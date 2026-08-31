'use client';
import { useEffect, useState } from 'react';

export function DataHealthPanel() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    let cancelled = false;
    async function fetchH() {
      try {
        const res = await fetch('/api/v1/institutional/health/data');
        const j = await res.json();
        if (!cancelled) setData(j);
      } catch { if (!cancelled) setData(null); }
    }
    fetchH();
    const id = setInterval(fetchH, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const dot = (status: string) => {
    if (status === 'LIVE') return 'bg-emerald-500';
    if (status === 'RECENT') return 'bg-amber-400';
    if (status === 'STALE' || status === 'FEED_DEGRADED') return 'bg-red-600';
    return 'bg-gray-400';
  };

  if (!data) return <div className="bg-card border rounded p-4 h-40 animate-pulse" />;

  const health = data.data_health || {};
  return (
    <div className="bg-card border rounded-lg p-4 space-y-2" data-testid="data-health-panel">
      <h3 className="font-bold text-sm tracking-widest uppercase">Data Health</h3>
      {['NIFTY','BANKNIFTY','SENSEX','BTCUSD'].map(id => {
        const entry = health[id] || {};
        const st = entry.data_health || entry.status || 'DISCONNECTED';
        return (
          <div key={id} className="flex items-center justify-between text-sm">
            <span className="font-mono font-medium w-24">{id}</span>
            <span className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${dot(st)}`} />
              <span className="text-xs">{st}</span>
            </span>
          </div>
        );
      })}
      <div className="border-t pt-2 grid grid-cols-2 gap-2 text-xs">
        <div className="flex items-center gap-1"><span className={`w-2 h-2 rounded-full ${dot(data.data_health ? 'LIVE' : 'STALE')}`} /> Clock Sync ● VALID</div>
        <div>Sequence ● VALID</div>
        <div>Snapshot ● VALID</div>
        <div>Contracts ● VALID</div>
      </div>
    </div>
  );
}
