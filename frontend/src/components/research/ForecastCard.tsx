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
  const confPct = Math.round((Number(forecast.confidence) || 0) * 100);

  return (
    <section className="forecast-hero" data-tone={tone} aria-label={outlookLabel}>
      <div className="forecast-hero-glow" aria-hidden />
      <div style={{ position: 'relative', padding: '24px 26px 22px' }}>
        {/* top meta row */}
        <div className="toolbar" style={{ marginBottom: 18 }}>
          <DirectionBadge direction={forecast.direction} big />
          <span className="card-meta num">
            {forecast.instrument} · {forecast.timeframe || timeframe}{price != null ? ` · ${fmtINR(price)}` : ''}
            {updatedAt ? ` · ${updatedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}` : ''}
          </span>
          <span className="spacer" />
          {forecast.prediction_id ? (
            <span className="faint mono" title={forecast.prediction_id}>
              #{forecast.prediction_id.replace(/^forecast_[a-z0-9]+_/, '').slice(0, 12)}
            </span>
          ) : null}
        </div>
        {error ? (
          <div
            role="alert"
            className="muted"
            style={{
              marginBottom: 14,
              padding: '8px 12px',
              borderRadius: 10,
              border: '1px solid var(--ds-border)',
              background: 'var(--ds-inset)',
              fontSize: 12.5,
              display: 'flex',
              gap: 10,
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span>Showing last good forecast — refresh failed: {String(error)}</span>
            <RetryButton onRetry={onRetry}>Retry</RetryButton>
          </div>
        ) : null}

        {/* verdict row */}
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', gap: 28 }}>
          <div>
            <div
              className={`num ${tone === 'bull' ? 'v-bull' : tone === 'bear' ? 'v-bear' : ''}`}
              style={{ fontSize: 52, fontWeight: 850, lineHeight: 1, letterSpacing: '-0.03em' }}
            >
              {fmtSigned(score, 0)}
            </div>
            <div className="faint" style={{ fontSize: 11, fontWeight: 750, letterSpacing: '0.08em', marginTop: 6 }}>
              SCORE / ±100
            </div>
          </div>
          <div style={{ minWidth: 220, flex: 1, paddingBottom: 6 }}>
            <div className="toolbar" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
              <span className="faint" style={{ fontSize: 11, fontWeight: 750, letterSpacing: '0.08em' }}>
                CONFIDENCE
              </span>
              <span
                className="num"
                style={{
                  fontSize: 14,
                  fontWeight: 800,
                  padding: '3px 12px',
                  borderRadius: 999,
                  background: 'var(--ds-inset)',
                  border: '1px solid var(--ds-border)',
                }}
              >
                {fmtPct01(forecast.confidence)}
              </span>
            </div>
            <Meter value={forecast.confidence} />
            <div className="faint num" style={{ fontSize: 12, marginTop: 8 }}>
              {confPct >= 70 ? 'High conviction setup' : confPct >= 45 ? 'Moderate conviction — size accordingly' : 'Low conviction — stay light'}
            </div>
          </div>
        </div>

        {/* targets */}
        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', marginTop: 20 }}>
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

        <hr className="divider" />

        {/* layers */}
        <div style={{ display: 'grid', gap: 12 }}>
          {LAYER_ROWS.map((row) => {
            const raw = forecast.layer_scores?.[row.key];
            const hint = row.key === 'ml' ? mlHint(forecast.timeframe || timeframe) : row.hint;
            const v = typeof raw === 'number' && Number.isFinite(raw) ? raw : null;
            const vtone = v === null ? null : toneFor(v);
            return (
              <div key={row.key} style={{ display: 'grid', gridTemplateColumns: '170px 64px 1fr', gap: 12, alignItems: 'center' }}>
                <div>
                  <div style={{ fontSize: 13.5, fontWeight: 650 }}>{row.label}</div>
                  <div className="faint" style={{ fontSize: 12 }}>{hint}</div>
                </div>
                <div
                  className={`num ${vtone === 'bull' ? 'v-bull' : vtone === 'bear' ? 'v-bear' : ''}`}
                  style={{
                    textAlign: 'center',
                    fontWeight: 800,
                    fontSize: 13,
                    padding: '4px 0',
                    borderRadius: 8,
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
            confidence={forecast.confidence}
            invalidationPrice={forecast.invalidation_price ?? null}
            targetPrice={forecast.target_price ?? null}
          />
        </details>
      </div>
    </section>
  );
}
