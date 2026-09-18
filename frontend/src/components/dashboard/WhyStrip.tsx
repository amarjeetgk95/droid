'use client';

import { useCallback, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { usePolling } from '@/hooks/usePolling';
import { useMarketSession } from '@/hooks/useMarketSession';
import { EmptyNote, TelemetryItem, TelemetryStrip, fmtINR, fmtNum } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';

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

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function finiteOrNull(v: unknown): number | null {
  return toNumber(v);
}

export function WhyStrip({ instrument }: { instrument: string }) {
  const { isOpen } = useMarketSession();
  const [ctx, setCtx] = useState<MarketCtx | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastAt, setLastAt] = useState<Date | null>(null);
  const loadedRef = useRef(false);
  const hasDataRef = useRef(false);

  const load = useCallback(async () => {
    const initial = !loadedRef.current;
    if (initial) setLoading(true);
    try {
      const regimeSymbol = toRegimeSymbol(instrument);
      const [regimeRes, optRes] = await Promise.allSettled([
        api.getRegimeOverview(regimeSymbol),
        api.getResearchOptionsContext(instrument),
      ]);

      let regimeState: string | null = null;
      let support: number | null = null;
      let resistance: number | null = null;
      let regimeAt: string | null = null;
      const failures: string[] = [];

      if (regimeRes.status === 'fulfilled') {
        const payload = asRecord((regimeRes.value as { data?: unknown })?.data);
        if (payload) {
          const state = payload.regime_state;
          if (typeof state === 'string' && state.length && state !== 'UNKNOWN') {
            regimeState = state.replace(/_/g, ' ');
          }
          const kl = asRecord(payload.key_levels);
          if (kl) {
            support = finiteOrNull(kl.nearest_support);
            resistance = finiteOrNull(kl.nearest_resistance);
          }
          const ts = payload.timestamp;
          if (typeof ts === 'string') regimeAt = ts;
        } else {
          failures.push('regime payload unusable');
        }
      } else {
        failures.push(
          regimeRes.reason instanceof Error ? regimeRes.reason.message : 'regime unavailable',
        );
      }

      let pcr: number | null = null;
      let callWall: number | null = null;
      let putWall: number | null = null;
      if (optRes.status === 'fulfilled') {
        const opt = asRecord(optRes.value);
        if (opt && opt.available === true) {
          pcr = finiteOrNull(opt.pcr_oi);
          callWall = finiteOrNull(opt.call_wall);
          putWall = finiteOrNull(opt.put_wall);
        } else {
          failures.push('options chain unavailable');
        }
      } else {
        failures.push(
          optRes.reason instanceof Error ? optRes.reason.message : 'options context unavailable',
        );
      }

      setCtx({ regime: regimeState, support, resistance, pcr, callWall, putWall });
      setError(failures.length > 0 ? failures.join(' · ') : null);
      if (regimeRes.status === 'fulfilled' || optRes.status === 'fulfilled') {
        hasDataRef.current = true;
        setLastAt(
          regimeAt !== null && !Number.isNaN(new Date(regimeAt).getTime())
            ? new Date(regimeAt)
            : new Date(),
        );
      }
    } catch (err) {
      setCtx(null);
      setError(err instanceof Error ? err.message : 'Market context unavailable');
    } finally {
      loadedRef.current = true;
      setLoading(false);
    }
  }, [instrument]);

  usePolling(() => {
    if (!isOpen && hasDataRef.current) return;
    return load();
  }, 60000);

  const header = (
    <div className="telemetry-item" style={{ background: 'var(--ds-surface-subtle)' }}>
      <span className="t-label">CONTEXT</span>
      <span className="t-val" style={{ fontSize: 12 }}>{instrument}</span>
    </div>
  );

  if (loading && !ctx) {
    return (
      <div aria-label="Market context">
        <TelemetryStrip>
          {header}
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="telemetry-item" style={{ minWidth: 90 }}>
              <div className="skel" style={{ height: 9, width: 40, marginBottom: 3 }}>.</div>
              <div className="skel" style={{ height: 13, width: 65 }}>.</div>
            </div>
          ))}
        </TelemetryStrip>
      </div>
    );
  }

  if (!ctx) {
    return (
      <div aria-label="Market context">
        <TelemetryStrip>
          {header}
          <div className="telemetry-item" style={{ flex: 1 }}>
            <EmptyNote>
              {error ? `Market context unavailable — ${error}` : 'Market context telemetry unavailable.'}
            </EmptyNote>
          </div>
        </TelemetryStrip>
      </div>
    );
  }

  const items: Array<{ label: string; value: string; sub: string }> = [
    { label: 'Regime', value: ctx.regime ?? '—', sub: 'Trend' },
    { label: 'Support', value: fmtINR(ctx.support), sub: 'Floor' },
    { label: 'Resistance', value: fmtINR(ctx.resistance), sub: 'Ceiling' },
    { label: 'PCR · OI', value: fmtNum(ctx.pcr), sub: 'Flow' },
    { label: 'Call wall', value: fmtINR(ctx.callWall), sub: 'Supply' },
    { label: 'Put wall', value: fmtINR(ctx.putWall), sub: 'Demand' },
  ];

  return (
    <div aria-label="Market context">
      <TelemetryStrip>
        {header}
        {items.map((item) => (
          <TelemetryItem
            key={item.label}
            label={item.label}
            value={item.value}
            sub={item.sub}
          />
        ))}
        <div className="telemetry-item" style={{ marginLeft: 'auto' }}>
          <FreshnessClock
            lastAt={lastAt}
            marketClosed={!isOpen}
            dataQuality={error ? 'DEGRADED' : null}
            sourceLabel="REST · 60s poll"
            note={error ? 'partial leg(s) missing' : undefined}
          />
        </div>
      </TelemetryStrip>
    </div>
  );
}
