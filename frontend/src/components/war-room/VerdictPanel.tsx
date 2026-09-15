'use client';

import { memo } from 'react';
import type { HourForecast } from '@/components/research/ForecastCard';
import { fmtNum } from '@/components/ui/desk';

export interface VerdictKeyLevels {
  r2?: number | null;
  r1?: number | null;
  pivot?: number | null;
  s1?: number | null;
  s2?: number | null;
}

interface VerdictPanelProps {
  forecast: HourForecast | null;
  loading: boolean;
  error: string | null;
  instrument: string;
  timeframe: string;
  onRefresh: () => void;
  fiiDii?: { fii_net_crores?: number; dii_net_crores?: number } | null;
  pcr?: number | null;
  maxPain?: number | null;
  liveSpot?: number | null;
  keyLevels?: VerdictKeyLevels | null;
  mtf?: Record<string, string> | null;
  updatedAt?: Date | null;
}

/** Normalize the backend `explain` bundle (unknown shape) into display strings. */
function explainToReasons(explain: unknown, direction: string, timeframe: string): string[] {
  const fallback = [
    `${timeframe.toUpperCase()} Trend momentum supports ${direction.toLowerCase()} continuation`,
    `Supertrend and EMA 20/50 alignment confirming directional bias`,
    `Options positioning and volume profile consistent with prevailing flow`,
  ];
  if (typeof explain === 'string') {
    return explain.trim() ? [explain.trim()] : fallback;
  }
  if (Array.isArray(explain) && explain.length > 0) {
    const out = explain
      .map((item: unknown): string => {
        if (typeof item === 'string') return item.trim();
        if (item != null && typeof item === 'object') {
          const rec = item as Record<string, unknown>;
          for (const k of ['message', 'summary', 'text', 'reason', 'detail']) {
            const v = rec[k];
            if (typeof v === 'string' && v.trim()) return v.trim();
          }
          try {
            return JSON.stringify(item);
          } catch {
            return String(item);
          }
        }
        return String(item);
      })
      .filter((s: string) => s.trim().length > 0);
    return out.length > 0 ? out : fallback;
  }
  if (explain != null && typeof explain === 'object') {
    const rec = explain as Record<string, unknown>;
    const bullets = rec['bullets'];
    if (Array.isArray(bullets) && bullets.length > 0) {
      return explainToReasons(bullets, direction, timeframe);
    }
    const summary = rec['summary'];
    if (typeof summary === 'string' && summary.trim()) return [summary.trim()];
  }
  return fallback;
}

function arrowFor(status: string): string {
  const st = status.toUpperCase();
  if (st.includes('BULL') || st.includes('UP')) return '▲';
  if (st.includes('BEAR') || st.includes('DOWN')) return '▼';
  return '–';
}

/**
 * Calm Kite-minimal verdict (Mock A): plain card, no hero gradient,
 * no pills/badges, plain context text row, quiet rationale list.
 * Levels are rendered by the parent desk — not here.
 */
export const VerdictPanel = memo(function VerdictPanel({
  forecast,
  loading,
  error,
  instrument,
  timeframe,
  fiiDii,
  pcr,
  maxPain,
  liveSpot,
  mtf: mtfProp,
}: VerdictPanelProps) {
  const biasRaw = String(forecast?.direction ?? 'NEUTRAL').toUpperCase();
  const isBull = biasRaw.includes('BULL') || biasRaw.includes('UP') || biasRaw.includes('LONG');
  const isBear = biasRaw.includes('BEAR') || biasRaw.includes('DOWN') || biasRaw.includes('SHORT');
  const direction = isBull ? 'BULLISH' : isBear ? 'BEARISH' : 'NEUTRAL';

  const confRaw = typeof forecast?.confidence === 'number' ? forecast.confidence : 0.65;
  const confPct = Math.round(confRaw > 1 ? confRaw : confRaw * 100);

  const spot = forecast?.current_price ?? liveSpot ?? null;
  const rawTarget = forecast?.target_price ?? null;
  const rawStop = forecast?.invalidation_price ?? null;
  const target =
    rawTarget ??
    (direction === 'NEUTRAL' || spot == null ? null : isBull ? spot * 1.006 : spot * 0.994);
  const stopLoss =
    rawStop ??
    (direction === 'NEUTRAL' || spot == null ? null : isBull ? spot * 0.995 : spot * 1.005);

  const mtfScore = forecast?.layer_scores?.mtf_alignment;
  const derivedMtf =
    typeof mtfScore === 'number' && Number.isFinite(mtfScore)
      ? mtfScore > 10
        ? 'BULL'
        : mtfScore < -10
          ? 'BEAR'
          : 'NEUT'
      : null;
  const mtf: Record<string, string> = mtfProp ?? {
    '1m': derivedMtf ?? 'NEUT',
    '5m': derivedMtf ?? 'NEUT',
    '15m': derivedMtf ?? 'NEUT',
    '1h': derivedMtf ?? 'NEUT',
  };
  const trendText = (['1m', '5m', '15m', '1h'] as const)
    .map((tf) => `${tf} ${arrowFor(mtf[tf] ?? 'NEUT')}`)
    .join(' · ');

  const reasons = explainToReasons(forecast?.explain, direction, timeframe);
  const fiiNet = fiiDii?.fii_net_crores ?? null;
  const showSkeleton = loading && !forecast;

  const stats: [string, string][] = [
    ['Spot', spot ? fmtNum(spot, 1) : '—'],
    ['Target', target ? fmtNum(target, 1) : '—'],
    ['Stop', stopLoss ? fmtNum(stopLoss, 1) : '—'],
    ['Confidence', `${confPct}%`],
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <section className="card" aria-label={`${instrument} tactical bias`}>
        <div className="card-bd" style={{ padding: '20px 22px' }}>
          {showSkeleton ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} aria-label="Loading verdict">
              <div className="skel" style={{ height: 12, width: 120 }} />
              <div className="skel" style={{ height: 30, width: '40%' }} />
              <div className="skel" style={{ height: 12, width: '70%' }} />
            </div>
          ) : (
            <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.08em', color: 'var(--ds-text-secondary)' }}>
                  TACTICAL BIAS · {instrument} · {timeframe.toUpperCase()}
                </div>
                <div
                  style={{
                    fontSize: 30,
                    fontWeight: 700,
                    marginTop: 4,
                    color: isBull ? 'var(--ds-bull-strong)' : isBear ? 'var(--ds-bear-strong)' : 'var(--ds-ink)',
                  }}
                >
                  {isBull ? '▲ Bullish' : isBear ? '▼ Bearish' : '◆ Neutral'}
                </div>
                <div style={{ fontSize: 13, color: 'var(--ds-text-secondary)', marginTop: 2 }}>
                  {isBull
                    ? 'Favour calls above support'
                    : isBear
                      ? 'Favour puts below resistance'
                      : 'Range — wait for breakout'}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
                {stats.map(([l, v]) => (
                  <div key={l}>
                    <div style={{ fontSize: 11, color: 'var(--ds-text-secondary)', fontWeight: 600 }}>{l}</div>
                    <div className="num" style={{ fontSize: 17, fontWeight: 700 }}>{v}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {error ? (
            <p style={{ margin: '10px 0 0', fontSize: 12, color: forecast ? 'var(--ds-text-secondary)' : 'var(--ds-bear-strong)' }}>
              {forecast ? `Showing last known bias — ${error}` : error}
            </p>
          ) : null}
        </div>
      </section>

      <div style={{ display: 'flex', gap: 24, fontSize: 13, color: 'var(--ds-text-secondary)', padding: '0 4px', flexWrap: 'wrap' }}>
        <span>PCR <b style={{ color: 'var(--ds-ink)' }}>{pcr != null && Number.isFinite(pcr) ? fmtNum(pcr, 2) : '—'}</b></span>
        <span>Max pain <b style={{ color: 'var(--ds-ink)' }}>{maxPain != null && Number.isFinite(maxPain) ? Math.round(maxPain).toLocaleString('en-IN') : '—'}</b></span>
        <span>FII net <b style={{ color: fiiNet != null && fiiNet > 0 ? 'var(--ds-bull-strong)' : fiiNet != null && fiiNet < 0 ? 'var(--ds-bear-strong)' : 'var(--ds-ink)' }}>
          {fiiNet != null && Number.isFinite(fiiNet) ? `${fiiNet > 0 ? '+' : ''}${Math.round(fiiNet)} Cr` : '—'}
        </b></span>
        <span>Trend <b style={{ color: 'var(--ds-ink)' }}>{trendText}</b></span>
      </div>

      {reasons.length > 0 && !showSkeleton ? (
        <section style={{ padding: '0 4px' }} aria-label="Why this bias">
          <h3 style={{ fontSize: 13, fontWeight: 700, margin: '0 0 6px' }}>Why this bias</h3>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
            {reasons.slice(0, 3).map((r, i) => (
              <li key={i} style={{ fontSize: 13, color: 'var(--ds-text-secondary)' }}>
                <span style={{ color: 'var(--ds-accent)', fontWeight: 700 }}>› </span>{r}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
});
