'use client';

import { Card, EmptyNote, Stat, fmtINR, fmtNum, fmtSigned } from '@/components/ui/desk';

/**
 * ExpectedMoveCard — ported from `components/options-intelligence/ExpectedMoveTab`.
 * Quant math preserved verbatim (metric formatting, T1/T2/T3 ladder, velocity
 * badge, rationale list). Only the tab wrapper was dropped; this is a plain
 * sober card for the single `/options` page.
 *
 * Backend-compat note: the engine returns `conservative_move_points` /
 * `aggressive_move_points` / `expected_move_points` as point OFFSETS from spot,
 * while older payloads carried absolute PRICES. `resolveTarget` treats a value
 * far below spot as an offset (spot + points) and anything near/above spot as a
 * legacy price, so both shapes render the same ladder. T3 resolves through the
 * same helper (`extended_target_t3`, else `expected_move_points`).
 */

export interface ExpectedMoveData {
  underlying: string;
  spot?: number;
  spot_price?: number;
  direction: 'BULLISH' | 'BEARISH' | string;
  horizon: string;
  expected_duration_hours?: number;
  expected_move_points?: number;
  expected_target_price?: number;
  expected_velocity_pts_per_hour?: number;
  iv_implied_1sigma_move?: number;
  atr_excursion_points?: number;
  hourly_theta_decay?: number;
  is_fast_enough_for_option?: boolean;
  forecast_rationale?: string[];
  conservative_target_t1?: number;
  structural_target_t2?: number;
  extended_target_t3?: number;
  conservative_move_points?: number;
  aggressive_move_points?: number;
}

export function resolveTarget(
  raw: number | null | undefined,
  spot: number,
  fallbackOffset: number,
): number {
  if (raw === null || raw === undefined || Number.isNaN(raw)) return spot + fallbackOffset;
  // Backend shape: small point offset (e.g. 45) far below a 25k spot.
  if (spot > 0 && raw > 0 && raw < spot * 0.5) return spot + raw;
  // Legacy shape: absolute price near spot.
  return raw;
}

export interface ExpectedMoveLadder {
  t1: number;
  t2: number;
  t3: number;
  t1Points: number;
  t2Points: number;
  t3Points: number;
}

export function resolveLadder(data: ExpectedMoveData, spot: number): ExpectedMoveLadder {
  const sign = data.direction === 'BEARISH' ? -1 : 1;
  const t1Points = Math.abs(resolveTarget(data.conservative_move_points, spot, 80) - spot) || 80;
  const t2Points = Math.abs(resolveTarget(data.aggressive_move_points, spot, 160) - spot) || 160;
  const t3Points =
    Math.abs(
      resolveTarget(data.extended_target_t3 ?? data.expected_move_points, spot, 100) - spot,
    ) || 100;
  return {
    t1: spot + sign * t1Points,
    t2: spot + sign * t2Points,
    t3: spot + sign * t3Points,
    t1Points,
    t2Points,
    t3Points,
  };
}

function fmtStat(v: number | null | undefined, digits: number, suffix: string): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${fmtNum(v, digits)}${suffix}` : '—';
}

export function ExpectedMoveCard({
  data,
  loading = false,
  error = null,
}: {
  data: ExpectedMoveData | null;
  loading?: boolean;
  error?: string | null;
}) {
  const spot = data?.spot_price ?? data?.spot ?? 0;

  if (!data || spot <= 0) {
    if (loading) {
      return (
        <Card title="Expected move — 1h forecast" meta="computing…">
          <div style={{ display: 'grid', gap: 8 }}>
            <div className="skel" style={{ height: 14, width: '55%' }}>.</div>
            <div className="skel" style={{ height: 64, width: '100%' }}>.</div>
          </div>
          <p className="muted" style={{ margin: '10px 0 0', fontSize: 12 }}>
            Projecting velocity, targets and theta drag from the live chain spot and ATM IV…
          </p>
        </Card>
      );
    }
    return (
      <Card title="Expected move — 1h forecast" meta="unavailable">
        <EmptyNote>
          {error
            ? `Expected move projection failed — ${error}`
            : 'Expected move projection unavailable — velocity vs theta ratios and staged target ladders require authentic market data from your broker API.'}
        </EmptyNote>
        {error ? null : (
          <p className="muted" style={{ margin: '8px 0 0', fontSize: 12 }}>
            <a href="/settings">Connect broker in Settings</a>
          </p>
        )}
      </Card>
    );
  }

  const velocityKnown = typeof data.is_fast_enough_for_option === 'boolean';
  const isVelocityApproved = data.is_fast_enough_for_option === true;
  const { t1, t2, t3, t1Points, t2Points, t3Points } = resolveLadder(data, spot);
  const sign = data.direction === 'BEARISH' ? -1 : 1;
  const targetPrice = resolveTarget(data.expected_target_price, spot, sign * t3Points);

  const range = Math.max(1, Math.abs(t3 - spot));
  const p1 = Math.min(100, Math.max(0, (t1Points / range) * 100));
  const p2 = Math.min(100, Math.max(0, (t2Points / range) * 100));

  return (
    <Card
      title="Expected move — 1h forecast"
      meta={`${data.underlying} · ${data.direction} · ${data.horizon}`}
      action={
        <span className={`badge ${!velocityKnown ? 'b-neut' : isVelocityApproved ? 'b-bull' : 'b-warn'}`}>
          {!velocityKnown
            ? 'Velocity check unavailable'
            : isVelocityApproved
              ? 'Velocity approved for buying'
              : 'Velocity too slow (theta dominates)'}
        </span>
      }
    >
      <p className="muted num" style={{ margin: '0 0 12px', fontSize: 12.5 }}>
        {data.underlying} spot {fmtINR(spot)}, {data.direction}, {data.horizon}.
      </p>

      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <Stat
          label="Expected move"
          value={fmtStat(data.expected_move_points, 1, ' pts')}
          sub={`Target ${fmtINR(targetPrice)}`}
        />
        <Stat
          label="Price velocity"
          value={fmtStat(data.expected_velocity_pts_per_hour, 1, ' pts/hr')}
          sub={data.expected_velocity_pts_per_hour == null ? 'Not published' : 'Underlying speed'}
        />
        <Stat
          label="Hourly theta drag"
          value={
            typeof data.hourly_theta_decay === 'number' && Number.isFinite(data.hourly_theta_decay)
              ? `-${fmtINR(Math.abs(data.hourly_theta_decay))}/hr`
              : '—'
          }
          sub="Option premium decay"
        />
        <Stat
          label="Expected duration"
          value={fmtStat(data.expected_duration_hours, 1, ' hrs')}
          sub="Target arrival horizon"
        />
        <Stat
          label="1-sigma IV move"
          value={
            typeof data.iv_implied_1sigma_move === 'number' && Number.isFinite(data.iv_implied_1sigma_move)
              ? `±${fmtNum(data.iv_implied_1sigma_move, 1)} pts`
              : '—'
          }
          sub="Statistical dispersion"
        />
        <Stat
          label="ATR excursion"
          value={fmtStat(data.atr_excursion_points, 1, ' pts')}
          sub="Range baseline"
        />
      </div>

      <div style={{ marginTop: 12 }}>
        <div className="faint" style={{ fontSize: 11, marginBottom: 4 }}>
          Spot {fmtINR(spot)} to T3 {fmtINR(t3)}
        </div>
        <div
          className="meter"
          role="img"
          aria-label={`Expected move ladder from spot ${fmtINR(spot)}: T1 ${fmtINR(t1)}, T2 ${fmtINR(t2)}, T3 ${fmtINR(t3)}.`}
          style={{ position: 'relative', overflow: 'visible' }}
        >
          <i style={{ width: '100%', opacity: 0.25 }} aria-hidden />
          <span
            aria-hidden
            title="T1"
            style={{ position: 'absolute', top: -3, bottom: -3, left: `${p1}%`, width: 2, background: 'var(--ds-ink)' }}
          />
          <span
            aria-hidden
            title="T2"
            style={{ position: 'absolute', top: -3, bottom: -3, left: `${p2}%`, width: 2, background: 'var(--ds-accent)' }}
          />
          <span
            aria-hidden
            title="T3"
            style={{ position: 'absolute', top: -3, bottom: -3, right: 0, width: 2, background: 'var(--ds-ink)' }}
          />
        </div>
        <div className="toolbar" style={{ justifyContent: 'space-between', marginTop: 4 }}>
          <span className="faint num" style={{ fontSize: 11 }}>T1 {fmtINR(t1)}</span>
          <span className="faint num" style={{ fontSize: 11 }}>T2 {fmtINR(t2)}</span>
          <span className="faint num" style={{ fontSize: 11 }}>T3 {fmtINR(t3)}</span>
        </div>
      </div>

      <div style={{ marginTop: 10 }}>
        <div className="faint" style={{ fontSize: 11 }}>Timing and velocity diagnostics</div>
        <ul className="muted" style={{ margin: '4px 0 0 18px', padding: 0, fontSize: 12 }}>
          {data.forecast_rationale && data.forecast_rationale.length > 0 ? (
            data.forecast_rationale.map((r: string, i: number) => (
              <li key={i} style={{ marginBottom: 4 }}>{r}</li>
            ))
          ) : (
            <li>No forecast rationale published by the engine.</li>
          )}
        </ul>
      </div>

      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', marginTop: 12 }}>
        <Stat
          label="Conservative target (T1)"
          value={fmtINR(t1)}
          sub={`${fmtSigned(sign * t1Points, 1)} pts · ~${fmtNum((data.expected_duration_hours || 1.0) * 0.5, 1)} hrs`}
        />
        <Stat
          label="Structural target (T2)"
          value={fmtINR(t2)}
          sub={`${fmtSigned(sign * t2Points, 1)} pts · ~${fmtNum(data.expected_duration_hours || 1.0, 1)} hrs`}
        />
        <Stat
          label="Extended target (T3)"
          value={fmtINR(t3)}
          sub={`${fmtSigned(sign * t3Points, 1)} pts · ~${fmtNum((data.expected_duration_hours || 1.0) * 1.5, 1)} hrs`}
        />
      </div>
      <p className="faint" style={{ margin: '10px 0 0', fontSize: 11.5 }}>
        T1 scalp anchor · T2 liquidity retest · T3 momentum extension.
      </p>
    </Card>
  );
}
