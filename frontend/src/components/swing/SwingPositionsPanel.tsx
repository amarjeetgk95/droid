'use client';

import { Square } from 'lucide-react';
import type { PortfolioRiskDTO, SwingPositionDTO } from '@/lib/api/swing';
import { toNumber } from '@/lib/coerce';
import { pnlClass } from '@/lib/ledger';
import { fmtDateTimeMs, fmtExpiry } from '@/lib/signalsNormalize';
import { safeNum } from '@/lib/utils';

function toMs(value: unknown): number | null {
  const n = toNumber(value);
  if (n === null) return null;
  return n < 1e12 ? Math.round(n * 1000) : Math.round(n);
}

function RiskStrip({ risk }: { risk: PortfolioRiskDTO | null }) {
  return (
    <div className="pnl-strip">
      <span className="ps">
        <span className="ps-l">Equity</span>
        <span className="ps-v">{safeNum(risk?.total_equity, '—', 0)}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Premium deployed</span>
        <span className="ps-v">{safeNum(risk?.total_premium_deployed, '—', 0)}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Premium at risk</span>
        <span className="ps-v">{safeNum(risk?.premium_at_risk, '—', 0)}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Heat</span>
        <span className="ps-v">
          {safeNum(risk?.portfolio_heat_pct, '—', 1)}%
          {risk?.max_heat_pct !== undefined ? ` / ${safeNum(risk.max_heat_pct, '—', 1)}%` : ''}
        </span>
      </span>
      <span className="ps">
        <span className="ps-l">Net Δ</span>
        <span className="ps-v">{safeNum(risk?.net_delta, '—', 2)}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Net Θ/day</span>
        <span className="ps-v">{safeNum(risk?.net_theta_day, '—', 1)}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Net ν</span>
        <span className="ps-v">{safeNum(risk?.net_vega, '—', 1)}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Open</span>
        <span className="ps-v">
          {safeNum(risk?.open_positions_count, '—', 0)}
          {risk?.max_positions_count !== undefined ? ` / ${risk.max_positions_count}` : ''}
        </span>
      </span>
    </div>
  );
}

function OpenPositionsTable({
  positions,
  busyPositionId,
  onExit,
}: {
  positions: SwingPositionDTO[];
  busyPositionId: string | null;
  onExit: (position: SwingPositionDTO) => void;
}) {
  if (positions.length === 0) {
    return <p className="sg-empty">No open swing positions.</p>;
  }
  return (
    <div className="tbl-scroll">
      <table className="sg-table">
        <thead>
          <tr>
            <th>Contract</th>
            <th className="r">Lots</th>
            <th className="r">Entry → Current</th>
            <th className="r">Stop</th>
            <th className="r">Targets</th>
            <th className="r">R</th>
            <th className="r">Unrealized</th>
            <th className="r">Exit</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => (
            <tr key={position.position_id}>
              <td>
                <div className="sg-sym">{position.contract_symbol}</div>
                <div className="sg-rownote">
                  {position.underlying} · {position.strike} {position.option_type} · {fmtExpiry(position.expiry_date)} ·{' '}
                  {position.strategy}
                </div>
              </td>
              <td className="r">
                <div className="mono">{position.num_lots}</div>
                <div className="sg-rownote">
                  held {position.days_held}d · DTE {position.dte_remaining}
                </div>
              </td>
              <td className="r">
                <div className="mono">
                  {safeNum(position.entry_premium)} → {safeNum(position.current_premium)}
                </div>
                <div className="sg-rownote">
                  spot {safeNum(position.spot_at_entry, '—', 0)} → {safeNum(position.current_spot, '—', 0)}
                </div>
              </td>
              <td className="r">
                <div className="mono">{safeNum(position.current_stop_premium)}</div>
                <div className="sg-rownote">
                  spot {safeNum(position.spot_stop, '—', 0)} · {position.stop_method}
                </div>
              </td>
              <td className="r">
                <div className="mono">
                  {safeNum(position.target_1)} / {safeNum(position.target_2)}
                </div>
                <div className="sg-rownote">high {safeNum(position.highest_premium)}</div>
              </td>
              <td className={`r mono ${pnlClass(position.r_multiple)}`}>
                {safeNum(position.r_multiple)}R
              </td>
              <td className={`r mono ${pnlClass(position.unrealized_pnl)}`}>
                <div>{safeNum(position.unrealized_pnl, '—', 0)}</div>
                <div className="sg-rownote">{safeNum(position.pnl_pct, '—', 2)}%</div>
              </td>
              <td>
                <div className="sg-actions">
                  <button
                    type="button"
                    className="sg-ibtn danger"
                    title="Close this position at the last scanner mark"
                    disabled={busyPositionId === position.position_id}
                    onClick={() => onExit(position)}
                  >
                    <Square size={12} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClosedPositionsTable({ positions }: { positions: SwingPositionDTO[] }) {
  if (positions.length === 0) {
    return <p className="sg-empty">No closed swing positions yet.</p>;
  }
  return (
    <div className="tbl-scroll">
      <table className="sg-table">
        <thead>
          <tr>
            <th>Contract</th>
            <th className="r">Entry</th>
            <th className="r">Exit</th>
            <th className="r">R</th>
            <th className="r">P&amp;L</th>
            <th>Reason</th>
            <th>Closed</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => (
            <tr key={position.position_id}>
              <td>
                <div className="sg-sym">{position.contract_symbol}</div>
                <div className="sg-rownote">
                  {position.underlying} · {position.num_lots} lot(s)
                </div>
              </td>
              <td className="r mono">{safeNum(position.entry_premium)}</td>
              <td className="r mono">{safeNum(position.close_premium ?? position.current_premium)}</td>
              <td className={`r mono ${pnlClass(position.r_multiple)}`}>
                {safeNum(position.r_multiple)}R
              </td>
              <td className={`r mono ${pnlClass(position.unrealized_pnl)}`}>
                <div>{safeNum(position.unrealized_pnl, '—', 0)}</div>
                <div className="sg-rownote">{safeNum(position.pnl_pct, '—', 2)}%</div>
              </td>
              <td>
                <span className="sg-tag neut">{position.exit_reason ?? '—'}</span>
              </td>
              <td className="mono">{fmtDateTimeMs(toMs(position.closed_at_utc))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SwingPositionsPanel({
  openPositions,
  closedPositions,
  portfolioRisk,
  busyPositionId,
  onExit,
}: {
  openPositions: SwingPositionDTO[];
  closedPositions: SwingPositionDTO[];
  portfolioRisk: PortfolioRiskDTO | null;
  busyPositionId: string | null;
  onExit: (position: SwingPositionDTO) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <RiskStrip risk={portfolioRisk} />
      <section className="panel">
        <header className="card-hd">
          <h3 className="card-title">Open Positions — Dual-Layer Stops</h3>
          <span className="card-meta">{openPositions.length} open</span>
        </header>
        <OpenPositionsTable
          positions={openPositions}
          busyPositionId={busyPositionId}
          onExit={onExit}
        />
      </section>
      <section className="panel">
        <header className="card-hd">
          <h3 className="card-title">Closed Positions</h3>
          <span className="card-meta">{closedPositions.length} recent</span>
        </header>
        <ClosedPositionsTable positions={closedPositions} />
      </section>
    </div>
  );
}
