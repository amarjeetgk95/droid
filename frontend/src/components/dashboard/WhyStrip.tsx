'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import type { MarketRegimeOverview } from '@/lib/types';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { usePolling } from '@/hooks/usePolling';
import { useMarketSession } from '@/hooks/useMarketSession';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { useCommandSection } from '@/context/AppStreamContext';
import { regimeFromSummary } from '@/lib/regime';
import { isNiftySymbol } from '@/lib/symbols';
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

type ContextView = {
  ctx: MarketCtx | null;
  error: string | null;
  lastAt: Date | null;
  degraded: boolean;
};

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function finiteOrNull(v: unknown): number | null {
  return toNumber(v);
}

export function WhyStrip({ instrument }: { instrument: string }) {
  const { isOpen } = useMarketSession();
  // The unified stream's `regime` slice is pinned to the NIFTY family; it is
  // preferred only when it actually carries usable data for this instrument.
  // Non-NIFTY symbols (BANKNIFTY/SENSEX) and stream-miss cases keep the
  // pre-conversion REST fetch below, owned solely by this component at its
  // original 60s cadence.
  const section = useCommandSection('regime');
  const market = useOptionalMarketDataContext();
  const contextRegime = regimeFromSummary(market?.regimeOverview, instrument);
  const niftyFamily = isNiftySymbol(instrument);

  const sectionValue = asRecord(section?.value);
  const sectionRawOverview = asRecord(sectionValue?.regime_overview);
  const sectionRegime = sectionRawOverview
    ? regimeFromSummary(sectionRawOverview as unknown as MarketRegimeOverview, instrument)
    : null;
  const sectionOptions = asRecord(sectionValue?.options_analytics);
  const sectionOptionsReady = niftyFamily && sectionOptions?.available === true;
  const streamUsable = niftyFamily && (sectionRegime !== null || sectionOptionsReady);

  const streamView = useMemo<ContextView>(() => {
    const overview = sectionRegime ?? contextRegime;

    let regime: string | null = null;
    let support: number | null = null;
    let resistance: number | null = null;
    let regimeAt: string | null = null;
    if (overview) {
      const state = overview.regime_state;
      if (typeof state === 'string' && state.length > 0 && state !== 'UNKNOWN') {
        regime = state.replace(/_/g, ' ');
      }
      const levels = asRecord(overview.key_levels);
      if (levels) {
        support = finiteOrNull(levels.nearest_support);
        resistance = finiteOrNull(levels.nearest_resistance);
      }
      const at = (overview as MarketRegimeOverview & { timestamp?: unknown }).timestamp;
      if (typeof at === 'string') regimeAt = at;
    }

    const pcr = sectionOptionsReady ? finiteOrNull(sectionOptions?.pcr_oi) : null;
    const callWall = sectionOptionsReady ? finiteOrNull(sectionOptions?.call_wall) : null;
    const putWall = sectionOptionsReady ? finiteOrNull(sectionOptions?.put_wall) : null;

    const failures: string[] = [];
    if (!niftyFamily) {
      failures.push('context telemetry covers NIFTY only');
    } else {
      if (!overview) failures.push('regime classification unavailable');
      if (!sectionOptionsReady) failures.push('options chain unavailable');
    }

    const ctx: MarketCtx | null =
      regime !== null ||
      support !== null ||
      resistance !== null ||
      pcr !== null ||
      callWall !== null ||
      putWall !== null
        ? { regime, support, resistance, pcr, callWall, putWall }
        : null;

    let lastAt: Date | null = null;
    if (regimeAt) {
      const parsed = new Date(regimeAt);
      if (!Number.isNaN(parsed.getTime())) lastAt = parsed;
    }
    if (!lastAt && section) {
      const parsed = new Date(section.updated_at);
      if (!Number.isNaN(parsed.getTime())) lastAt = parsed;
    }

    return {
      ctx,
      error: failures.length > 0 ? failures.join(' · ') : null,
      lastAt,
      degraded: section?.degraded ?? false,
    };
  }, [section, sectionRegime, contextRegime, niftyFamily, sectionOptions, sectionOptionsReady]);

  const [restView, setRestView] = useState<ContextView | null>(null);
  const [restLoading, setRestLoading] = useState(true);
  const loadedRef = useRef(false);
  const hasDataRef = useRef(false);

  const loadRest = useCallback(async () => {
    const initial = !loadedRef.current;
    if (initial) setRestLoading(true);
    try {
      const regimeSymbol = toRegimeSymbol(instrument);
      const [regimeRes, optRes] = await Promise.allSettled([
        contextRegime
          ? Promise.resolve({ data: contextRegime } as { data?: unknown })
          : api.getRegimeOverview(regimeSymbol),
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

      const ctx: MarketCtx | null =
        regimeState !== null ||
        support !== null ||
        resistance !== null ||
        pcr !== null ||
        callWall !== null ||
        putWall !== null
          ? { regime: regimeState, support, resistance, pcr, callWall, putWall }
          : null;

      const anyFulfilled = regimeRes.status === 'fulfilled' || optRes.status === 'fulfilled';
      if (anyFulfilled) hasDataRef.current = true;
      const lastAt =
        regimeAt !== null && !Number.isNaN(new Date(regimeAt).getTime())
          ? new Date(regimeAt)
          : new Date();
      setRestView((prev) => ({
        ctx,
        error: failures.length > 0 ? failures.join(' · ') : null,
        lastAt: anyFulfilled ? lastAt : (prev?.lastAt ?? null),
        degraded: failures.length > 0,
      }));
    } catch (err) {
      setRestView({
        ctx: null,
        error: err instanceof Error ? err.message : 'Market context unavailable',
        lastAt: null,
        degraded: true,
      });
    } finally {
      loadedRef.current = true;
      setRestLoading(false);
    }
  }, [instrument, contextRegime]);

  usePolling(
    () => {
      if (streamUsable) return;
      if (!isOpen && hasDataRef.current) return;
      return loadRest();
    },
    60000,
    !streamUsable,
  );

  const usingRest = !streamUsable && restView !== null;
  const view: ContextView = usingRest && restView ? restView : streamView;
  const loading = !streamUsable && restView === null && restLoading && streamView.ctx === null;

  const header = (
    <div className="telemetry-item" style={{ background: 'var(--ds-surface-subtle)' }}>
      <span className="t-label">CONTEXT</span>
      <span className="t-val" style={{ fontSize: 12 }}>{instrument}</span>
    </div>
  );

  if (loading) {
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

  if (!view.ctx) {
    return (
      <div aria-label="Market context">
        <TelemetryStrip>
          {header}
          <div className="telemetry-item" style={{ flex: 1 }}>
            <EmptyNote>
              {view.error
                ? `Market context unavailable — ${view.error}`
                : 'Market context telemetry unavailable.'}
            </EmptyNote>
          </div>
        </TelemetryStrip>
      </div>
    );
  }

  const items: Array<{ label: string; value: string; sub: string }> = [
    { label: 'Regime', value: view.ctx.regime ?? '—', sub: 'Trend' },
    { label: 'Support', value: fmtINR(view.ctx.support), sub: 'Floor' },
    { label: 'Resistance', value: fmtINR(view.ctx.resistance), sub: 'Ceiling' },
    { label: 'PCR · OI', value: fmtNum(view.ctx.pcr), sub: 'Flow' },
    { label: 'Call wall', value: fmtINR(view.ctx.callWall), sub: 'Supply' },
    { label: 'Put wall', value: fmtINR(view.ctx.putWall), sub: 'Demand' },
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
            lastAt={view.lastAt}
            marketClosed={!isOpen}
            dataQuality={view.error || view.degraded ? 'DEGRADED' : null}
            sourceLabel={streamUsable ? 'SSE · command stream' : 'REST · 60s poll'}
            note={view.error ? 'partial leg(s) missing' : undefined}
          />
        </div>
      </TelemetryStrip>
    </div>
  );
}
