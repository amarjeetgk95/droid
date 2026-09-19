'use client';

import { Fragment, useState } from 'react';
import { Square, TrendingUp } from 'lucide-react';
import type { TradeMode, TradePosition } from '@/lib/tradeOps';
import { fmtInr, pnlClass } from '@/lib/ledger';
import { safeNum } from '@/lib/utils';
import { OptionPayoffDiagram } from '@/components/ui/OptionPayoffDiagram';

export function PositionsPanel({
  positions,
  mode,
  loading,
  busyId,
  onExit,
  onExitAll,
}: {
  positions: TradePosition[];
  mode: TradeMode;
  loading: boolean;
  busyId: string | null;
  onExit: (position: TradePosition) => void;
  onExitAll: () => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const openCount = positions.filter((p) => p.isOpen !== false).length;
  return (
    <section className="panel">
      <header className="card-hd">
        <h3 className="card-title">Positions</h3>
        <span className="card-meta">
          {openCount} open · mode {mode}
        </span>
      </header>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-sell"
          disabled={positions.length === 0}
          title="Trigger emergency exit on every open position — asks for typed confirmation"
          onClick={onExitAll}
        >
          Exit all
        </button>
      </div>
      {positions.length === 0 ? (
        <p className="sg-empty">
          {loading
            ? 'Loading positions…'
            : 'No algo positions on record. Fills from executed orders open positions here.'}
        </p>
      ) : (
        <div className="tbl-scroll">
          <table className="sg-table">
            <thead>
              <tr>
                <th>Contract</th>
                <th>Side</th>
                <th className="r">Qty</th>
                <th className="r">Avg</th>
                <th className="r">LTP</th>
                <th className="r">Unrealized</th>
                <th>Status</th>
                <th className="r">Action</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => {
                const busy = busyId === position.id;
                const open = position.isOpen !== false;
                const optMatch = position.symbol.match(/(\d{4,5})\s*(CE|PE)/i);
                const strike = optMatch ? parseInt(optMatch[1], 10) : null;
                const isCall = optMatch ? optMatch[2].toUpperCase() === 'CE' : true;
                const isOption = strike !== null;
                const isExpanded = expandedId === position.id;

                return (
                  <Fragment key={position.id}>
                    <tr>
                      <td>
                        <div className="sg-sym">{position.symbol}</div>
                        <div className="sg-rownote">
                          {position.underlying ?? '—'}
                          {position.strategyId ? ` · ${position.strategyId}` : ''}
                        </div>
                      </td>
                      <td>
                        <span className={`sg-tag ${position.side === 'SHORT' || position.side === 'SELL' ? 'bear' : position.side ? 'bull' : 'neut'}`}>
                          {position.side ?? '—'}
                        </span>
                      </td>
                      <td className="r mono">{position.quantity ?? '—'}</td>
                      <td className="r mono">{safeNum(position.avgEntry)}</td>
                      <td className="r mono">{safeNum(position.currentPrice)}</td>
                      <td className={`r mono ${pnlClass(position.unrealized)}`}>
                        {fmtInr(position.unrealized, true)}
                      </td>
                      <td>
                        <span className={`sg-tag ${open ? 'bull' : 'neut'}`}>
                          {position.exitState ?? (open ? 'OPEN' : 'CLOSED')}
                        </span>
                      </td>
                      <td>
                        <div className="sg-actions">
                          {isOption ? (
                            <button
                              type="button"
                              className={`sg-ibtn ${isExpanded ? 'active text-primary' : ''}`}
                              title={isExpanded ? 'Hide payoff diagram' : 'Show payoff diagram at expiry'}
                              onClick={() => setExpandedId(isExpanded ? null : position.id)}
                            >
                              <TrendingUp size={12} />
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className="sg-ibtn danger"
                            title={open ? 'Exit this position' : 'Position already closed'}
                            disabled={busy || !open}
                            onClick={() => onExit(position)}
                          >
                            <Square size={12} />
                          </button>
                        </div>
                      </td>
                    </tr>
                    {isExpanded && isOption ? (
                      <tr>
                        <td colSpan={8} className="p-2.5 bg-surface-subtle border-b border-border">
                          <OptionPayoffDiagram
                            direction={isCall ? 'LONG_CALL' : 'LONG_PUT'}
                            strike={strike}
                            entryPremium={position.avgEntry ?? 100}
                            lotSize={Math.abs(position.quantity ?? 25)}
                            currentSpot={position.currentPrice}
                          />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
