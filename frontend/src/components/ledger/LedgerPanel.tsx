'use client';

import { useCallback, useState } from 'react';
import { RotateCcw, Square } from 'lucide-react';
import { fmtInr, pnlClass, positionUnrealized } from '@/lib/ledger';
import { safeNum } from '@/lib/utils';
import { shortId, stateTone, type LedgerRow } from '@/lib/signalsNormalize';
import type { VirtualPosition } from '@/lib/types';
import type { LedgerActionResult, PaperLedgerState } from '@/hooks/usePaperLedger';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/toast';

function sideText(side: string | null | undefined): string {
  return side === 'SELL' ? 'SHORT' : 'LONG';
}

function StatusStrip({ ledger }: { ledger: PaperLedgerState }) {
  const { totals, ledgerSummary } = ledger;
  return (
    <div className="pnl-strip">
      <span className="ps">
        <span className="ps-l">Source</span>
        <span className="ps-v">{ledger.liveSource === 'stream' ? 'LIVE MTM' : 'REST SNAPSHOT'}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Capital</span>
        <span className="ps-v">{fmtInr(totals.capital)}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Available</span>
        <span className="ps-v">{fmtInr(totals.available)}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Used</span>
        <span className="ps-v">
          {fmtInr(totals.used)}
          {totals.utilizationPct !== null ? ` (${safeNum(totals.utilizationPct, '—', 1)}%)` : ''}
        </span>
      </span>
      <span className="ps">
        <span className="ps-l">Realized</span>
        <span className={`ps-v ${pnlClass(totals.realized)}`}>{fmtInr(totals.realized, true)}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Unrealized</span>
        <span className={`ps-v ${pnlClass(totals.unrealized)}`}>{fmtInr(totals.unrealized, true)}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Total P&amp;L</span>
        <span className={`ps-v ${pnlClass(totals.total)}`}>{fmtInr(totals.total, true)}</span>
      </span>
      <span className="ps">
        <span className="ps-l">Open</span>
        <span className="ps-v">{totals.openCount}</span>
      </span>
      {ledgerSummary?.winRate !== null && ledgerSummary?.winRate !== undefined ? (
        <span className="ps">
          <span className="ps-l">Win rate</span>
          <span className="ps-v">
            {safeNum(ledgerSummary.winRate * (ledgerSummary.winRate <= 1 ? 100 : 1), '—', 1)}%
          </span>
        </span>
      ) : null}
    </div>
  );
}

function PositionsTable({
  positions,
  onSquareOff,
  busyId,
}: {
  positions: VirtualPosition[];
  onSquareOff: (position: VirtualPosition) => void;
  busyId: string | null;
}) {
  if (positions.length === 0) {
    return <p className="sg-empty">No open paper positions.</p>;
  }
  return (
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
            <th className="r col-hide-m">Margin</th>
            <th className="r">Action</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => {
            const unrealized = positionUnrealized(position);
            return (
              <tr key={position.position_id}>
                <td>
                  <div className="sg-sym">{position.symbol}</div>
                  <div className="sg-rownote">
                    {position.underlying} · {position.product} · {shortId(position.position_id)}
                  </div>
                </td>
                <td>
                  <span className={`sg-dir ${position.side === 'SELL' ? 'short' : 'long'}`}>
                    {sideText(position.side)}
                  </span>
                </td>
                <td className="r mono">{position.quantity}</td>
                <td className="r mono">{safeNum(position.average_price)}</td>
                <td className="r mono">{safeNum(position.ltp)}</td>
                <td className={`r mono ${pnlClass(unrealized)}`}>{fmtInr(unrealized, true)}</td>
                <td className="r mono col-hide-m">{fmtInr(position.used_margin)}</td>
                <td>
                  <div className="sg-actions">
                    <button
                      type="button"
                      className="sg-ibtn danger"
                      title="Square off this position"
                      disabled={busyId === position.position_id}
                      onClick={() => onSquareOff(position)}
                    >
                      <Square size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function LedgerHistoryTable({ rows }: { rows: LedgerRow[] }) {
  if (rows.length === 0) {
    return <p className="sg-empty">No audited signal history yet.</p>;
  }
  return (
    <div className="tbl-scroll">
      <table className="sg-table">
        <thead>
          <tr>
            <th>Signal</th>
            <th>Status</th>
            <th className="r">Qty</th>
            <th className="r">Entry</th>
            <th className="r">Exit / LTP</th>
            <th className="r">Realized</th>
            <th className="r">Total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <div className="sg-sym">{row.underlying}</div>
                <div className="sg-rownote">
                  {row.strategy} · {shortId(row.id)}
                  {row.outcomeLabel ? ` · ${row.outcomeLabel}` : ''}
                </div>
              </td>
              <td>
                <span className={`sg-tag ${stateTone(row.status)}`}>{row.status}</span>
                {row.quarantined ? (
                  <span className="sg-tag warn ml-1" title={row.quarantineReason ?? undefined}>
                    QUARANTINED
                  </span>
                ) : null}
              </td>
              <td className="r mono">{row.qty ?? '—'}</td>
              <td className="r mono">{safeNum(row.entry)}</td>
              <td className="r mono">{safeNum(row.exit ?? row.current)}</td>
              <td className={`r mono ${pnlClass(row.realized)}`}>{fmtInr(row.realized, true)}</td>
              <td className={`r mono ${pnlClass(row.total)}`}>{fmtInr(row.total, true)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function LedgerPanel({ ledger, marketClosed }: { ledger: PaperLedgerState; marketClosed: boolean }) {
  const { push } = useToast();
  const [pendingPosition, setPendingPosition] = useState<VirtualPosition | null>(null);
  const [closeAllOpen, setCloseAllOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const runAction = useCallback(
    async (action: () => Promise<LedgerActionResult>) => {
      const result = await action();
      push(result.ok ? 'success' : 'error', result.message);
    },
    [push],
  );

  const handleSquareOff = useCallback(async () => {
    if (!pendingPosition) return;
    setBusyId(pendingPosition.position_id);
    try {
      await runAction(() => ledger.closePosition(pendingPosition.position_id));
    } finally {
      setBusyId(null);
      setPendingPosition(null);
    }
  }, [ledger, pendingPosition, runAction]);

  return (
    <div className="flex flex-col gap-3">
      <StatusStrip ledger={ledger} />

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn"
          onClick={() => void ledger.refresh()}
          disabled={ledger.refreshing}
        >
          {ledger.refreshing ? 'Refreshing…' : 'Refresh ledger'}
        </button>
        <button
          type="button"
          className="btn btn-sell"
          disabled={ledger.positions.length === 0 || marketClosed}
          title={marketClosed ? 'Market closed — square-off disabled.' : 'Square off every open paper position'}
          onClick={() => setCloseAllOpen(true)}
        >
          Square off all
        </button>
        <button type="button" className="btn btn-ic" onClick={() => setResetOpen(true)}>
          <RotateCcw size={13} />
          Reset account
        </button>
        {ledger.error ? <span className="sg-err">{ledger.error}</span> : null}
      </div>

      <section className="panel">
        <header className="card-hd">
          <h3 className="card-title">Open Positions — Realtime MTM</h3>
          <span className="card-meta">
            {ledger.liveSource === 'stream' ? 'stream ~4s' : 'rest fallback'}
            {ledger.totals.openCount > 0 ? ` · ${ledger.totals.openCount} open` : ''}
          </span>
        </header>
        <PositionsTable
          positions={ledger.positions}
          onSquareOff={setPendingPosition}
          busyId={busyId}
        />
      </section>

      <div className="ds-grid-dashboard">
        <section className="panel">
          <header className="card-hd">
            <h3 className="card-title">Recent Paper Orders</h3>
            <span className="card-meta">{ledger.orders.length}</span>
          </header>
          {ledger.orders.length === 0 ? (
            <p className="sg-empty">No paper orders yet.</p>
          ) : (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Contract</th>
                    <th>Side</th>
                    <th className="r">Qty</th>
                    <th className="r">Fill</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {ledger.orders.slice(0, 15).map((order) => (
                    <tr key={order.order_id}>
                      <td className="mono">
                        {order.timestamp
                          ? new Date(order.timestamp).toLocaleTimeString('en-IN', {
                              timeZone: 'Asia/Kolkata',
                              hour: '2-digit',
                              minute: '2-digit',
                            })
                          : '—'}
                      </td>
                      <td>
                        <div className="sg-sym">{order.symbol}</div>
                        <div className="sg-rownote">{order.order_type}</div>
                      </td>
                      <td>
                        <span className={`sg-dir ${order.side === 'SELL' ? 'short' : 'long'}`}>
                          {order.side}
                        </span>
                      </td>
                      <td className="r mono">{order.quantity}</td>
                      <td className="r mono">{safeNum(order.fill_price ?? order.price)}</td>
                      <td>
                        <span className={`sg-tag ${order.status === 'FILLED' ? 'bull' : order.status === 'REJECTED' ? 'bear' : 'neut'}`}>
                          {order.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel">
          <header className="card-hd">
            <h3 className="card-title">Signal Audit Ledger</h3>
            <span className="card-meta">{ledger.ledgerRows.length} records</span>
          </header>
          <LedgerHistoryTable rows={ledger.ledgerRows} />
        </section>
      </div>

      <ConfirmDialog
        open={pendingPosition !== null}
        onOpenChange={(open) => {
          if (!open) setPendingPosition(null);
        }}
        tone="danger"
        confirmLabel="Square off"
        title={`Square off ${pendingPosition?.symbol ?? 'position'}?`}
        intentRows={
          pendingPosition
            ? [
                { label: 'Side', value: sideText(pendingPosition.side) },
                { label: 'Quantity', value: String(pendingPosition.quantity) },
                { label: 'LTP', value: safeNum(pendingPosition.ltp) },
                {
                  label: 'Unrealized',
                  value: fmtInr(positionUnrealized(pendingPosition), true),
                },
              ]
            : undefined
        }
        onConfirm={handleSquareOff}
      />

      <ConfirmDialog
        open={closeAllOpen}
        onOpenChange={setCloseAllOpen}
        tone="danger"
        confirmLabel="Square off all"
        title="Square off every open paper position?"
        description="Realized P&L is booked at the live mark. This cannot be undone."
        onConfirm={() => runAction(() => ledger.closeAll())}
      />

      <ConfirmDialog
        open={resetOpen}
        onOpenChange={setResetOpen}
        tone="danger"
        confirmLabel="Reset account"
        requireTypedConfirmation="RESET"
        title="Reset the paper trading account?"
        description="All positions and order history are cleared and the virtual capital is restored."
        onConfirm={() => runAction(() => ledger.resetAccount())}
      />
    </div>
  );
}
