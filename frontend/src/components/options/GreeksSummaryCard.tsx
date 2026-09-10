'use client';

import { Card, Stat, fmtNum } from '@/components/ui/desk';

/**
 * GreeksSummaryCard — slim port of `components/options-intelligence/PortfolioGreeksTab`.
 * Keeps the quant display math (delta/gamma/theta/vega formatting, horizon and
 * underlying exposure tables). Drops the cross-horizon harmonizer prose and
 * badge cards; the single `/options` page only needs the numbers.
 *
 * Backend-compat: the ledger returns `net_exposure_by_underlying` and
 * `positions_by_horizon` while older payloads carried `by_underlying` /
 * `by_horizon` delta-theta maps. Both shapes render; tables prefer the
 * delta-theta maps when present.
 */

export interface GreeksSummaryData {
  total_delta: number;
  total_gamma: number;
  total_theta_day: number;
  total_vega: number;
  total_open_positions: number;
  by_horizon?: Record<string, { delta: number; theta: number }>;
  by_underlying?: Record<string, { delta: number; theta: number }>;
  net_exposure_by_underlying?: Record<string, number>;
  positions_by_horizon?: Record<string, number>;
}

export function GreeksSummaryCard({ summary }: { summary: GreeksSummaryData | null }) {
  const delta = summary?.total_delta ?? 0.0;
  const gamma = summary?.total_gamma ?? 0.0;
  const theta = summary?.total_theta_day ?? 0.0;
  const vega = summary?.total_vega ?? 0.0;
  const openPositions = summary?.total_open_positions ?? 0;

  const byHorizon = summary?.by_horizon ? Object.entries(summary.by_horizon) : [];
  const byUnderlying = summary?.by_underlying ? Object.entries(summary.by_underlying) : [];
  const netByUnderlying = summary?.net_exposure_by_underlying
    ? Object.entries(summary.net_exposure_by_underlying)
    : [];
  const posByHorizon = summary?.positions_by_horizon
    ? Object.entries(summary.positions_by_horizon)
    : [];

  return (
    <Card title="Greeks summary" meta={`${openPositions} open positions`}>
      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <Stat
          label="Portfolio delta"
          value={delta > 0 ? `+${fmtNum(delta)}` : fmtNum(delta)}
          sub="Net directional shares equivalent."
          tone={delta > 0 ? 'bull' : delta < 0 ? 'bear' : 'neut'}
        />
        <Stat label="Portfolio gamma" value={fmtNum(gamma, 4)} sub="Second-order curvature exposure." />
        <Stat
          label="Daily theta burn"
          value={`₹${Math.abs(theta).toLocaleString('en-IN', { maximumFractionDigits: 0 })}/day`}
          sub="Consolidated overnight decay cost."
        />
        <Stat
          label="Portfolio vega"
          value={`₹${vega.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
          sub="Exposure per 1% IV shift."
        />
      </div>

      {byHorizon.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="faint" style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', marginBottom: 6 }}>
            EXPOSURE BY HORIZON
          </div>
          <div className="tbl-wrap">
            <table className="tbl num">
              <thead>
                <tr>
                  <th>Horizon</th>
                  <th className="r">Delta</th>
                  <th className="r">Theta</th>
                </tr>
              </thead>
              <tbody>
                {byHorizon.map(([k, v]) => (
                  <tr key={k}>
                    <td>{k}</td>
                    <td className="r">{fmtNum(v.delta)}</td>
                    <td className="r">{fmtNum(v.theta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {byUnderlying.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="faint" style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', marginBottom: 6 }}>
            EXPOSURE BY UNDERLYING
          </div>
          <div className="tbl-wrap">
            <table className="tbl num">
              <thead>
                <tr>
                  <th>Underlying</th>
                  <th className="r">Delta</th>
                  <th className="r">Theta</th>
                </tr>
              </thead>
              <tbody>
                {byUnderlying.map(([k, v]) => (
                  <tr key={k}>
                    <td>{k}</td>
                    <td className="r">{fmtNum(v.delta)}</td>
                    <td className="r">{fmtNum(v.theta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {byHorizon.length === 0 && byUnderlying.length === 0 && (netByUnderlying.length > 0 || posByHorizon.length > 0) && (
        <div style={{ marginTop: 12 }}>
          <div className="faint" style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', marginBottom: 4 }}>
            LEDGER BREAKDOWN
          </div>
          {netByUnderlying.length > 0 && (
            <p className="muted num" style={{ margin: '0 0 4px', fontSize: 12 }}>
              Net exposure: {netByUnderlying.map(([k, v]) => `${k} ${fmtNum(Number(v))}`).join(' · ')}
            </p>
          )}
          {posByHorizon.length > 0 && (
            <p className="muted num" style={{ margin: 0, fontSize: 12 }}>
              Positions: {posByHorizon.map(([k, v]) => `${k} ${v}`).join(' · ')}
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
