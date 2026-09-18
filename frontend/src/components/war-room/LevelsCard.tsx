'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { regimeFromSummary } from '@/lib/regime';
import { TelemetryStrip, TelemetryItem, fmtNum } from '@/components/ui/desk';
import type { KeyLevelsModel, MarketRegimeOverview, TechnicalIndicators, VixRegimeInfo } from '@/lib/types';

export interface LevelsCardProps {
  instrument: string;
  spot: number | null;
  target: number | null;
  stop: number | null;
  loading?: boolean;
}

type SrcMeta = { provider: string | null; at: string | null };

/** Backend truthful-zero convention: 0 / NaN / non-numbers are missing, never rendered. */
function posNum(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null;
}

function finiteNum(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** `NSE:NIFTY 50` / `nifty 50` / `NIFTY` all normalise to `NIFTY`. */
function normSymbol(s: string): string {
  return s
    .replace(/^(NSE|BSE):/i, '')
    .trim()
    .toUpperCase()
    .replace(/\s*50$/, '')
    .replace(/\s+/g, '');
}

function fmtPx(v: number): string {
  return v.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function fmtClock(at: string | null): string | null {
  if (!at) return null;
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/** `TRENDING_BULLISH` → `Trending bullish`; sentence case, never a shout. */
function humanizeToken(v: unknown): string | null {
  if (typeof v !== 'string' || !v.trim()) return null;
  const s = v.trim().toLowerCase().replace(/_+/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

type NamedLevel = { name: string; value: number };

function nearestAnchor(value: number, anchors: NamedLevel[]): NamedLevel | null {
  let best: NamedLevel | null = null;
  let bestGap = Number.POSITIVE_INFINITY;
  for (const a of anchors) {
    const gap = Math.abs(value - a.value);
    if (gap < bestGap) {
      bestGap = gap;
      best = a;
    }
  }
  return best;
}

/** `+42 pts` / `−38 pts` distance of a level from the live spot. */
function spotDeltaText(value: number, spot: number | null): string | null {
  if (spot === null) return null;
  const d = value - spot;
  const pts = Math.round(Math.abs(d));
  if (pts === 0) return 'at spot';
  return d > 0 ? `+${pts} pts` : `−${pts} pts`;
}

/** `18 pts above R1` / `at Pivot` — verdict overlays anchored to a named level. */
function levelRelText(value: number, anchors: NamedLevel[]): string | null {
  const a = nearestAnchor(value, anchors);
  if (!a) return null;
  const pts = Math.round(Math.abs(value - a.value));
  if (pts === 0) return `at ${a.name}`;
  return value > a.value ? `${pts} pts above ${a.name}` : `${pts} pts below ${a.name}`;
}

/**
 * Phase W4 key-levels rail card. Instrument-scoped: the fetch is keyed by
 * `instrument`, stale responses from a previous symbol are dropped, and any
 * payload whose symbol echo (when the backend provides one) or whose price
 * scale disagrees with the live spot renders as unavailable for the
 * requested instrument — never another symbol's pivots.
 */
export function LevelsCard({ instrument, spot, target, stop, loading }: LevelsCardProps) {
  // Summary regime leg is NIFTY-only; when it covers this instrument the 15s
  // cycle reuses it instead of fetching /regime/{symbol}/overview again.
  const market = useOptionalMarketDataContext();
  const contextRegime = regimeFromSummary(market?.regimeOverview, instrument);
  const contextRegimeRef = useRef<MarketRegimeOverview | null>(contextRegime);
  const [levels, setLevels] = useState<KeyLevelsModel | null>(null);
  const [fetching, setFetching] = useState(true);
  const [failed, setFailed] = useState<string | null>(null);
  const [echoMismatch, setEchoMismatch] = useState(false);
  const [meta, setMeta] = useState<SrcMeta>({ provider: null, at: null });

  // Regime context lives with structure, not the verdict: VIX + regime state
  // + momentum micro-row, all scoped to `instrument` (VIX is global).
  const [vix, setVix] = useState<VixRegimeInfo | null>(null);
  const [vixAt, setVixAt] = useState<string | null>(null);
  const [regime, setRegime] = useState<MarketRegimeOverview | null>(null);
  const [regimeAt, setRegimeAt] = useState<string | null>(null);
  const [tech, setTech] = useState<TechnicalIndicators | null>(null);

  // Render-phase reset on symbol change (React-endorsed previous-render
  // pattern): stale pivots must never linger under a new instrument while
  // the scoped refetch is in flight.
  const [prevInstrument, setPrevInstrument] = useState(instrument);
  if (prevInstrument !== instrument) {
    setPrevInstrument(instrument);
    setLevels(null);
    setFailed(null);
    setEchoMismatch(false);
    setMeta({ provider: null, at: null });
    setVix(null);
    setVixAt(null);
    setRegime(null);
    setRegimeAt(null);
    setTech(null);
    setFetching(true);
  }

  // Ref keeps the latest shared regime without re-identifying fetchLevelsData
  // (a new summary payload must not restart the 15s interval).
  useEffect(() => {
    contextRegimeRef.current = contextRegime;
    if (contextRegime) {
      setRegime(contextRegime);
      setRegimeAt(null);
    }
  }, [contextRegime]);

  const fetchLevelsData = useCallback(async (isInitial = false) => {
    if (typeof document !== 'undefined' && document.hidden && !isInitial) return;
    if (isInitial) setFetching(true);

    try {
      const sharedRegime = contextRegimeRef.current;
      const [levelsRes, vixRes, regimeRes, techRes] = await Promise.allSettled([
        api.getRegimeKeyLevels(instrument),
        api.getVixRegime(),
        sharedRegime
          ? Promise.resolve({ data: sharedRegime } as { data?: MarketRegimeOverview | null })
          : api.getRegimeOverview(instrument),
        typeof api.getRegimeTechnicalIndicators === 'function'
          ? api.getRegimeTechnicalIndicators(instrument)
          : Promise.resolve(null),
      ]);

      if (levelsRes.status === 'fulfilled') {
        const res = levelsRes.value;
        const data = (res as { data?: KeyLevelsModel | null } | null)?.data ?? null;
        const echo = (data as unknown as { symbol?: unknown } | null)?.symbol;
        if (typeof echo === 'string' && echo.trim() && normSymbol(echo) !== normSymbol(instrument)) {
          setLevels(null);
          setEchoMismatch(true);
        } else {
          setLevels(data);
          setEchoMismatch(false);
          setFailed(null);
        }
        const m = (res as { meta?: { provider?: unknown; timestamp?: unknown } } | null)?.meta;
        setMeta({
          provider: typeof m?.provider === 'string' ? m.provider : null,
          at: typeof m?.timestamp === 'string' ? m.timestamp : null,
        });
      } else if (isInitial) {
        setLevels(null);
        setFailed(levelsRes.reason instanceof Error ? levelsRes.reason.message : 'key levels unavailable');
      }

      if (vixRes.status === 'fulfilled' && vixRes.value) {
        const data = vixRes.value.data ?? null;
        setVix(data && typeof data.vix_value === 'number' && data.vix_value > 0 ? data : null);
        const at = (vixRes.value as { meta?: { timestamp?: unknown } } | null)?.meta?.timestamp;
        setVixAt(typeof at === 'string' ? at : null);
      }

      if (regimeRes.status === 'fulfilled' && regimeRes.value) {
        const data = regimeRes.value.data ?? null;
        const echo = typeof data?.symbol === 'string' ? data.symbol : null;
        setRegime(data && echo && normSymbol(echo) !== normSymbol(instrument) ? null : data);
        const at = (regimeRes.value as { meta?: { timestamp?: unknown } } | null)?.meta?.timestamp;
        setRegimeAt(typeof at === 'string' ? at : null);
      }

      if (techRes.status === 'fulfilled' && techRes.value) {
        setTech((techRes.value as { data?: TechnicalIndicators | null } | null)?.data ?? null);
      }
    } catch (err) {
      if (isInitial) {
        setFailed(err instanceof Error ? err.message : 'key levels unavailable');
      }
    } finally {
      if (isInitial) setFetching(false);
    }
  }, [instrument]);

  useEffect(() => {
    void fetchLevelsData(true);
    // Refresh key levels and technical indicators in real-time every 15s
    const id = setInterval(() => {
      void fetchLevelsData(false);
    }, 15000);
    return () => clearInterval(id);
  }, [fetchLevelsData]);

  const liveSpot = posNum(spot);
  const classic = levels?.classic_pivots ?? null;

  const ladder: NamedLevel[] = [];
  const r2 = classic ? posNum(classic.r2) : null;
  const r1 = classic ? posNum(classic.r1) : null;
  const piv = classic ? posNum(classic.pivot) : null;
  const s1 = classic ? posNum(classic.s1) : null;
  const s2 = classic ? posNum(classic.s2) : null;
  if (r2 !== null) ladder.push({ name: 'R2', value: r2 });
  if (r1 !== null) ladder.push({ name: 'R1', value: r1 });
  if (piv !== null) ladder.push({ name: 'Pivot', value: piv });
  if (s1 !== null) ladder.push({ name: 'S1', value: s1 });
  if (s2 !== null) ladder.push({ name: 'S2', value: s2 });

  const nearR = posNum(levels?.nearest_resistance);
  const nearS = posNum(levels?.nearest_support);
  const nearRDist = finiteNum(levels?.distance_to_resistance_pts);
  const nearSDist = finiteNum(levels?.distance_to_support_pts);

  const poc = posNum(levels?.poc);
  const vah = posNum(levels?.vah);
  const val = posNum(levels?.val);

  const dayOpen = posNum(levels?.day_open);
  const pdH = posNum(levels?.prior_day_high);
  const pdL = posNum(levels?.prior_day_low);
  const pdC = posNum(levels?.prior_day_close);

  const hasAnyLevel =
    ladder.length > 0 ||
    nearR !== null ||
    nearS !== null ||
    poc !== null ||
    vah !== null ||
    val !== null ||
    dayOpen !== null ||
    pdH !== null ||
    pdL !== null ||
    pdC !== null;

  // Scale guard: index futures trade thousands of points apart, so a pivot
  // sitting >25% away from the live spot cannot belong to this instrument.
  const pivotRef = piv ?? (nearR !== null && nearS !== null ? (nearR + nearS) / 2 : (poc ?? null));
  const scaleMismatch =
    !echoMismatch &&
    pivotRef !== null &&
    liveSpot !== null &&
    Math.abs(pivotRef - liveSpot) / liveSpot > 0.25;

  const showSkeleton = (loading === true || fetching) && !hasAnyLevel && !echoMismatch && !scaleMismatch && failed === null;
  if (showSkeleton) {
    return (
      <section className="card" aria-label={`${instrument} key levels`}>
        <div className="card-hd">
          <h2 className="card-title">Key levels</h2>
          <span className="card-meta num">{instrument}</span>
        </div>
        <div className="card-bd" style={{ display: 'grid', gap: 6 }} aria-label="Loading key levels">
          {[92, 78, 64, 78, 92].map((w, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <div className="skel" style={{ height: 12, width: 64 }}>.</div>
              <div className="skel num" style={{ height: 12, width: w }}>.</div>
            </div>
          ))}
        </div>
      </section>
    );
  }

  if (echoMismatch || scaleMismatch || failed !== null || !hasAnyLevel) {
    return (
      <section className="card" aria-label={`${instrument} key levels`}>
        <div className="card-hd">
          <h2 className="card-title">Key levels</h2>
          <span className="card-meta num">{instrument}</span>
        </div>
        <div className="card-bd">
          <p
            className="muted num"
            style={{ margin: 0, fontSize: 12 }}
            title={failed ?? (echoMismatch || scaleMismatch ? 'response did not match the requested symbol' : undefined)}
          >
            levels unavailable for {instrument}
          </p>
        </div>
      </section>
    );
  }

  const spotVsPivot =
    liveSpot !== null && piv !== null
      ? Math.abs(liveSpot - piv) / piv <= 0.0005
        ? { text: 'at pivot', tone: 'chip--neut' }
        : liveSpot > piv
          ? { text: 'above pivot', tone: 'chip--up' }
          : { text: 'below pivot', tone: 'chip--down' }
      : null;

  const verdictTarget = posNum(target);
  const verdictStop = posNum(stop);
  const targetParts: string[] = [];
  const stopParts: string[] = [];
  if (verdictTarget !== null) {
    const d = spotDeltaText(verdictTarget, liveSpot);
    if (d) targetParts.push(d);
    const r = levelRelText(verdictTarget, ladder);
    if (r) targetParts.push(r);
  }
  if (verdictStop !== null) {
    const d = spotDeltaText(verdictStop, liveSpot);
    if (d) stopParts.push(d);
    const r = levelRelText(verdictStop, ladder);
    if (r) stopParts.push(r);
  }

  const clock = fmtClock(meta.at);
  const freshness = meta.provider || clock ? `${meta.provider ?? 'regime engine'}${clock ? ` · ${clock}` : ''}` : null;

  const vixLabel = vix ? humanizeToken(vix.regime_category) : null;
  const regimeLabel = regime ? humanizeToken(regime.regime_state) : null;
  const regimeConf =
    regime && typeof regime.confidence_score === 'number' && Number.isFinite(regime.confidence_score) && regime.confidence_score > 0
      ? Math.round(regime.confidence_score)
      : null;
  const showTech =
    tech !== null &&
    typeof tech.rsi_14 === 'number' &&
    Number.isFinite(tech.rsi_14) &&
    ((typeof tech.adx_14 === 'number' && tech.adx_14 > 0) ||
      (typeof tech.atr_14 === 'number' && tech.atr_14 > 0) ||
      (typeof tech.supertrend_value === 'number' && tech.supertrend_value > 0));
  // Tone only on a published direction — a missing field must not read bullish.
  const supertrendDir =
    showTech && tech !== null && typeof tech.supertrend_direction === 'string'
      ? tech.supertrend_direction.toUpperCase()
      : null;
  const showRegime = (vix && vixLabel) || (regime && regimeLabel) || showTech;

  return (
    <section className="card" aria-label={`${instrument} key levels`}>
      <div className="card-hd">
        <h2 className="card-title">Key levels</h2>
        <span className="card-meta num">{instrument}</span>
      </div>
      <div className="card-bd" style={{ padding: '4px 12px 8px' }}>
        {spotVsPivot ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0 2px' }}>
            <span className={`chip ${spotVsPivot.tone}`}>{spotVsPivot.text}</span>
            {liveSpot !== null && piv !== null ? (
              <span className="faint num" style={{ fontSize: 11 }}>
                spot {fmtPx(liveSpot)} vs pivot {fmtPx(piv)}
              </span>
            ) : null}
          </div>
        ) : null}

        {ladder.length > 0 ? (
          <div style={{ marginTop: 4 }}>
            <div className="micro-label" style={{ fontSize: 10 }}>Classic pivots</div>
            {ladder.map((row) => {
              const d = spotDeltaText(row.value, liveSpot);
              return (
                <div key={row.name} className="sg-kv">
                  <span className="l">{row.name}</span>
                  <span className="v num">
                    {fmtPx(row.value)}
                    {d ? <span className="faint" style={{ fontWeight: 400 }}> · {d}</span> : null}
                  </span>
                </div>
              );
            })}
          </div>
        ) : null}

        {nearR !== null || nearS !== null ? (
          <div style={{ marginTop: 6 }}>
            <div className="micro-label" style={{ fontSize: 10 }}>Nearest structure</div>
            {nearR !== null ? (
              <div className="sg-kv">
                <span className="l">Resistance</span>
                <span className="v num">
                  {fmtPx(nearR)}
                  <span className="faint" style={{ fontWeight: 400 }}>
                    {' · +'}
                    {nearRDist !== null && nearRDist > 0
                      ? fmtNum(nearRDist, 0)
                      : liveSpot !== null
                        ? fmtNum(Math.max(0, nearR - liveSpot), 0)
                        : '—'}{' '}
                    pts
                  </span>
                </span>
              </div>
            ) : null}
            {nearS !== null ? (
              <div className="sg-kv">
                <span className="l">Support</span>
                <span className="v num">
                  {fmtPx(nearS)}
                  <span className="faint" style={{ fontWeight: 400 }}>
                    {' · −'}
                    {nearSDist !== null && nearSDist > 0
                      ? fmtNum(nearSDist, 0)
                      : liveSpot !== null
                        ? fmtNum(Math.max(0, liveSpot - nearS), 0)
                        : '—'}{' '}
                    pts
                  </span>
                </span>
              </div>
            ) : null}
          </div>
        ) : null}

        {poc !== null || vah !== null || val !== null ? (
          <div style={{ marginTop: 6 }}>
            <div className="micro-label" style={{ fontSize: 10 }}>Value area</div>
            {poc !== null ? (
              <div className="sg-kv">
                <span className="l">POC</span>
                <span className="v num">{fmtPx(poc)}</span>
              </div>
            ) : null}
            {vah !== null ? (
              <div className="sg-kv">
                <span className="l">VAH</span>
                <span className="v num">{fmtPx(vah)}</span>
              </div>
            ) : null}
            {val !== null ? (
              <div className="sg-kv">
                <span className="l">VAL</span>
                <span className="v num">{fmtPx(val)}</span>
              </div>
            ) : null}
          </div>
        ) : null}

        {dayOpen !== null || pdH !== null || pdL !== null || pdC !== null ? (
          <div style={{ marginTop: 6 }}>
            <div className="micro-label" style={{ fontSize: 10 }}>Session reference</div>
            {dayOpen !== null ? (
              <div className="sg-kv">
                <span className="l">Day open</span>
                <span className="v num">{fmtPx(dayOpen)}</span>
              </div>
            ) : null}
            {pdH !== null ? (
              <div className="sg-kv">
                <span className="l">Prior high</span>
                <span className="v num">{fmtPx(pdH)}</span>
              </div>
            ) : null}
            {pdL !== null ? (
              <div className="sg-kv">
                <span className="l">Prior low</span>
                <span className="v num">{fmtPx(pdL)}</span>
              </div>
            ) : null}
            {pdC !== null ? (
              <div className="sg-kv">
                <span className="l">Prior close</span>
                <span className="v num">{fmtPx(pdC)}</span>
              </div>
            ) : null}
          </div>
        ) : null}

        {verdictTarget !== null || verdictStop !== null ? (
          <div style={{ marginTop: 6 }}>
            <div className="micro-label" style={{ fontSize: 10 }}>Verdict overlays</div>
            {verdictTarget !== null ? (
              <div className="sg-kv">
                <span className="l">Target</span>
                <span className="v num">
                  {fmtPx(verdictTarget)}
                  {targetParts.length > 0 ? (
                    <span className="faint" style={{ fontWeight: 400 }}> · {targetParts.join(' · ')}</span>
                  ) : null}
                </span>
              </div>
            ) : null}
            {verdictStop !== null ? (
              <div className="sg-kv">
                <span className="l">Stop</span>
                <span className="v num">
                  {fmtPx(verdictStop)}
                  {stopParts.length > 0 ? (
                    <span className="faint" style={{ fontWeight: 400 }}> · {stopParts.join(' · ')}</span>
                  ) : null}
                </span>
              </div>
            ) : null}
          </div>
        ) : null}

        {freshness ? (
          <div className="faint num" style={{ fontSize: 11, marginTop: 6 }} title={meta.at ?? undefined}>
            {freshness}
          </div>
        ) : null}

        {showRegime ? (
          <div style={{ marginTop: 8 }}>
            <div className="micro-label" style={{ fontSize: 10, marginBottom: 4 }}>Regime</div>
            <TelemetryStrip aria-label="Volatility and regime">
              {vix && vixLabel ? (
                <TelemetryItem
                  label="VIX"
                  value={<span className="num" style={{ fontSize: 12 }}>{fmtNum(vix.vix_value, 2)}</span>}
                  sub={vixLabel}
                  title={vixAt ? `India VIX · ${fmtClock(vixAt) ?? ''}` : 'India VIX'}
                />
              ) : null}
              {regime && regimeLabel ? (
                <TelemetryItem
                  label="Regime"
                  value={<span className="num" style={{ fontSize: 12 }}>{regimeLabel}</span>}
                  sub={regimeConf !== null ? `conf ${regimeConf}%` : undefined}
                  title={regimeAt ? `${regime?.symbol ?? instrument} · ${fmtClock(regimeAt) ?? ''}` : (regime?.symbol ?? instrument)}
                />
              ) : null}
              {showTech && tech ? (
                <>
                  <TelemetryItem
                    label="RSI 14"
                    value={<span className="num" style={{ fontSize: 12 }}>{fmtNum(tech.rsi_14, 1)}</span>}
                  />
                  <TelemetryItem
                    label="ADX 14"
                    value={<span className="num" style={{ fontSize: 12 }}>{fmtNum(tech.adx_14, 1)}</span>}
                  />
                  <TelemetryItem
                    label="ATR 14"
                    value={<span className="num" style={{ fontSize: 12 }}>{fmtNum(tech.atr_14, 1)}</span>}
                  />
                  <TelemetryItem
                    label="Supertrend"
                    value={<span className="num" style={{ fontSize: 12 }}>{fmtNum(tech.supertrend_value, 1)}</span>}
                    sub={humanizeToken(tech.supertrend_direction) ?? undefined}
                    tone={supertrendDir === 'BULLISH' ? 'bull' : supertrendDir === 'BEARISH' ? 'bear' : undefined}
                  />
                </>
              ) : null}
            </TelemetryStrip>
          </div>
        ) : null}
      </div>
    </section>
  );
}
