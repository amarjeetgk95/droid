'use client';

import { Card, EmptyNote, Stat, fmtINR, fmtNum } from '@/components/ui/desk';

/**
 * ExpectedMoveCard — ported from `components/options-intelligence/ExpectedMoveTab`.
 * Quant math preserved verbatim (metric formatting, T1/T2/T3 ladder, velocity
 * badge, rationale list). Only the tab wrapper was dropped; this is a plain
 * sober card for the single `/options` page.
 *
 * Backend-compat note: the engine returns `conservative_move_points` /
 * `aggressive_move_points` as point OFFSETS from spot, while older payloads
 * carried them as absolute PRICES. `resolveTarget` treats a value far below
 * spot as an offset (spot + points) and anything near/above spot as a legacy
 * price, so both shapes render the same ladder.
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

function resolveTarget(
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

export function ExpectedMoveCard({ data }: { data: ExpectedMoveData | null }) {
  const spot = data?.spot_price ?? data?.spot ?? 0;

  if (!data || spot <= 0) {
    return (
      <Card title="Expected move — 1h forecast" meta="unavailable">
        <EmptyNote>
          Expected move projection unavailable — velocity vs theta ratios and staged target ladders
          require authentic market data from your broker API.
        </EmptyNote>
        <p className="muted" style={{ margin: '8px 0 0', fontSize: 12 }}>
          <a href="/settings">Connect broker in Settings</a>
        </p>
      </Card>
    );
  }

  const isVelocityApproved = data.is_fast_enough_for_option ?? true;
  const bearish = data.direction === 'BEARISH';
  const sign = bearish ? -1 : 1;

  // Magnitudes preserved from the original tab; sign follows forecast direction.
  const t1mag = Math.abs(resolveTarget(data.conservative_move_points, spot, 80) - spot) || 80;
  const t2mag = Math.abs(resolveTarget(data.aggressive_move_points, spot, 160) - spot) || 160;
  const t3mag = Math.abs(data.expected_move_points || 100);
  const t1 = spot + sign * t1mag;
  const t2 = spot + sign * t2mag;
  const t3 = spot + sign * t3mag;

  const range = Math.max(1, Math.abs(t3 - spot));
  const p1 = Math.min(100, Math.max(0, (Math.abs(t1 - spot) / range) * 100));
  const p2 = Math.min(100, Math.max(0, (Math.abs(t2 - spot) / range) * 100));

  const movePts = data.expected_move_points || 0;
  const targetPrice = data.expected_target_price ?? t3;

  return (
    <Card
      title="Expected move — 1h forecast"
      meta={`${data.underlying} · ${data.direction} · ${data.horizon}`}
      action={
        <span className={`badge ${isVelocityApproved ? 'b-bull' : 'b-neut'}`}>
          {isVelocityApproved ? 'Velocity approved for buying' : 'Velocity too slow (theta dominates)'}
        </span>
      }
    >
      <p className="muted num" style={{ margin: '0 0 12px', fontSize: 12.5 }}>
        {data.underlying} spot {fmtINR(spot)}, {data.direction}, {data.horizon}.
      </p>

      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <Stat
          label="Expected move"
          value={`${fmtNum(movePts, 1)} pts`}
          sub={`Target ${fmtINR(targetPrice)}`}
        />
        <Stat
          label="Price velocity"
          value={`${fmtNum(data?.expected_velocity_pts_per_hour ?? 0, 1)} pts/hr`}
          sub="Underlying speed"
        />
        <Stat
          label="Hourly theta drag"
          value={`-${fmtINR(Math.abs(data?.hourly_theta_decay ?? 0))}/hr`}
          sub="Option premium decay"
        />
        <Stat
          label="Expected duration"
          value={`${fmtNum(data?.expected_duration_hours ?? 1, 1)} hrs`}
          sub="Target arrival horizon"
        />
        <Stat
          label="1-sigma IV move"
          value={`±${fmtNum(data?.iv_implied_1sigma_move ?? 0, 1)} pts`}
          sub="Statistical dispersion"
        />
        <Stat
          label="ATR excursion"
          value={`${fmtNum(data?.atr_excursion_points ?? 0, 1)} pts`}
          sub="Range baseline"
        />
      </div>

      <div style={{ marginTop: 12 }}>
        <div className="faint" style={{ fontSize: 11, marginBottom: 4 }}>
          Spot {fmtINR(spot)} to T3 {fmtINR(t3)}
        </div>
        <div className="meter" style={{ position: 'relative', overflow: 'visible' }}>
          <i style={{ width: '100%', opacity: 0.25 }} />
          <span
            title="T1"
            style={{ position: 'absolute', top: -3, bottom: -3, left: `${p1}%`, width: 2, background: 'var(--ds-ink)' }}
          />
          <span
            title="T2"
            style={{ position: 'absolute', top: -3, bottom: -3, left: `${p2}%`, width: 2, background: 'var(--ds-accent)' }}
          />
          <span
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
          {data?.forecast_rationale?.map((r: string, i: number) => (
            <li key={i} style={{ marginBottom: 4 }}>{r}</li>
          )) || <li>Standard session volatility baseline.</li>}
        </ul>
      </div>

      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', marginTop: 12 }}>
        <Stat
          label="Conservative target (T1)"
          value={fmtINR(t1)}
          sub={`+${fmtNum(Math.abs(t1 - spot), 1)} pts · ~${fmtNum((data?.expected_duration_hours || 1.0) * 0.5, 1)} hrs`}
        />
        <Stat
          label="Structural target (T2)"
          value={fmtINR(t2)}
          sub={`+${fmtNum(Math.abs(t2 - spot), 1)} pts · ~${fmtNum(data?.expected_duration_hours || 1.0, 1)} hrs`}
        />
        <Stat
          label="Extended target (T3)"
          value={fmtINR(t3)}
          sub={`+${fmtNum(Math.abs(t3 - spot), 1)} pts · ~${fmtNum((data?.expected_duration_hours || 1.0) * 1.5, 1)} hrs`}
        />
      </div>
      <p className="faint" style={{ margin: '10px 0 0', fontSize: 11.5 }}>
        T1 scalp anchor · T2 liquidity retest · T3 momentum extension.
      </p>
    </Card>
  );
}
