'use client';

import {
  DirectionBadge,
  EmptyNote,
  Meter,
  RetryButton,
  StackedProbabilityBar,
  TelemetryItem,
  TelemetryStrip,
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
  // Durable-storage truth from the backend (true only when the immutable
  // snapshot+prediction were actually written to the database). Absent on
  // pre-P0 responses, so treat undefined as unknown rather than false-y.
  persisted?: boolean | null;
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
  const outlookLabel = `${tfLabel} Tactical Bias`;
  if (loading && !forecast) {
    return (
      <section className="card" aria-label={outlookLabel}>
        <div className="card-hd">
          <h2 className="card-title">{outlookLabel}</h2>
          <span className="card-meta">evaluating…</span>
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
            Tactical bias unavailable — {error ? String(error) : 'the feed or model did not respond.'}
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
  const bullBar = probBars?.find((b) => b.key === 'bullish');
  const neutBar = probBars?.find((b) => b.key === 'neutral');
  const bearBar = probBars?.find((b) => b.key === 'bearish');
  const bullPct = bullBar?.pct ?? 0;
  const neutPct = neutBar?.pct ?? 0;
  const bearPct = bearBar?.pct ?? 0;
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
      <div style={{ position: 'relative', padding: '12px 14px' }}>
        {/* top unified meta row */}
        <div className="toolbar" style={{ marginBottom: 10, gap: 8 }}>
          <DirectionBadge direction={forecast.direction} />
          <span className="card-meta num">
            {forecast.instrument} · {forecast.timeframe || timeframe}{price != null ? ` · ${fmtINR(price)}` : ''}
            {updatedAt ? ` · ${updatedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}` : ''}
          </span>
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
              SETTLE · {settlement}
            </span>
          ) : null}
          <span className="spacer" />
          {shortForecastId(forecast.prediction_id) ? (
            <span className="faint mono" title={forecast.prediction_id ?? undefined}>
              #{shortForecastId(forecast.prediction_id)}
            </span>
          ) : null}
        </div>

        {error ? (
          <div
            role="alert"
            className="muted"
            style={{
              marginBottom: 10,
              padding: '5px 8px',
              borderRadius: 4,
              border: '1px solid var(--ds-border)',
              background: 'var(--ds-inset)',
              fontSize: 11.5,
              display: 'flex',
              gap: 8,
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span>Showing last good bias — refresh failed: {String(error)}</span>
            <RetryButton onRetry={onRetry}>Retry</RetryButton>
          </div>
        ) : null}

        {/* verdict row: dense horizontal presentation */}
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <div
              className={`num ${tone === 'bull' ? 'v-bull' : tone === 'bear' ? 'v-bear' : ''}`}
              style={{ fontSize: 28, fontWeight: 700, lineHeight: 1, letterSpacing: '-0.02em' }}
            >
              {fmtSigned(score, 0)}
            </div>
            <div className="faint" style={{ fontSize: 9.5, fontWeight: 600, letterSpacing: '0.06em' }}>
              SCORE / ±100
            </div>
          </div>
          <div style={{ minWidth: 180, flex: 1 }}>
            <div className="toolbar" style={{ justifyContent: 'space-between', marginBottom: 4 }}>
              <span className="faint" style={{ fontSize: 9.5, fontWeight: 600, letterSpacing: '0.06em' }}>
                CONFIDENCE {fmtPct01(displayConfidence)}
              </span>
              <span
                className={calibrated ? 'badge b-bull' : 'badge b-neut'}
                style={{ fontSize: 10, padding: '1px 5px' }}
                title={
                  calibrated
                    ? `Calibrated${forecast.calibrator_version ? ` · ${forecast.calibrator_version}` : ''}`
                    : `Uncalibrated${forecast.calibrator_version ? ` · ${forecast.calibrator_version}` : ''}`
                }
              >
                {calibLabel}
              </span>
            </div>
            <Meter value={displayConfidence} />
            <div className="faint num" style={{ fontSize: 11, marginTop: 3 }}>
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

        {/* outcome probabilities: single stacked horizontal bar */}
        {probBars ? (
          <div style={{ marginTop: 10 }} aria-label="Outcome probabilities">
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, fontWeight: 600, marginBottom: 3 }}>
              <span className="v-bull">{bullPct}% Bull</span>
              <span className="muted">{neutPct}% Neut</span>
              <span className="v-bear">{bearPct}% Bear</span>
            </div>
            <StackedProbabilityBar bullPct={bullPct} neutPct={neutPct} bearPct={bearPct} height={6} />
          </div>
        ) : null}

        {/* targets and levels: 1-row telemetry strip */}
        <div style={{ marginTop: 10 }}>
          <TelemetryStrip>
            <TelemetryItem
              label="Target"
              value={fmtINR(forecast.target_price)}
              sub={price != null ? `${distPct(forecast.target_price, price)}` : '—'}
              tone={forecast.direction === 'BEARISH' ? 'bear' : 'bull'}
            />
            <TelemetryItem
              label="Invalidation"
              value={fmtINR(forecast.invalidation_price)}
              sub={price != null ? `${distPct(forecast.invalidation_price, price)}` : '—'}
            />
            <TelemetryItem
              label="Spot"
              value={fmtINR(price)}
              sub={forecast.forecast_horizon ? `horizon ${forecast.forecast_horizon}` : 'horizon 1h'}
            />
            {forecast.direction === 'NEUTRAL' && expectedRange ? (
              <>
                <TelemetryItem
                  label="Range Low"
                  value={fmtINR(expectedRange.lower)}
                  sub={price != null ? `${distPct(expectedRange.lower, price)}` : undefined}
                />
                <TelemetryItem
                  label="Range Mid"
                  value={fmtINR(expectedRange.mid)}
                  sub="chop center"
                />
                <TelemetryItem
                  label="Range High"
                  value={fmtINR(expectedRange.upper)}
                  sub={price != null ? `${distPct(expectedRange.upper, price)}` : undefined}
                />
              </>
            ) : null}
          </TelemetryStrip>
        </div>

        {/* Collapsible model audit & limitations drawer */}
        {showModelLine || limitations.length > 0 || forecast.settleable === false ? (
          <details className="forecast-meta-drawer">
            <summary>
              Model Specifications &amp; Audit ({forecast.model_version ?? 'v1'}{forecast.regime ? ` · ${forecast.regime}` : ''}{limitations.length ? ` · ${limitations.length} notes` : ''})
            </summary>
            <div className="forecast-meta-content">
              {showModelLine ? (
                <div className="faint mono" style={{ fontSize: 11 }}>
                  model {forecast.model_version ?? '—'} · calibrator {forecast.calibrator_version ?? 'none-v0'}
                  {forecast.regime ? ` · regime ${forecast.regime}` : ''}
                  {forecast.session ? ` · session ${forecast.session}` : ''}
                  {shortForecastId(forecast.snapshot_id) ? ` · snap ${shortForecastId(forecast.snapshot_id)}` : ''}
                </div>
              ) : null}
              {forecast.settleable === false ? (
                <div
                  role="note"
                  className="muted"
                  style={{
                    marginTop: 6,
                    padding: '4px 8px',
                    borderRadius: 3,
                    border: '1px solid #f59e0b',
                    background: '#fef3c7',
                    color: '#92580a',
                    fontSize: 11.5,
                  }}
                  title={settleReason ?? undefined}
                >
                  {UNSETTLEABLE_NOTE}{settleReason ? ` — ${settleReason}` : ''}
                </div>
              ) : null}
              {limitations.length > 0 ? (
                <div style={{ marginTop: 6 }}>
                  <div className="faint" style={{ fontSize: 9.5, fontWeight: 600, letterSpacing: '0.06em' }}>
                    LIMITATIONS
                  </div>
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

        <hr className="divider" style={{ margin: '8px 0' }} />

        {/* layers */}
        <div style={{ display: 'grid', gap: 6 }}>
          {LAYER_ROWS.map((row) => {
            const raw = forecast.layer_scores?.[row.key];
            const hint = row.key === 'ml' ? mlHint(forecast.timeframe || timeframe) : row.hint;
            const v = typeof raw === 'number' && Number.isFinite(raw) ? raw : null;
            const vtone = v === null ? null : toneFor(v);
            return (
              <div key={row.key} style={{ display: 'grid', gridTemplateColumns: '160px 52px 1fr', gap: 8, alignItems: 'center' }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{row.label}</div>
                  <div className="faint" style={{ fontSize: 10.5 }}>{hint}</div>
                </div>
                <div
                  className={`num ${vtone === 'bull' ? 'v-bull' : vtone === 'bear' ? 'v-bear' : ''}`}
                  style={{
                    textAlign: 'center',
                    fontWeight: 700,
                    fontSize: 11.5,
                    padding: '1px 0',
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

        <hr className="divider" style={{ margin: '8px 0' }} />

        {/* explainability */}
        <details
          style={{
            marginTop: 8,
            border: '1px solid var(--ds-border)',
            borderRadius: 6,
            background: 'var(--ds-inset)',
            padding: '7px 12px',
          }}
        >
          <summary style={{ cursor: 'pointer', fontSize: 13.5, fontWeight: 750 }}>
            Why this tactical bias? How &amp; why
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
