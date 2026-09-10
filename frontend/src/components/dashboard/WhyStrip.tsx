'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { EmptyNote, fmtINR, fmtNum } from '@/components/ui/desk';

function toRegimeSymbol(instrument: string): string {
  if (instrument === 'NIFTY 50') return 'NIFTY';
  return instrument;
}

type MarketCtx = {
  regime: string | null;
  support: unknown;
  resistance: unknown;
  pcr: unknown;
  callWall: unknown;
  putWall: unknown;
};

export function WhyStrip({ instrument }: { instrument: string }) {
  const [ctx, setCtx] = useState<MarketCtx | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    setLoading(true);
    try {
      const regimeSymbol = toRegimeSymbol(instrument);
      const [regimeRes, optRes] = await Promise.allSettled([
        api.getRegimeOverview(regimeSymbol),
        api.getResearchOptionsContext(instrument),
      ]);

      let regimeState: string | null = null;
      let support: unknown = null;
      let resistance: unknown = null;
      if (regimeRes.status === 'fulfilled') {
        const raw = regimeRes.value as unknown as { data?: Record<string, unknown> } | Record<string, unknown>;
        const payload = (raw as { data?: Record<string, unknown> })?.data
          ?? (raw as Record<string, unknown>);
        const state = (payload as Record<string, unknown>)?.regime_state;
        if (typeof state === 'string' && state.length) regimeState = state.replace(/_/g, ' ');
        const kl = (payload as Record<string, unknown>)?.key_levels as Record<string, unknown> | undefined;
        if (kl) {
          support = kl.nearest_support ?? null;
          resistance = kl.nearest_resistance ?? null;
        }
      }

      let pcr: unknown = null;
      let callWall: unknown = null;
      let putWall: unknown = null;
      if (optRes.status === 'fulfilled') {
        const opt = optRes.value as Record<string, unknown>;
        pcr = opt?.pcr_oi ?? null;
        callWall = opt?.call_wall ?? null;
        putWall = opt?.put_wall ?? null;
      }

      setCtx({ regime: regimeState, support, resistance, pcr, callWall, putWall });
    } catch {
      setCtx(null);
    } finally {
      setLoading(false);
    }
  }, [instrument]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void load();
    }, 60000);
    return () => clearInterval(id);
  }, [load]);

  if (loading && !ctx) {
    return (
      <section className="card" aria-label="Market context">
        <div className="card-hd">
          <h2 className="card-title">Why this view — market context</h2>
          <span className="card-meta">{instrument}</span>
        </div>
        <div className="card-bd">
          <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="skel" style={{ height: 76 }}>.</div>
            ))}
          </div>
        </div>
      </section>
    );
  }

  if (!ctx) {
    return (
      <section className="card" aria-label="Market context">
        <div className="card-hd">
          <h2 className="card-title">Why this view — market context</h2>
          <span className="card-meta">{instrument}</span>
        </div>
        <div className="card-bd">
          <EmptyNote>Market context unavailable.</EmptyNote>
        </div>
      </section>
    );
  }

  const items: Array<{ label: string; value: string; sub: string }> = [
    { label: 'Regime', value: ctx.regime ?? '—', sub: 'Trend state' },
    { label: 'Support', value: fmtINR(ctx.support), sub: 'Nearest floor' },
    { label: 'Resistance', value: fmtINR(ctx.resistance), sub: 'Nearest ceiling' },
    { label: 'PCR · OI', value: fmtNum(ctx.pcr), sub: 'Positioning' },
    { label: 'Call wall', value: fmtINR(ctx.callWall), sub: 'Supply zone' },
    { label: 'Put wall', value: fmtINR(ctx.putWall), sub: 'Demand zone' },
  ];

  return (
    <section className="card" aria-label="Market context">
      <div className="card-hd">
        <h2 className="card-title">Why this view — market context</h2>
        <span className="card-meta">{instrument}</span>
      </div>
      <div className="card-bd">
        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
          {items.map((item) => (
            <div key={item.label} className="stat">
              <div className="stat-l">{item.label}</div>
              <div className="stat-v num" style={{ fontSize: 16 }}>{item.value}</div>
              <div className="stat-s">{item.sub}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
