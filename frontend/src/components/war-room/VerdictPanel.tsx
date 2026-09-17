'use client';

import { memo } from 'react';
import type { HourForecast } from '@/lib/types';
import { fmtNum, TelemetryStrip, TelemetryItem, StackedProbabilityBar } from '@/components/ui/desk';
import {
  UNSETTLEABLE_NOTE,
  asStringList,
  calibrationLabel,
  getDataQualityLabel,
  getExpectedRange,
  getForecastStatusLabel,
  getSettlementLabel,
  isAbstainForecast,
  isCalibratedForecast,
  isDegradedForecast,
  probabilityBars,
  shortForecastId,
} from '@/components/research/forecastStatus';

export interface VerdictKeyLevels {
  r2?: number | null;
  r1?: number | null;
  pivot?: number | null;
  s1?: number | null;
  s2?: number | null;
}

export interface BiasDrift {
  pts: number;
  pct: number;
}

/**
 * Live drift of the executable price away from the bias snapshot price.
 * Pure + fail-false: null when either leg is missing/non-finite — caller
 * renders nothing rather than a fabricated 0.0.
 */
export function calcBiasDrift(liveSpot: number | null | undefined, biasPrice: number | null | undefined): BiasDrift | null {
  if (typeof liveSpot !== 'number' || typeof biasPrice !== 'number') return null;
  if (!Number.isFinite(liveSpot) || !Number.isFinite(biasPrice)) return null;
  if (liveSpot <= 0 || biasPrice <= 0) return null;
  const pts = liveSpot - biasPrice;
  if (!Number.isFinite(pts)) return null;
  const pct = (pts / biasPrice) * 100;
  if (!Number.isFinite(pct)) return null;
  return { pts, pct };
}

interface VerdictPanelProps {
  forecast: HourForecast | null;
  loading: boolean;
  error: string | null;
  instrument: string;
  timeframe: string;
  onRefresh?: () => void;
  fiiDii?: { fii_net_crores?: number; dii_net_crores?: number } | null;
  pcr?: number | null;
  maxPain?: number | null;
  liveSpot?: number | null;
  updatedAt?: Date | null;
}

/**
 * Normalize the backend `explain` bundle (unknown shape) into display strings.
 * Returns [] when the payload carries no rationale — never canned copy that
 * would masquerade as backend-sourced reasoning.
 */
function explainToReasons(explain: unknown): string[] {
  if (typeof explain === 'string') {
    return explain.trim() ? [explain.trim()] : [];
  }
  if (Array.isArray(explain)) {
    const out = explain
      .map((item: unknown): string => {
        if (typeof item === 'string') return item.trim();
        if (item != null && typeof item === 'object') {
          const rec = item as Record<string, unknown>;
          for (const k of ['message', 'summary', 'text', 'reason', 'detail']) {
            const v = rec[k];
            if (typeof v === 'string' && v.trim()) return v.trim();
          }
          return '';
        }
        return String(item);
      })
      .filter((s: string) => s.trim().length > 0);
    return out;
  }
  if (explain != null && typeof explain === 'object') {
    const rec = explain as Record<string, unknown>;
    const bullets = rec['bullets'];
    if (Array.isArray(bullets) && bullets.length > 0) {
      return explainToReasons(bullets);
    }
    const summary = rec['summary'];
    if (typeof summary === 'string' && summary.trim()) return [summary.trim()];
  }
  return [];
}

/**
 * Verdict terminal hero: eyebrow truth line, single 24px direction verdict,
 * four-figure stat row, telemetry context strip, quiet rationale list.
 * No pills, no shouting type, no fabricated levels.
 */
export const VerdictPanel = memo(function VerdictPanel({
  forecast,
  loading,
  error,
  instrument,
  timeframe,
  onRefresh,
  fiiDii,
  pcr,
  maxPain,
  liveSpot,
  updatedAt,
}: VerdictPanelProps) {
  const biasRaw = String(forecast?.direction ?? 'NEUTRAL').toUpperCase();
  const isBull = biasRaw.includes('BULL') || biasRaw.includes('UP') || biasRaw.includes('LONG');
  const isBear = biasRaw.includes('BEAR') || biasRaw.includes('DOWN') || biasRaw.includes('SHORT');
  const direction = isBull ? 'BULLISH' : isBear ? 'BEARISH' : 'NEUTRAL';

  // Do not default to arbitrary 65% if confidence is absent from backend
  const confRaw = typeof forecast?.confidence === 'number' && Number.isFinite(forecast.confidence) ? forecast.confidence : NaN;
  const confPct = Number.isFinite(confRaw) ? Math.round(confRaw > 1 ? confRaw : confRaw * 100) : null;

  const spot = forecast?.current_price ?? liveSpot ?? null;
  // Realtime drift: executable WS price vs the bias snapshot price.
  // Null when either leg is missing — never fabricate a 0.0 drift.
  const biasPrice = typeof forecast?.current_price === 'number' ? forecast.current_price : null;
  const drift = calcBiasDrift(liveSpot ?? null, biasPrice);
  const driftLabel = drift
    ? `${drift.pts >= 0 ? '+' : ''}${fmtNum(drift.pts, 1)} pts (${drift.pts >= 0 ? '+' : ''}${fmtNum(drift.pct, 2)}% since bias)`
    : null;
  // Fail-truthful: do not fabricate synthetic target or stop prices if backend didn't provide them
  const target = forecast?.target_price ?? null;
  const stopLoss = forecast?.invalidation_price ?? null;

  const mtfScore = forecast?.layer_scores?.mtf_alignment;
  // Single honest value: one trend-leg number, never fanned out to four labels.
  const mtfAligned =
    typeof mtfScore === 'number' && Number.isFinite(mtfScore)
      ? mtfScore > 10
        ? 'BULL'
        : mtfScore < -10
          ? 'BEAR'
          : 'FLAT'
      : null;

  // — v2 honesty block (same contract as the forecast honesty helpers; ABSTAIN/DEGRADED/
  // UNSETTLEABLE must be visually unmistakable) —
  const v2Status = getForecastStatusLabel(forecast);
  const degraded = isDegradedForecast(forecast);
  const abstain = isAbstainForecast(forecast);
  const dataQuality = getDataQualityLabel(forecast);
  const settlement = getSettlementLabel(forecast);
  const limitations = asStringList(forecast?.limitations);
  const probBars = probabilityBars(forecast);
  const bullPct = probBars?.find((b) => b.key === 'bullish')?.pct ?? 0;
  const neutPct = probBars?.find((b) => b.key === 'neutral')?.pct ?? 0;
  const bearPct = probBars?.find((b) => b.key === 'bearish')?.pct ?? 0;
  const calibrated = isCalibratedForecast(forecast);
  const calibLabel = calibrationLabel(forecast);
  const expectedRange = getExpectedRange(forecast);
  const settleReason =
    typeof forecast?.settle_reason === 'string' && forecast.settle_reason.trim()
      ? forecast.settle_reason.trim()
      : null;
  const showModelLine =
    forecast?.model_version != null ||
    forecast?.calibrator_version != null ||
    forecast?.regime != null ||
    forecast?.session != null;
  const showProvenance =
    showModelLine || limitations.length > 0 || forecast?.settleable === false || forecast?.prediction_id != null;

  const trendText = mtfAligned ?? '—';

  const reasons = explainToReasons(forecast?.explain);
  const fiiNet = fiiDii?.fii_net_crores ?? null;
  const showSkeleton = loading && !forecast;

  const stats: [string, string][] = [
    ['Spot', spot ? fmtNum(spot, 1) : '—'],
    ['Target', target ? fmtNum(target, 1) : '—'],
    ['Stop', stopLoss ? fmtNum(stopLoss, 1) : '—'],
    ['Confidence', confPct !== null ? `${confPct}%` : '—'],
  ];

  const statusTone =
    v2Status === 'ABSTAIN' ? 'chip--warn' : v2Status === 'DEGRADED' ? 'chip--warn' : v2Status === 'MVIG' ? 'chip--up' : 'chip--info';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <section
        className="card"
        aria-label={`${instrument} tactical bias`}
        // Amber border for DEGRADED so it can never be mistaken for a healthy call.
        style={degraded ? { borderColor: 'var(--ds-warn)' } : undefined}
      >
        <div className="card-bd" style={{ padding: '12px 14px' }}>
          {showSkeleton ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} aria-label="Loading verdict">
              <div className="skel" style={{ height: 12, width: 120 }} />
              <div className="skel" style={{ height: 30, width: '40%' }} />
              <div className="skel" style={{ height: 12, width: '70%' }} />
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div>
                <div className="micro-label num">
                  Tactical bias · {instrument} · {timeframe.toUpperCase()}
                  {updatedAt ? ` · updated ${updatedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}` : ''}
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }} aria-label="Forecast status">
                  <span className={`chip ${statusTone}`} title={forecast?.forecast_version ? `forecast ${forecast.forecast_version}` : 'forecast v1'}>
                    {v2Status}
                  </span>
                  {dataQuality ? (
                    <span className={`chip ${dataQuality === 'HEALTHY' ? 'chip--up' : dataQuality === 'DEGRADED' ? 'chip--warn' : 'chip--neut'}`} title="Data quality">
                      Data · {dataQuality}
                    </span>
                  ) : null}
                  {settlement ? (
                    <span
                      className={`chip ${settlement === 'YES' ? 'chip--up' : 'chip--warn'}`}
                      title={settleReason ?? 'Settlement eligibility'}
                    >
                      Settle · {settlement}
                    </span>
                  ) : null}
                  <span
                    className={`chip ${calibrated ? 'chip--up' : 'chip--neut'}`}
                    title={calibrated
                      ? `Calibrated${forecast?.calibrator_version ? ` · ${forecast.calibrator_version}` : ''}`
                      : `Uncalibrated${forecast?.calibrator_version ? ` · ${forecast.calibrator_version}` : ''}`}
                  >
                    {calibLabel}
                  </span>
                  {shortForecastId(forecast?.prediction_id) ? (
                    <span className="faint mono num" title={forecast?.prediction_id ?? undefined} style={{ fontSize: 11, alignSelf: 'center' }}>
                      #{shortForecastId(forecast?.prediction_id)}
                    </span>
                  ) : null}
                </div>
                <div
                  className="num"
                  style={{
                    fontSize: 24,
                    fontWeight: 600,
                    letterSpacing: '-0.01em',
                    marginTop: 4,
                    color: abstain
                      ? 'var(--ds-warn-strong)'
                      : isBull
                        ? 'var(--ds-bull-strong)'
                        : isBear
                          ? 'var(--ds-bear-strong)'
                          : 'var(--ds-ink)',
                  }}
                >
                  {abstain ? '◆ Abstain' : isBull ? '▲ Bullish' : isBear ? '▼ Bearish' : '◆ Neutral'}
                </div>
                <div style={{ fontSize: 12, color: 'var(--ds-text-secondary)', marginTop: 2 }}>
                  {abstain
                    ? 'Abstain — insufficient evidence, no position'
                    : isBull
                      ? 'Favour calls above support'
                      : isBear
                        ? 'Favour puts below resistance'
                        : 'Range — wait for breakout'}
                  {degraded ? ' · degraded inputs' : ''}
                </div>
              </div>
              <div className="verdict-stats">
                {stats.map(([l, v]) => (
                  <div key={l} className="verdict-stat">
                    <div className="verdict-stat-l">{l}</div>
                    <div className="verdict-stat-v num">{v}</div>
                    {l === 'Confidence' && confPct !== null ? (
                      <div
                        className="meter"
                        role="progressbar"
                        aria-valuenow={confPct}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        style={{ width: '100%', maxWidth: 120, marginTop: 5 }}
                      >
                        <i style={{ width: `${confPct}%` }} />
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
              {driftLabel && liveSpot != null ? (
                <div
                  aria-label="Live price drift since bias"
                  title={`Bias snapshot ${fmtNum(biasPrice, 1)} · live ${fmtNum(liveSpot, 1)} via WS ticks`}
                  className="num"
                  style={{ fontSize: 11.5, color: 'var(--ds-text-secondary)' }}
                >
                  live {fmtNum(liveSpot, 1)} · {driftLabel}
                </div>
              ) : null}
              {probBars ? (
                <div aria-label="Outcome probabilities">
                  <div className="num" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, fontWeight: 600, marginBottom: 3 }}>
                    <span className="v-bull">{bullPct}% Bull</span>
                    <span className="muted">{neutPct}% Neut</span>
                    <span className="v-bear">{bearPct}% Bear</span>
                  </div>
                  <StackedProbabilityBar bullPct={bullPct} neutPct={neutPct} bearPct={bearPct} height={6} />
                </div>
              ) : null}
            </div>
          )}
          {error ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              <p style={{ margin: 0, fontSize: 12, color: forecast ? 'var(--ds-text-secondary)' : 'var(--ds-bear-strong)' }}>
                {forecast ? `Showing last known bias — ${error}` : error}
              </p>
              {onRefresh ? (
                <button
                  type="button"
                  onClick={onRefresh}
                  className="btn"
                  style={{ fontSize: 11, padding: '2px 8px' }}
                >
                  Retry
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </section>

      <TelemetryStrip aria-label="Bias context">
        <TelemetryItem label="PCR" value={pcr != null && Number.isFinite(pcr) ? fmtNum(pcr, 2) : '—'} />
        <TelemetryItem
          label="Max pain"
          value={maxPain != null && Number.isFinite(maxPain) ? Math.round(maxPain).toLocaleString('en-IN') : '—'}
        />
        <TelemetryItem
          label="FII net"
          value={fiiNet != null && Number.isFinite(fiiNet) ? `${fiiNet > 0 ? '+' : ''}${Math.round(fiiNet)} Cr` : '—'}
          tone={fiiNet != null && fiiNet > 0 ? 'bull' : fiiNet != null && fiiNet < 0 ? 'bear' : undefined}
        />
        <TelemetryItem
          label="MTF align"
          value={<span className="num" style={{ fontSize: 12 }}>{trendText}</span>}
          sub="trend leg"
          tone={mtfAligned === 'BULL' ? 'bull' : mtfAligned === 'BEAR' ? 'bear' : undefined}
        />
        {direction === 'NEUTRAL' && expectedRange ? (
          <>
            <TelemetryItem label="Range low" value={fmtNum(expectedRange.lower, 1)} />
            <TelemetryItem label="Range mid" value={fmtNum(expectedRange.mid, 1)} sub="chop centre" />
            <TelemetryItem label="Range high" value={fmtNum(expectedRange.upper, 1)} />
          </>
        ) : null}
      </TelemetryStrip>

      {showProvenance && !showSkeleton ? (
        <details className="forecast-meta-drawer">
          <summary>
            Model audit ({forecast?.model_version ?? 'v1'}
            {forecast?.regime ? ` · ${forecast.regime}` : ''}
            {limitations.length ? ` · ${limitations.length} notes` : ''})
          </summary>
          <div className="forecast-meta-content">
            {showModelLine ? (
              <div className="faint mono num" style={{ fontSize: 11 }}>
                model {forecast?.model_version ?? '—'} · calibrator {forecast?.calibrator_version ?? 'none'}
                {forecast?.regime ? ` · regime ${forecast.regime}` : ''}
                {forecast?.session ? ` · session ${forecast.session}` : ''}
                {shortForecastId(forecast?.snapshot_id) ? ` · snap ${shortForecastId(forecast.snapshot_id)}` : ''}
                {typeof forecast?.latency_ms === 'number' ? ` · ${Math.round(forecast.latency_ms)}ms` : ''}
                {forecast?.persisted === true ? ' · persisted' : forecast?.persisted === false ? ' · not persisted' : ''}
              </div>
            ) : null}
            {forecast?.settleable === false ? (
              <div role="note" className="notice notice--warn" style={{ marginTop: 6, fontSize: 11.5 }} title={settleReason ?? undefined}>
                <span>{UNSETTLEABLE_NOTE}{settleReason ? ` — ${settleReason}` : ''}</span>
              </div>
            ) : null}
            {limitations.length > 0 ? (
              <div style={{ marginTop: 6 }}>
                <div className="micro-label" style={{ fontSize: 10 }}>Limitations</div>
                <ul className="muted" style={{ margin: '3px 0 0', paddingLeft: 16, fontSize: 11, display: 'grid', gap: 2 }}>
                  {limitations.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </details>
      ) : null}

      {!showSkeleton && forecast ? (
        <section style={{ padding: '0 4px' }} aria-label="Why this bias">
          <h3 className="micro-label" style={{ margin: '0 0 6px', fontSize: 11 }}>Why this bias</h3>
          {reasons.length > 0 ? (
            <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {reasons.slice(0, 3).map((r, i) => (
                <li key={i} style={{ fontSize: 12.5, color: 'var(--ds-text-secondary)' }}>
                  <span aria-hidden="true" style={{ color: 'var(--ds-ink-3)', marginRight: 6 }}>›</span>{r}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted" style={{ margin: 0, fontSize: 12 }}>
              No rationale provided by the model for this verdict.
            </p>
          )}
        </section>
      ) : null}
    </div>
  );
});
