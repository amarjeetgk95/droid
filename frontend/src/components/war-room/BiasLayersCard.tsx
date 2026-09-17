'use client';

import type { HourForecast } from '@/lib/types';
import {
  DivergingBar,
  EmptyNote,
  TelemetryItem,
  TelemetryStrip,
  fmtNum,
  fmtPct01,
  fmtSigned,
  normalizeDirection,
  toneFor,
} from '@/components/ui/desk';

export interface BiasLayersCardProps {
  forecast: HourForecast | null;
  loading: boolean;
}

type LayerKey = keyof NonNullable<HourForecast['layer_scores']>;

const LAYER_ROWS: Array<{ key: LayerKey; label: string }> = [
  { key: 'mtf_alignment', label: 'Trend alignment' },
  { key: 'indicators', label: 'Indicators' },
  { key: 'ml', label: 'ML ensemble' },
  { key: 'options', label: 'Options flow' },
  { key: 'structure', label: 'Structure' },
];

function asFiniteNumber(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function asNonEmptyString(v: unknown): string | null {
  if (typeof v !== 'string') return null;
  const s = v.trim();
  return s ? s : null;
}

/** Backend `layer_weights` is not on the shared HourForecast type — read it defensively. */
function readLayerWeights(forecast: HourForecast): Partial<Record<LayerKey, number>> {
  const rec = forecast as unknown as Record<string, unknown>;
  const raw = rec['layer_weights'];
  if (raw === null || raw === undefined || typeof raw !== 'object' || Array.isArray(raw)) return {};
  const src = raw as Record<string, unknown>;
  const out: Partial<Record<LayerKey, number>> = {};
  for (const row of LAYER_ROWS) {
    const v = asFiniteNumber(src[row.key]);
    if (v !== null) out[row.key] = v;
  }
  return out;
}

type MlFeature = { name: string; contribution: number | null };

type MlDetail = {
  bias: string | null;
  confidence: number | null;
  features: MlFeature[];
  modelVersion: string | null;
};

/** Backend `ml_forecast` is typed unknown — surface only known fields, never fabricate. */
function readMlDetail(forecast: HourForecast): MlDetail | null {
  const raw = forecast.ml_forecast;
  if (raw === null || raw === undefined || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const rec = raw as Record<string, unknown>;
  const bias = asNonEmptyString(rec['predicted_bias']);
  const confidence = asFiniteNumber(rec['confidence_score']);
  const modelVersion = asNonEmptyString(rec['model_version']);
  const features: MlFeature[] = [];
  const top = rec['top_features'];
  if (Array.isArray(top)) {
    for (const item of top) {
      if (features.length >= 3) break;
      if (item === null || item === undefined || typeof item !== 'object' || Array.isArray(item)) continue;
      const fr = item as Record<string, unknown>;
      const name = asNonEmptyString(fr['feature_name'] ?? fr['name']);
      if (!name) continue;
      features.push({ name, contribution: asFiniteNumber(fr['contribution']) });
    }
  }
  if (bias === null && confidence === null && modelVersion === null && features.length === 0) return null;
  return { bias, confidence, features, modelVersion };
}

/**
 * Phase W2 why-panel: the five bias legs behind the verdict plus the ML
 * detail bundle. Fail-truthful — absent legs render as an em-dash.
 */
export function BiasLayersCard({ forecast, loading }: BiasLayersCardProps) {
  if (loading && !forecast) {
    return (
      <section className="card" aria-label="Bias layers">
        <div className="card-hd">
          <h2 className="card-title">Bias layers</h2>
          <span className="card-meta num">loading</span>
        </div>
        <div className="card-bd" aria-label="Loading bias layers">
          <div className="bias-grid">
            {LAYER_ROWS.map((row) => (
              <div key={row.key} style={{ display: 'grid', gap: 4 }}>
                <div className="skel" style={{ height: 11, width: 72 }}>.</div>
                <div className="skel" style={{ height: 14, width: 40 }}>.</div>
                <div className="skel" style={{ height: 8 }}>.</div>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  }

  if (!forecast) {
    return (
      <section className="card" aria-label="Bias layers">
        <div className="card-hd">
          <h2 className="card-title">Bias layers</h2>
          <span className="card-meta">no bias</span>
        </div>
        <div className="card-bd">
          <EmptyNote>Bias layers unavailable — no forecast in scope.</EmptyNote>
        </div>
      </section>
    );
  }

  const weights = readLayerWeights(forecast);
  const ml = readMlDetail(forecast);
  const mlBiasDir = ml?.bias ? normalizeDirection(ml.bias) : null;

  return (
    <section className="card" aria-label="Bias layers">
      <div className="card-hd">
        <h2 className="card-title">Bias layers</h2>
        <span className="card-meta num">{forecast.instrument} · {forecast.timeframe}</span>
      </div>
      <div className="card-bd" style={{ display: 'grid', gap: 8 }}>
        <div className="bias-grid">
          {LAYER_ROWS.map((row) => {
            const v = asFiniteNumber(forecast.layer_scores?.[row.key]);
            const tone = toneFor(v);
            const w = weights[row.key] ?? null;
            return (
              <div key={row.key} style={{ minWidth: 0 }}>
                <div
                  className="muted"
                  title={w !== null ? `weight ${fmtNum(w, 2)}` : row.label}
                  style={{ fontSize: 11, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                >
                  {row.label}
                  {w !== null ? <span className="faint num"> · {fmtNum(w, 2)}</span> : null}
                </div>
                <div
                  className={`num ${tone === 'bull' ? 'v-bull' : tone === 'bear' ? 'v-bear' : 'muted'}`}
                  style={{ fontSize: 15, fontWeight: 600 }}
                >
                  {v === null ? '—' : fmtSigned(v, 0)}
                </div>
                {v !== null ? (
                  <div style={{ marginTop: 3 }}>
                    <DivergingBar value={v} />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>

        {ml ? (
          <details className="forecast-meta-drawer">
            <summary>ML detail{ml.modelVersion ? ` · ${ml.modelVersion}` : ''}</summary>
            <div className="forecast-meta-content" style={{ display: 'grid', gap: 6 }}>
              <TelemetryStrip aria-label="ML detail">
                {ml.bias && mlBiasDir ? (
                  <TelemetryItem
                    label="ML bias"
                    value={
                      <span
                        className={`chip ${mlBiasDir === 'BULLISH' ? 'chip--up' : mlBiasDir === 'BEARISH' ? 'chip--down' : 'chip--neut'}`}
                      >
                        {mlBiasDir}
                      </span>
                    }
                  />
                ) : null}
                {ml.confidence !== null ? (
                  <TelemetryItem
                    label="ML confidence"
                    value={
                      ml.confidence >= 0 && ml.confidence <= 1
                        ? fmtPct01(ml.confidence)
                        : `${fmtNum(ml.confidence, 1)}%`
                    }
                  />
                ) : null}
              </TelemetryStrip>
              {ml.features.length > 0 ? (
                <div>
                  <div className="micro-label" style={{ marginBottom: 3 }}>Top features</div>
                  <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: 2 }}>
                    {ml.features.map((f, i) => {
                      const ftone = toneFor(f.contribution);
                      return (
                        <li
                          key={`${f.name}-${i}`}
                          style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 11.5 }}
                        >
                          <span
                            className="muted"
                            title={f.name}
                            style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                          >
                            {f.name}
                          </span>
                          <span
                            className={`num ${ftone === 'bull' ? 'v-bull' : ftone === 'bear' ? 'v-bear' : 'faint'}`}
                            style={{ fontWeight: 600 }}
                          >
                            {f.contribution === null ? '—' : fmtSigned(f.contribution, 2)}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ) : null}
            </div>
          </details>
        ) : null}
      </div>
    </section>
  );
}
