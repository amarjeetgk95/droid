'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { usePolling } from '@/hooks/usePolling';
import { useMarketSession } from '@/hooks/useMarketSession';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { useCommandSection } from '@/context/AppStreamContext';
import { regimeFromSummary } from '@/lib/regime';
import { EmptyNote, TelemetryItem, TelemetryStrip, fmtINR, fmtNum } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';

/**
 * `regime.value.by_symbol` keys are the canonical broker symbols the backend
 * composes (`INSTRUMENT_SYMBOLS`); the display spelling "NIFTY 50" maps to
 * NIFTY. An unknown instrument resolves to itself and therefore reads no
 * entry rather than another symbol's payload.
 */
const REGIME_SYMBOL_KEYS: Record<string, string> = {
  NIFTY: 'NIFTY',
  'NIFTY 50': 'NIFTY',
  BANKNIFTY: 'BANKNIFTY',
  SENSEX: 'SENSEX',
};

function toRegimeSymbol(instrument: string): string {
  return REGIME_SYMBOL_KEYS[instrument.toUpperCase()] ?? instrument.toUpperCase();
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

type RestOptionsView = {
  available: boolean;
  pcr: number | null;
  callWall: number | null;
  putWall: number | null;
  lastAt: Date | null;
  error: string | null;
};

type OverviewView = {
  regime: string | null;
  support: number | null;
  resistance: number | null;
  at: string | null;
};

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function finiteOrNull(v: unknown): number | null {
  return toNumber(v);
}

function readOverview(raw: unknown): OverviewView {
  const o = asRecord(raw);
  let regime: string | null = null;
  let support: number | null = null;
  let resistance: number | null = null;
  let at: string | null = null;
  if (o) {
    const state = o.regime_state;
    if (typeof state === 'string' && state.length > 0 && state !== 'UNKNOWN') {
      regime = state.replace(/_/g, ' ');
    }
    const levels = asRecord(o.key_levels);
    if (levels) {
      support = finiteOrNull(levels.nearest_support);
      resistance = finiteOrNull(levels.nearest_resistance);
    }
    if (typeof o.timestamp === 'string') at = o.timestamp;
  }
  return { regime, support, resistance, at };
}

/**
 * Market context telemetry for the selected index.
 *
 * Regime/support/resistance come from `regime.value.by_symbol[instrument]`
 * for every supported instrument (the NIFTY-family MarketDataContext leg is
 * kept only as a pre-stream warm-up fallback); the cross-instrument REST
 * regime fetch is gone.
 *
 * The by_symbol `options_analytics` leg is the `/options/{symbol}/analytics`
 * shape (OptionsAnalytics): it carries `pcr_oi` but has no availability flag
 * and no `call_wall`/`put_wall` strikes, so PCR is read from the stream and
 * the two wall rows stay on the REST `/research/options-context` fallback —
 * still owned solely by this component at its original 60s cadence. Missing
 * legs render as "—" with a degraded note; nothing is fabricated.
 */
export function WhyStrip({ instrument }: { instrument: string }) {
  const { isOpen } = useMarketSession();
  const section = useCommandSection('regime');
  const market = useOptionalMarketDataContext();
  const contextRegime = regimeFromSummary(market?.regimeOverview, instrument);
  const symbol = toRegimeSymbol(instrument);

  const sectionValue = asRecord(section?.value);
  const bySymbol = asRecord(sectionValue?.by_symbol);
  const entry = bySymbol ? asRecord(bySymbol[symbol]) : null;
  const streamOverview = entry?.regime_overview ?? null;
  const streamOptions = asRecord(entry?.options_analytics);
  const streamPcr = streamOptions ? finiteOrNull(streamOptions.pcr_oi) : null;

  const overview = useMemo(() => {
    if (streamOverview !== null) return readOverview(streamOverview);
    return readOverview(contextRegime);
  }, [streamOverview, contextRegime]);

  // The REST view is tagged with the instrument it was fetched for so a
  // selection change can never surface the previous instrument's walls.
  const [restState, setRestState] = useState<{ instrument: string; view: RestOptionsView } | null>(
    null,
  );
  const hasDataRef = useRef<string | null>(null);

  const loadRest = useCallback(async () => {
    const requested = instrument;
    try {
      const opt = asRecord(await api.getResearchOptionsContext(requested));
      if (opt && opt.available === true) {
        const at = typeof opt.timestamp === 'string' ? new Date(opt.timestamp) : null;
        setRestState({
          instrument: requested,
          view: {
            available: true,
            pcr: finiteOrNull(opt.pcr_oi),
            callWall: finiteOrNull(opt.call_wall),
            putWall: finiteOrNull(opt.put_wall),
            lastAt: at && !Number.isNaN(at.getTime()) ? at : new Date(),
            error: null,
          },
        });
        hasDataRef.current = requested;
      } else {
        setRestState((prev) => ({
          instrument: requested,
          view: {
            available: false,
            pcr: null,
            callWall: null,
            putWall: null,
            lastAt: prev?.instrument === requested ? prev.view.lastAt : null,
            error: 'options chain unavailable',
          },
        }));
      }
    } catch (err) {
      setRestState({
        instrument: requested,
        view: {
          available: false,
          pcr: null,
          callWall: null,
          putWall: null,
          lastAt: null,
          error: err instanceof Error ? err.message : 'options context unavailable',
        },
      });
    }
  }, [instrument]);

  // Single REST owner: supplies the call/put wall rows the stream's
  // `by_symbol.options_analytics` shape does not carry.
  usePolling(
    () => {
      if (!isOpen && hasDataRef.current === instrument) return;
      return loadRest();
    },
    60000,
  );

  const restView =
    restState !== null && restState.instrument === instrument ? restState.view : null;

  const view = useMemo<ContextView>(() => {
    const failures: string[] = [];
    if (overview.regime === null) failures.push('regime classification unavailable');

    if (restView !== null && !restView.available) {
      failures.push(restView.error ?? 'options chain unavailable');
    } else if (
      restView !== null &&
      (restView.callWall === null || restView.putWall === null)
    ) {
      failures.push('options walls unavailable');
    }

    const pcr = streamPcr ?? (restView?.available ? restView.pcr : null);
    const callWall = restView?.available ? restView.callWall : null;
    const putWall = restView?.available ? restView.putWall : null;

    const ctx: MarketCtx | null =
      overview.regime !== null ||
      overview.support !== null ||
      overview.resistance !== null ||
      pcr !== null ||
      callWall !== null ||
      putWall !== null
        ? {
            regime: overview.regime,
            support: overview.support,
            resistance: overview.resistance,
            pcr,
            callWall,
            putWall,
          }
        : null;

    let lastAt: Date | null = null;
    if (overview.at) {
      const parsed = new Date(overview.at);
      if (!Number.isNaN(parsed.getTime())) lastAt = parsed;
    }
    if (!lastAt && section) {
      const parsed = new Date(section.updated_at);
      if (!Number.isNaN(parsed.getTime())) lastAt = parsed;
    }
    if (!lastAt && restView?.lastAt) lastAt = restView.lastAt;

    return {
      ctx,
      error: failures.length > 0 ? failures.join(' · ') : null,
      lastAt,
      degraded: section?.degraded === true || failures.length > 0,
    };
  }, [overview, streamPcr, restView, section]);

  const loading = view.ctx === null && section === null && restState === null;

  const streamUsed = streamOverview !== null || streamPcr !== null;
  const restUsed = restView?.available === true;
  const sourceLabel =
    streamUsed && restUsed
      ? 'SSE + REST · 60s'
      : streamUsed
        ? 'SSE · command stream'
        : 'REST · 60s poll';

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
            sourceLabel={sourceLabel}
            note={view.error ? 'partial leg(s) missing' : undefined}
          />
        </div>
      </TelemetryStrip>
    </div>
  );
}
