'use client';

import {
  DirectionBadge,
  EmptyNote,
  Meter,
  RetryButton,
  fmtINR,
  fmtPct01,
  fmtSigned,
  toneFor,
} from '@/components/ui/desk';
import WhyPanel from '@/components/forecast/WhyPanel';
import {
  ABSTAIN_VERDICT,
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
  maxProbability,
  probabilityBars,
  shortForecastId,
  type ForecastV2Probabilities,
  type ForecastV2Status,
} from './forecastStatus';

export type HourForecastDirection = 'BULLISH' | 'BEARISH' | 'NEUTRAL';

export type HourForecast = {
  instrument: string;
  timeframe: string;
  forecast_horizon?: string;
  current_price?: number | null;
  direction: HourForecastDirection;
  score: number;
  confidence: number;
  target_price?: number | null;
  invalidation_price?: number | null;
  layer_scores?: {
    mtf_alignment?: number;
    indicators?: number;
    ml?: number;
    options?: number;
    structure?: number;
  };
  ml_forecast?: unknown;
  indicator_outputs?: unknown;
  prediction_id?: string;
  explain?: unknown;
  component_values?: Record<string, unknown> | null;
  // — 1H forecast v2.3 (P0) honesty fields: ALL optional so v1
  // responses without new keys still render (status defaults to RESEARCH).
  forecast_version?: string | null;
  status?: ForecastV2Status | null;
  probabilities?: ForecastV2Probabilities | null;
  raw_confidence?: number | null;
  regime?: string | null;
  session?: string | null;
  settleable?: boolean | null;
  settle_reason?: string | null;
  data_quality?: string | null;
  model_version?: string | null;
  calibrator_version?: string | null;
  snapshot_id?: string | null;
  limitations?: string[] | null;
  // — 1H forecast v2.3 (P3-4) prob UI: ALL optional so v1 renders as before.
  calibrated?: boolean | null;
  calibration?: unknown;
  expected_range?: { lower?: number | null; mid?: number | null; upper?: number | null } | null;
  target_basis?: string | null;
  latency_ms?: number | null;
};

type ForecastCardProps = {
  forecast: HourForecast | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  updatedAt?: Date | null;
  timeframe?: string;
  timeframeLabel?: string;
};

const ML_HINT_BY_TIMEFRAME: Record<string, string> = {
  '1m': 'quant baseline (no 1m ML artifact)',
  '5m': '5-min model',
  '15m': '15-min model',
  '30m': '30-min model',
  '1h': '60-min model',
};

function mlHint(timeframe: string): string {
  return ML_HINT_BY_TIMEFRAME[timeframe] ?? `${timeframe} model`;
}

const LAYER_ROWS: Array<{ key: keyof NonNullable<HourForecast['layer_scores']>; label: string; hint: string }> = [
  { key: 'mtf_alignment', label: 'Trend alignment', hint: '1m → 1D agreement' },
  { key: 'indicators', label: 'Indicators', hint: 'RSI · MACD · Momentum · VWAP · OMPI' },
  { key: 'ml', label: 'ML ensemble', hint: '60-min model' },
  { key: 'options', label: 'Options flow', hint: 'PCR · walls · max pain' },
  { key: 'structure', label: 'Structure', hint: 'Supertrend · RSI · levels' },
];

function distPct(anchor: number | null | undefined, ref: number | null | undefined): string {
  if (anchor === null || anchor === undefined || ref === null || ref === undefined) return '';
  if (!Number.isFinite(anchor) || !Number.isFinite(ref) || ref === 0) return '';
  const pct = ((anchor - ref) / ref) * 100;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

export default function ForecastCard({ forecast, loading, error, onRetry, updatedAt, timeframe = '1h', timeframeLabel }: ForecastCardProps) {
  const tfLabel = timeframeLabel ?? timeframe.toUpperCase();
  const outlookLabel = `${tfLabel} Outlook`;
  if (loading && !forecast) {
    return (
      <section className="card" aria-label={outlookLabel}>
        <div className="card-hd">
          <h2 className="card-title">{outlookLabel}</h2>
          <span className="card-meta">scanning…</span>
        </div>
        <div className="card-bd" style={{ display: 'grid', gap: 10 }}>
          <div className="skel" style={{ height: 44, width: '42%' }}>.</div>
          <div className="skel" style={{ height: 16, width: '75%' }}>.</div>
          <div className="skel" style={{ height: 16, width: '60%' }}>.</div>
          <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginTop: 4 }}>
            {[0, 1, 2].map((i) => (
              <div key={i} className="skel" style={{ height: 84 }}>.</div>
            ))}
          </div>
        </div>
      </section>
    );
  }

  if (!forecast) {
    return (
      <section className="card" aria-label={outlookLabel}>
        <div className="card-hd">
          <h2 className="card-title">{outlookLabel}</h2>
          <span className="card-meta">unavailable</span>
        </div>
        <div className="card-bd">
          <EmptyNote>
            Forecast unavailable — {error ? String(error) : 'the feed or model did not respond.'}
          </EmptyNote>
          <div style={{ marginTop: 12 }}>
            <RetryButton onRetry={onRetry} />
          </div>
        </div>
      </section>
    );
  }

  const score = Number.isFinite(forecast.score) ? forecast.score : 0;
  const tone = toneFor(score);
  const price = forecast.current_price ?? null;

  // — v2.3 (P0) honesty state: all derived defensively so v1 payloads render unchanged —
  const v2Status = getForecastStatusLabel(forecast);
  const degraded = isDegradedForecast(forecast);
  const abstain = isAbstainForecast(forecast);
  const dataQuality = getDataQualityLabel(forecast);
  const settlement = getSettlementLabel(forecast);
  const limitations = asStringList(forecast.limitations);
  // — P3-4 prob UI: optional; v1 payloads (no probabilities) hide these —
  const probBars = probabilityBars(forecast);
  const maxP = maxProbability(forecast);
  const displayConfidence =
    typeof maxP === 'number' && Number.isFinite(maxP) ? maxP : Number(forecast.confidence) || 0;
  const calibLabel = calibrationLabel(forecast);
  const calibrated = isCalibratedForecast(forecast);
  const expectedRange = getExpectedRange(forecast);
  const confPct = Math.round(displayConfidence * 100);
  const settleReason =
    typeof forecast.settle_reason === 'string' && forecast.settle_reason.trim()
      ? forecast.settle_reason.trim()
      : null;
  const showModelLine =
    forecast.model_version != null ||
    forecast.calibrator_version != null ||
    forecast.regime != null ||
    forecast.session != null;
  const statusBadgeClass =
    v2Status === 'MVIG' ? 'badge b-bull' : v2Status === 'ABSTAIN' ? 'badge b-neut' : v2Status === 'DEGRADED' ? 'badge' : 'badge b-info';
  const statusBadgeStyle =
    v2Status === 'DEGRADED'
      ? { color: '#92580a', background: '#fef3c7', borderColor: '#f59e0b' }
      : undefined;
  const dataChipClass =
    dataQuality === 'HEALTHY'
      ? 'badge b-bull'
      : dataQuality === 'HEURISTIC'
        ? 'badge b-info'
        : dataQuality === 'DEGRADED'
          ? 'badge'
          : 'badge b-neut';
  const dataChipStyle =
    dataQuality === 'DEGRADED'
      ? { color: '#92580a', background: '#fef3c7', borderColor: '#f59e0b' }
      : undefined;

  return (
    <section
      className="forecast-hero"
      data-tone={tone}
      data-status={v2Status}
      aria-label={outlookLabel}
      // Amber border for DEGRADED so it can never be mistaken for a healthy bull/bear card.
      style={degraded ? { borderColor: '#f59e0b' } : undefined}
    >
      <div className="forecast-hero-glow" aria-hidden />
      <div style={{ position: 'relative', padding: '16px 20px' }}>
        {/* top meta row */}
        <div className="toolbar" style={{ marginBottom: 14 }}>
          <DirectionBadge direction={forecast.direction} big />
          <span className="card-meta num">
            {forecast.instrument} · {forecast.timeframe || timeframe}{price != null ? ` · ${fmtINR(price)}` : ''}
            {updatedAt ? ` · ${updatedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}` : ''}
          </span>
          <span className="spacer" />
          {shortForecastId(forecast.prediction_id) ? (
            <span className="faint mono" title={forecast.prediction_id ?? undefined}>
              #{shortForecastId(forecast.prediction_id)}
            </span>
          ) : null}
          {shortForecastId(forecast.snapshot_id) ? (
            <span className="faint mono" title={forecast.snapshot_id ?? undefined}>
              snap {shortForecastId(forecast.snapshot_id)}
            </span>
          ) : null}
        </div>
        {error ? (
          <div
            role="alert"
            className="muted"
            style={{
              marginBottom: 12,
              padding: '6px 10px',
              borderRadius: 4,
              border: '1px solid var(--ds-border)',
              background: 'var(--ds-inset)',
              fontSize: 12,
              display: 'flex',
              gap: 8,
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span>Showing last good forecast — refresh failed: {String(error)}</span>
            <RetryButton onRetry={onRetry}>Retry</RetryButton>
          </div>
        ) : null}

        {/* v2 honesty badges — RESEARCH default until MVIG; hidden extras on v1 payloads */}
        <div className="toolbar" style={{ marginBottom: 12, gap: 8 }} aria-label="Forecast status">
          <span className={statusBadgeClass} style={statusBadgeStyle} title={forecast.forecast_version ? `forecast ${forecast.forecast_version}` : 'forecast v1'}>
            {v2Status}
          </span>
          {dataQuality ? (
            <span className={dataChipClass} style={dataChipStyle} title="Data quality">
              DATA · {dataQuality}
            </span>
          ) : null}
          {settlement ? (
            <span
              className={settlement === 'YES' ? 'badge b-bull' : 'badge'}
              style={settlement === 'YES' ? undefined : { color: '#92580a', background: '#fef3c7', borderColor: '#f59e0b' }}
              title={settleReason ?? 'Settlement eligibility'}
            >
              SETTLEMENT · {settlement}
            </span>
          ) : null}
        </div>
        {showModelLine ? (
          <div className="faint mono" style={{ fontSize: 11, marginBottom: 12 }}>
            model {forecast.model_version ?? '—'} · calibrator {forecast.calibrator_version ?? 'none-v0'}
            {forecast.regime ? ` · regime ${forecast.regime}` : ''}
            {forecast.session ? ` · session ${forecast.session}` : ''}
          </div>
        ) : null}
        {forecast.settleable === false ? (
          <div
            role="note"
            className="muted"
            style={{
              marginBottom: 12,
              padding: '6px 10px',
              borderRadius: 4,
              border: '1px solid #f59e0b',
              background: '#fef3c7',
              color: '#92580a',
              fontSize: 12,
            }}
            title={settleReason ?? undefined}
          >
            {UNSETTLEABLE_NOTE}{settleReason ? ` — ${settleReason}` : ''}
          </div>
        ) : null}
        {limitations.length > 0 ? (
          <div style={{ marginBottom: 12 }}>
            <div className="faint" style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em' }}>
              LIMITATIONS
            </div>
            <ul className="muted" style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 12, display: 'grid', gap: 2 }}>
              {limitations.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* verdict row */}
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', gap: 24 }}>
          <div>
            <div
              className={`num ${tone === 'bull' ? 'v-bull' : tone === 'bear' ? 'v-bear' : ''}`}
              style={{ fontSize: 40, fontWeight: 700, lineHeight: 1, letterSpacing: '-0.02em' }}
            >
              {fmtSigned(score, 0)}
            </div>
            <div className="faint" style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', marginTop: 4 }}>
              SCORE / ±100
            </div>
          </div>
          <div style={{ minWidth: 200, flex: 1, paddingBottom: 4 }}>
            <div className="toolbar" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
              <span className="faint" style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em' }}>
                CONFIDENCE
              </span>
              <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                <span
                  className="num"
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    padding: '2px 8px',
                    borderRadius: 3,
                    background: 'var(--ds-inset)',
                    border: '1px solid var(--ds-border)',
                  }}
                  title={probBars ? 'Confidence = max(BULL, NEUT, BEAR)' : 'Confidence'}
                >
                  {fmtPct01(displayConfidence)}
                </span>
                <span
                  className={calibrated ? 'badge b-bull' : 'badge b-neut'}
                  title={
                    calibrated
                      ? `Calibrated${forecast.calibrator_version ? ` · ${forecast.calibrator_version}` : ''}`
                      : `Uncalibrated${forecast.calibrator_version ? ` · ${forecast.calibrator_version}` : ''}`
                  }
                >
                  {calibLabel}
                </span>
              </span>
            </div>
            <Meter value={displayConfidence} />
            <div className="faint num" style={{ fontSize: 11.5, marginTop: 6 }}>
              {abstain
                ? ABSTAIN_VERDICT
                : confPct >= 70
                  ? 'High conviction setup'
                  : confPct >= 45
                    ? 'Moderate conviction — size accordingly'
                    : 'Low conviction — stay light'}
            </div>
          </div>
        </div>

        {/* v2 probability bars — hidden for v1 payloads without probabilities */}
        {probBars ? (
          <div style={{ marginTop: 14, display: 'grid', gap: 8 }} aria-label="Outcome probabilities">
            <div className="faint" style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em' }}>
              PROBABILITIES
            </div>
            {probBars.map((b) => (
              <div
                key={b.key}
                style={{ display: 'grid', gridTemplateColumns: '52px 48px 1fr', gap: 10, alignItems: 'center' }}
              >
                <div style={{ fontSize: 11.5, fontWeight: 700 }}>{b.label}</div>
                <div className="num" style={{ fontSize: 12, fontWeight: 600, textAlign: 'right' }}>
                  {b.pct}%
                </div>
                <div className="dbar" aria-hidden>
                  <i
                    className={b.key === 'bullish' ? 'pos' : b.key === 'bearish' ? 'neg' : undefined}
                    style={{
                      left: 0,
                      width: `${Math.min(100, Math.max(0, b.pct))}%`,
                      ...(b.key === 'neutral'
                        ? { background: 'var(--ds-border)' }
                        : {}),
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {/* targets */}
        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', marginTop: 16 }}>
          <div className="stat">
            <div className="stat-l">Target</div>
            <div className={`stat-v ${forecast.direction === 'BEARISH' ? 'v-bear' : 'v-bull'}`}>{fmtINR(forecast.target_price)}</div>
            <div className="stat-s num">{price != null ? `${distPct(forecast.target_price, price)} from spot` : '—'}</div>
          </div>
          <div className="stat">
            <div className="stat-l">Invalidation</div>
            <div className="stat-v">{fmtINR(forecast.invalidation_price)}</div>
            <div className="stat-s num">{price != null ? `${distPct(forecast.invalidation_price, price)} from spot` : '—'}</div>
          </div>
          <div className="stat">
            <div className="stat-l">Spot</div>
            <div className="stat-v">{fmtINR(price)}</div>
            <div className="stat-s num">{forecast.forecast_horizon ? `horizon ${forecast.forecast_horizon}` : 'horizon 1h'}</div>
          </div>
        </div>
        {/* NEUTRAL expected range — only when the backend supplies it; v1 renders targets as before */}
        {forecast.direction === 'NEUTRAL' && expectedRange ? (
          <div
            className="stat-grid"
            style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', marginTop: 10 }}
            aria-label="Expected range"
          >
            <div className="stat">
              <div className="stat-l">Range low</div>
              <div className="stat-v">{fmtINR(expectedRange.lower)}</div>
              <div className="stat-s num">{price != null ? `${distPct(expectedRange.lower, price)} from spot` : '—'}</div>
            </div>
            <div className="stat">
              <div className="stat-l">Range mid</div>
              <div className="stat-v">{fmtINR(expectedRange.mid)}</div>
              <div className="stat-s num">expected chop center</div>
            </div>
            <div className="stat">
              <div className="stat-l">Range high</div>
              <div className="stat-v">{fmtINR(expectedRange.upper)}</div>
              <div className="stat-s num">{price != null ? `${distPct(expectedRange.upper, price)} from spot` : '—'}</div>
            </div>
          </div>
        ) : null}

        <hr className="divider" />

        {/* layers */}
        <div style={{ display: 'grid', gap: 10 }}>
          {LAYER_ROWS.map((row) => {
            const raw = forecast.layer_scores?.[row.key];
            const hint = row.key === 'ml' ? mlHint(forecast.timeframe || timeframe) : row.hint;
            const v = typeof raw === 'number' && Number.isFinite(raw) ? raw : null;
            const vtone = v === null ? null : toneFor(v);
            return (
              <div key={row.key} style={{ display: 'grid', gridTemplateColumns: '170px 56px 1fr', gap: 10, alignItems: 'center' }}>
                <div>
                  <div style={{ fontSize: 12.5, fontWeight: 600 }}>{row.label}</div>
                  <div className="faint" style={{ fontSize: 11 }}>{hint}</div>
                </div>
                <div
                  className={`num ${vtone === 'bull' ? 'v-bull' : vtone === 'bear' ? 'v-bear' : ''}`}
                  style={{
                    textAlign: 'center',
                    fontWeight: 700,
                    fontSize: 12,
                    padding: '2px 0',
                    borderRadius: 3,
                    background: v === null ? 'transparent' : vtone === 'bull' ? 'var(--ds-bull-wash)' : vtone === 'bear' ? 'var(--ds-bear-wash)' : 'var(--ds-neut-wash)',
                  }}
                >
                  {v === null ? '—' : fmtSigned(v, 0)}
                </div>
                <div className="dbar">
                  {v !== null && (
                    <i
                      className={v >= 0 ? 'pos' : 'neg'}
                      style={v >= 0 ? { left: '50%', width: `${Math.min(50, Math.abs(v) / 2)}%` } : { right: '50%', width: `${Math.min(50, Math.abs(v) / 2)}%` }}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <hr className="divider" />

        {/* explainability */}
        <details
          style={{
            marginTop: 16,
            border: '1px solid var(--ds-border)',
            borderRadius: 12,
            background: 'var(--ds-inset)',
            padding: '10px 14px',
          }}
        >
          <summary style={{ cursor: 'pointer', fontSize: 13.5, fontWeight: 750 }}>
            Why this forecast? How &amp; why
          </summary>
          <WhyPanel
            explain={
              (forecast.explain as unknown) ??
              (forecast.component_values?.explain as unknown) ??
              null
            }
            fallbackLayerScores={forecast.layer_scores}
            direction={forecast.direction}
            confidence={displayConfidence}
            invalidationPrice={forecast.invalidation_price ?? null}
            targetPrice={forecast.target_price ?? null}
          />
        </details>
      </div>
    </section>
  );
}
