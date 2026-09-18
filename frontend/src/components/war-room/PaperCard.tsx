'use client';

/* PaperCard — Phase W6 paper-portfolio truth for the War Room rail.
 *
 * Consumes usePaperTrading hook (self-fetching on a 15s poll).
 * Square-off (per-row and square-off-all) is destructive and goes through
 * the shared ConfirmDialog with an intent block.
 */

import { memo, useCallback, useState } from 'react';
import { fmtINR, TelemetryStrip, TelemetryItem } from '@/components/ui/desk';
import { ConfirmDialog, type ConfirmIntentRow } from '@/components/ui/ConfirmDialog';
import { usePaperTrading } from '@/hooks/usePaperTrading';
import type { VirtualPosition } from '@/lib/types';

const POLL_MS = 15_000;

function fmtQty(v: unknown): string {
  const n = typeof v === 'string' ? Number(v) : (v as number);
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return n.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

function fmtUtil(v: unknown): string {
  const n = typeof v === 'string' ? Number(v) : (v as number);
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return `${n.toFixed(1)}%`;
}

function fmtClock(d: Date): string {
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function pnlTone(v: unknown): 'bull' | 'bear' | undefined {
  const n = typeof v === 'string' ? Number(v) : (v as number);
  if (typeof n !== 'number' || !Number.isFinite(n) || n === 0) return undefined;
  return n > 0 ? 'bull' : 'bear';
}

type PendingAction =
  | { kind: 'single'; position: VirtualPosition; snapshot: string }
  | { kind: 'all'; count: number; snapshot: string };

function intentRows(pending: PendingAction | null): ConfirmIntentRow[] {
  if (!pending) return [];
  if (pending.kind === 'all') {
    return [
      { label: 'Positions', value: `${pending.count} open` },
      { label: 'Action', value: 'Square off all at live mark' },
      { label: 'Snapshot', value: pending.snapshot },
    ];
  }
  const p = pending.position;
  return [
    { label: 'Position', value: `${p.symbol} · ${String(p.position_id).slice(0, 8)}` },
    { label: 'Side', value: `${p.side} ${fmtQty(p.quantity)}` },
    { label: 'Basis', value: fmtINR(p.average_price) },
    { label: 'Snapshot', value: pending.snapshot },
  ];
}

export const PaperCard = memo(function PaperCard() {
  const {
    portfolio,
    positions,
    loading,
    portfolioError: portfolioNote,
    positionsError: positionsNote,
    lastUpdated: updatedAt,
    squareOffPosition,
    squareOffAll,
    refresh,
  } = usePaperTrading({ pollIntervalMs: POLL_MS });

  const [actionNote, setActionNote] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [acting, setActing] = useState(false);

  const confirmSquareOff = useCallback(async () => {
    if (!pending || acting) return;
    setActing(true);
    setActionNote(null);
    try {
      if (pending.kind === 'all') {
        await squareOffAll();
      } else {
        await squareOffPosition(pending.position.position_id);
      }
      setPending(null);
      await refresh();
    } catch (err) {
      setActionNote(err instanceof Error ? err.message : 'square-off failed');
    } finally {
      setActing(false);
    }
  }, [pending, acting, squareOffAll, squareOffPosition, refresh]);

  const positionsKnown = !loading || positions.length > 0;
  const openCount = positions.length;
  const showSkeleton = loading && portfolio === null && !positionsKnown;

  return (
    <section className="card" aria-label="Paper portfolio">
      <div className="card-hd">
        <h2 className="card-title">Paper portfolio</h2>
        {positionsKnown ? <span className="card-meta num">{openCount} open</span> : null}
      </div>
      <div className="card-bd" style={{ padding: 0 }}>
        {showSkeleton ? (
          <div style={{ display: 'grid', gap: 6, padding: '8px 12px' }} aria-label="Loading paper portfolio">
            {[88, 72, 80].map((w, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <div className="skel" style={{ height: 12, width: 64 }}>.</div>
                <div className="skel num" style={{ height: 12, width: w }}>.</div>
              </div>
            ))}
          </div>
        ) : null}

        {portfolio ? (
          <TelemetryStrip>
            <TelemetryItem label="Capital" value={<span className="num">{fmtINR(portfolio.virtual_capital)}</span>} />
            <TelemetryItem label="Avail margin" value={<span className="num">{fmtINR(portfolio.available_margin)}</span>} />
            <TelemetryItem label="Used margin" value={<span className="num">{fmtINR(portfolio.used_margin)}</span>} />
            <TelemetryItem label="Util" value={<span className="num">{fmtUtil(portfolio.margin_utilization_pct)}</span>} />
            <TelemetryItem
              label="Realized"
              tone={pnlTone(portfolio.total_realized_pnl)}
              value={<span className="num">{fmtINR(portfolio.total_realized_pnl)}</span>}
            />
            <TelemetryItem
              label="Unrealized"
              tone={pnlTone(portfolio.total_unrealized_pnl)}
              value={<span className="num">{fmtINR(portfolio.total_unrealized_pnl)}</span>}
            />
          </TelemetryStrip>
        ) : null}
        {portfolioNote && !showSkeleton ? (
          <p className="muted num" style={{ margin: 0, padding: '6px 12px', fontSize: 12 }} title={portfolioNote}>
            paper portfolio unavailable — {portfolioNote}
          </p>
        ) : null}

        {positionsKnown && openCount === 0 && !positionsNote ? (
          <p className="muted" style={{ margin: 0, padding: '6px 12px 8px', fontSize: 12 }}>
            No open paper positions
          </p>
        ) : null}
        {positionsNote ? (
          <p className="muted num" style={{ margin: 0, padding: '6px 12px', fontSize: 12 }} title={positionsNote}>
            paper positions unavailable — {positionsNote}
            {openCount > 0 ? ' · showing last known list' : ''}
          </p>
        ) : null}

        {openCount > 0 ? (
          <div className="tbl-wrap" style={{ border: 0 }}>
            <table className="tbl tbl-dense num">
              <thead>
                <tr>
                  <th scope="col">Symbol</th>
                  <th scope="col">Side</th>
                  <th scope="col" className="r">Qty</th>
                  <th scope="col" className="r">Entry</th>
                  <th scope="col" className="r">Live</th>
                  <th scope="col" className="r">P&amp;L</th>
                  <th scope="col"><span className="faint">Exit</span></th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => {
                  const pnl = typeof p.unrealized_pnl === 'number' && Number.isFinite(p.unrealized_pnl)
                    ? p.unrealized_pnl
                    : null;
                  return (
                    <tr key={p.position_id}>
                      <td title={p.position_id}>{p.symbol}</td>
                      <td>
                        <span className={`chip ${p.side === 'SELL' ? 'chip--down' : 'chip--up'}`}>{p.side}</span>
                      </td>
                      <td className="r">{fmtQty(p.quantity)}</td>
                      <td className="r">{fmtINR(p.average_price)}</td>
                      <td className="r">{fmtINR(p.ltp)}</td>
                      <td
                        className="r"
                        title={typeof p.realized_pnl === 'number' ? `realized ${fmtINR(p.realized_pnl)}` : undefined}
                      >
                        <span className={pnl !== null && pnl > 0 ? 'v-bull' : pnl !== null && pnl < 0 ? 'v-bear' : undefined}>
                          {pnl === null ? '—' : fmtINR(pnl)}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn"
                          style={{ fontSize: 11, padding: '2px 8px' }}
                          disabled={acting}
                          onClick={() => setPending({ kind: 'single', position: p, snapshot: fmtClock(new Date()) })}
                        >
                          Square off
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}

        {openCount > 0 ? (
          <div style={{ padding: '6px 12px 8px' }}>
            <button
              type="button"
              className="btn w-full"
              style={{ fontSize: 11 }}
              disabled={acting}
              onClick={() => setPending({ kind: 'all', count: openCount, snapshot: fmtClock(new Date()) })}
            >
              Square off all ({fmtQty(openCount)})
            </button>
          </div>
        ) : null}

        {actionNote ? (
          <p role="status" className="muted num" style={{ margin: 0, padding: '0 12px 8px', fontSize: 12 }} title={actionNote}>
            square-off failed — {actionNote}
          </p>
        ) : null}
        {updatedAt && (portfolio || positionsKnown) ? (
          <div className="faint num" style={{ fontSize: 11, padding: '0 12px 8px' }} title={updatedAt.toISOString()}>
            updated {fmtClock(updatedAt)}
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => { if (!open) setPending(null); }}
        busy={acting}
        tone="danger"
        title={
          pending?.kind === 'all'
            ? `Square off all ${pending.count} open paper positions?`
            : pending
              ? `Square off ${pending.position.symbol} ${pending.position.side} ${fmtQty(pending.position.quantity)}?`
              : 'Square off paper position?'
        }
        description={
          pending?.kind === 'all'
            ? 'Closes every open paper position at the live mark. Simulated only, no real orders.'
            : 'Closes this paper position at the live mark. Simulated only, no real order.'
        }
        intentRows={intentRows(pending)}
        confirmLabel={pending?.kind === 'all' ? 'Square off all' : 'Square off'}
        onConfirm={() => { void confirmSquareOff(); }}
      />
    </section>
  );
});

export default PaperCard;
