'use client';

import type { PapHorizon, PapLive } from '@/lib/api/pap';
import {
  PAP_UNAVAILABLE_LABEL,
  alignmentBadgeClass,
  alignmentLabel,
  confidenceLabel,
  dataStatusOf,
  fmtAge,
  fmtClock,
  fmtPrice,
  freshnessBadgeClass,
  horizonDist,
  isPapUnavailable,
  papFreshnessOf,
  predictionBadgeClass,
  unavailableReason,
} from '@/lib/pap';

export function ProbabilityBar({ horizon }: { horizon: PapHorizon }) {
  const dist = horizonDist(horizon);
  const up = dist.find((d) => d.label === 'UP')?.pct ?? 0;
  const neut = dist.find((d) => d.label === 'NEUTRAL')?.pct ?? 0;
  const down = dist.find((d) => d.label === 'DOWN')?.pct ?? 0;
  return (
    <div>
      <div
        className="prob-bar-stacked"
        role="img"
        aria-label={`Up ${up}%, neutral ${neut}%, down ${down}%`}
        data-testid="pap-prob-bar"
      >
        <i className="seg-bull" style={{ width: `${up}%` }} />
        <i className="seg-neut" style={{ width: `${neut}%` }} />
        <i className="seg-bear" style={{ width: `${down}%` }} />
      </div>
      <div className="mt-1 flex items-center justify-between font-mono text-[11px] text-ink-2">
        <span className="v-bull">UP {up}%</span>
        <span>NEU {neut}%</span>
        <span className="v-bear">DOWN {down}%</span>
      </div>
    </div>
  );
}

export function HorizonCard({ id, horizon }: { id: string; horizon: PapHorizon }) {
  return (
    <section className="card" aria-label={`PAP ${id} prediction`} data-testid={`pap-horizon-${id}`}>
      <div className="card-hd">
        <h3 className="card-title">{id.toUpperCase()}</h3>
        <span className={`badge ${predictionBadgeClass(horizon.prediction)}`} data-testid={`pap-pred-${id}`}>
          {horizon.prediction}
        </span>
      </div>
      <div className="card-bd flex flex-col gap-2">
        <ProbabilityBar horizon={horizon} />
        <div className="flex items-center justify-between">
          <span className="stat-l">confidence</span>
          <span className="mono text-[13px] font-semibold" data-testid={`pap-conf-${id}`}>
            {confidenceLabel(horizon)}
            {horizon.confidence === null ? (
              <span className="card-meta"> · not calibrated</span>
            ) : null}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`badge ${horizon.prediction_state === 'ACTIVE' ? 'b-bull' : 'b-warn'}`}>
            {horizon.prediction_state}
          </span>
          {horizon.calibrated ? (
            <span className="badge b-bull">CALIBRATED</span>
          ) : (
            <span className="badge b-warn" title="No calibrated artifact for this horizon — probabilities are advisory">
              NOT CALIBRATED
            </span>
          )}
          {horizon.model_source === 'heuristic_ensemble' ? (
            <span className="badge b-neut" title="Heuristic fallback from real features — not a trained prediction">
              HEURISTIC
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function fmtVal(v: number | string | null | undefined, digits = 2): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'string') return v;
  if (!Number.isFinite(v)) return '—';
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(digits)}`;
}

export function PapLivePanel({
  live,
  error,
  loading,
}: {
  live: PapLive | null;
  error: string | null;
  loading: boolean;
}) {
  if (loading && !live && !error) {
    return (
      <section className="card" aria-label="PAP live">
        <div className="card-bd">
          <p className="sg-empty">Loading PAP Intelligence…</p>
        </div>
      </section>
    );
  }

  if (error && !live) {
    return (
      <section className="card" aria-label="PAP live">
        <div className="card-hd">
          <h3 className="card-title">PAP Intelligence</h3>
          <span className="badge b-warn">OFFLINE</span>
        </div>
        <div className="card-bd">
          <p className="sg-err" data-testid="pap-unavailable">
            {PAP_UNAVAILABLE_LABEL} — {error}
          </p>
        </div>
      </section>
    );
  }

  if (isPapUnavailable(live)) {
    return (
      <section className="card" aria-label="PAP live">
        <div className="card-hd">
          <h3 className="card-title">PAP Intelligence</h3>
          <span className="badge b-warn" data-testid="pap-status">
            {dataStatusOf(live)}
          </span>
        </div>
        <div className="card-bd">
          <p className="sg-err" data-testid="pap-unavailable">
            {PAP_UNAVAILABLE_LABEL}
            {live?.unavailable_reason ? ` — ${live.unavailable_reason}` : ''}
          </p>
          <p className="sg-note mt-2">
            Shadow mode stays on. DROID strategy, risk, FSM and execution are unaffected.
          </p>
        </div>
      </section>
    );
  }

  const l = live as PapLive;
  const freshness = papFreshnessOf(l.data_status, l.data_age_s);
  const ms = (l.market_state ?? {}) as Record<string, number | string | null>;
  const align = l.droid_alignment;

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar" aria-label="PAP live header">
        <div className="ds-title">
          <h2>PAP Intelligence</h2>
          <span className={`badge ${freshnessBadgeClass(freshness)}`} data-testid="pap-status">
            ● {freshness}
          </span>
          <span className="badge b-neut" title="PAP never places orders — advisory only">
            SHADOW
          </span>
          <span className="card-meta">{l.instrument}</span>
        </div>
        <div className="stat-chips">
          <span className="stat-chip" title="Current index price">
            price <b data-testid="pap-price">{fmtPrice(l.price)}</b>
          </span>
          <span className="stat-chip" title="Last backend update (IST)">
            updated <b>{fmtClock(l.timestamp)}</b>
          </span>
          <span className="stat-chip" title="Age of the backend quote">
            age <b data-testid="pap-age">{fmtAge(l.data_age_s)}</b>
          </span>
          <span className="stat-chip">timeframe <b>1 MIN</b></span>
        </div>
      </section>

      <div className="grid gap-3 md:grid-cols-3">
        {['3m', '5m', '10m'].map((id) =>
          l.horizons?.[id] ? <HorizonCard key={id} id={id} horizon={l.horizons[id]} /> : null,
        )}
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="card" aria-label="Horizon consensus">
          <div className="card-hd">
            <h3 className="card-title">Horizon consensus</h3>
          </div>
          <div className="card-bd">
            <div className="flex flex-col gap-1" data-testid="pap-consensus">
              {l.horizons
                ? Object.entries(l.horizons).map(([id, h]) => (
                    <div key={id} className="flex items-center justify-between text-xs">
                      <span className="stat-l">{id.toUpperCase()}</span>
                      <span>
                        <span className={`badge ${predictionBadgeClass(h.prediction)}`}>{h.prediction}</span>{' '}
                        <span className="mono text-ink-2">{h.probability}%</span>
                      </span>
                    </div>
                  ))
                : null}
            </div>
            <p className="mt-2 text-sm font-semibold" data-testid="pap-consensus-label">
              {l.horizon_consensus.consensus}
            </p>
            <p className="sg-note">Informational — horizons may disagree; that is shown, not averaged away.</p>
          </div>
        </section>

        <section className="card" aria-label="DROID PAP alignment">
          <div className="card-hd">
            <h3 className="card-title">DROID / PAP alignment</h3>
            <span className={`badge ${alignmentBadgeClass(align.alignment)}`} data-testid="pap-alignment">
              {alignmentLabel(align.alignment)}
            </span>
          </div>
          <div className="card-bd">
            <div className="sg-kvlist">
              <div className="sg-kv">
                <span className="l">DROID signal</span>
                <span className="v" data-testid="pap-droid-signal">
                  {align.droid_signal ?? '—'}
                  {align.droid_strategy ? ` · ${align.droid_strategy}` : ''}
                </span>
              </div>
              <div className="sg-kv">
                <span className="l">PAP (5M)</span>
                <span className="v">{align.pap_primary ?? '—'}</span>
              </div>
            </div>
            <p className="sg-note mt-2">
              Informational only — alignment never overrides strategy, risk, FSM or execution.
            </p>
          </div>
        </section>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="card" aria-label="PAP market state">
          <div className="card-hd">
            <h3 className="card-title">Market state</h3>
            <span className="card-meta">1m features</span>
          </div>
          <div className="card-bd">
            <div className="sg-kvlist" data-testid="pap-market-state">
              <div className="sg-kv">
                <span className="l">Fisher</span>
                <span className="v">{fmtVal(ms.fisher as number | null)}</span>
              </div>
              <div className="sg-kv">
                <span className="l">Price vs VWAP</span>
                <span className="v">{fmtVal(ms.price_vs_vwap_pct as number | null)}%</span>
              </div>
              <div className="sg-kv">
                <span className="l">ADX</span>
                <span className="v">{fmtVal(ms.adx as number | null, 1)}</span>
              </div>
              <div className="sg-kv">
                <span className="l">DMI</span>
                <span className="v">
                  +DI {fmtVal(ms.plus_di as number | null, 1)} / -DI {fmtVal(ms.minus_di as number | null, 1)}
                </span>
              </div>
              <div className="sg-kv">
                <span className="l">LR slope</span>
                <span className="v">{fmtVal(ms.lr_slope as number | null, 6)}</span>
              </div>
              <div className="sg-kv">
                <span className="l">BB width</span>
                <span className="v">{fmtVal(ms.bb_width_pct as number | null)}%</span>
              </div>
              <div className="sg-kv">
                <span className="l">Trend</span>
                <span className="v">{(ms.trend as string) ?? '—'}</span>
              </div>
              <div className="sg-kv">
                <span className="l">Volatility</span>
                <span className="v">{(ms.volatility as string) ?? '—'}</span>
              </div>
              <div className="sg-kv">
                <span className="l">VWAP position</span>
                <span className="v">{(ms.vwap_position as string) ?? '—'}</span>
              </div>
            </div>
          </div>
        </section>

        <section className="card" aria-label="PAP evidence">
          <div className="card-hd">
            <h3 className="card-title">PAP evidence</h3>
            <span className="card-meta">explanatory</span>
          </div>
          <div className="card-bd">
            <ul className="flex flex-col gap-1.5" data-testid="pap-evidence">
              {l.evidence.map((e, i) => (
                <li key={i} className="flex items-start gap-2 text-xs">
                  <span aria-hidden>
                    {e.state === 'supportive' ? '✓' : e.state === 'caution' ? '△' : '·'}
                  </span>
                  <span>
                    <span className="font-medium">{e.label}</span>{' '}
                    <span className="card-meta">{e.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="sg-note mt-2">{l.evidence_note ?? unavailableReason(null, '')}</p>
          </div>
        </section>
      </div>

      <section className="card" aria-label="PAP model quality">
        <div className="card-hd">
          <h3 className="card-title">Prediction quality</h3>
          <span className={`badge ${l.model.status === 'VALID' ? 'b-bull' : 'b-warn'}`}>{l.model.status}</span>
        </div>
        <div className="card-bd">
          <div className="stat-chips">
            <span className="stat-chip">
              model <b>{l.model.name}</b>
            </span>
            <span className="stat-chip" title={l.model.versions.join(', ')}>
              version <b>{l.model.versions[0] ?? '—'}</b>
            </span>
            <span className="stat-chip">
              schema <b>{l.model.feature_schema}</b>
            </span>
            <span className="stat-chip">
              calibration <b>{l.model.calibration.replace('_', ' ')}</b>
            </span>
            <span className="stat-chip">
              data <b>{l.model.data_quality}</b>
            </span>
            <span className="stat-chip">
              execution <b>{l.model.execution}</b>
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
