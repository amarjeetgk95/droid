'use client';

import React, { useCallback, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useExecutionGuard } from '@/hooks/useExecutionGuard';
import { api } from '@/lib/api';
import type { PortfolioSummary } from '@/lib/types';
import { ageLabel } from '@/lib/feedState';
import { Card } from '../shared/Card';
import { Gauge } from '../shared/Gauge';
import { ConfirmDialog } from '../shared/ConfirmDialog';

function toNumber(value: unknown): number | null {
  const n = typeof value === 'string' ? Number(value) : value;
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

function errorMessage(err: unknown): string {
  return err instanceof Error && err.message ? err.message : 'Unknown portfolio error';
}

const money = (value: number | null): string =>
  value === null ? '—' : `₹${value.toLocaleString('en-IN')}`;

export const PaperPortfolioCard: React.FC = () => {
  const [data, setData] = useState<Partial<PortfolioSummary> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [squareOffModal, setSquareOffModal] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [partialWarning, setPartialWarning] = useState<string | null>(null);
  const guard = useExecutionGuard();

  const refresh = useCallback(async () => {
    try {
      const res = await api.getPaperPortfolio();
      if (res?.error) throw new Error(res.error);
      if (!res?.data) throw new Error('Backend returned no portfolio payload.');
      setData(res.data);
      setLastUpdated(Date.now());
      setLoadError(null);
    } catch (err) {
      setLoadError(errorMessage(err));
    }
  }, []);

  usePolling(refresh, 4000);

  const capital = toNumber(data?.virtual_capital);
  const availableMargin = toNumber(data?.available_margin);
  const unrealizedPnl = toNumber(data?.total_unrealized_pnl);
  const realizedPnl = toNumber(data?.total_realized_pnl);
  const openPositions = toNumber(data?.open_positions_count);

  const reportedMarginPct = toNumber(data?.margin_utilization_pct);
  const derivedMarginPct =
    capital !== null && capital > 0 && availableMargin !== null
      ? Math.round(((capital - availableMargin) / capital) * 100)
      : null;
  const marginPct = reportedMarginPct ?? derivedMarginPct;
  const usedMargin =
    capital !== null && availableMargin !== null ? capital - availableMargin : null;

  const handleSquareOffAll = async () => {
    const openBefore = openPositions ?? 0;
    setActionError(null);
    setActionNotice(null);
    setPartialWarning(null);

    let failure: string | null = null;
    const outcome = await guard.execute(async () => {
      try {
        const res = await api.closeAllPaperPositions();
        if (res?.error) throw new Error(res.error);
        const rows: unknown = res?.data;
        if (!Array.isArray(rows)) {
          throw new Error('Paper desk did not return a square-off result — verify positions manually.');
        }
        const closedCount = rows.length;
        if (openBefore > 0 && closedCount < openBefore) {
          setPartialWarning(
            `Square-off incomplete: ${closedCount} of ${openBefore} position(s) confirmed closed. Refresh and retry the remainder.`,
          );
        } else {
          setActionNotice(`Square-off confirmed: ${closedCount} position(s) closed.`);
        }
        return true;
      } catch (err) {
        failure = errorMessage(err);
        throw err;
      }
    });

    if (outcome === null) {
      const message = failure ?? 'A square-off is already in progress. Wait for it to finish.';
      setActionError(message);
      throw new Error(message);
    }

    await refresh();
  };

  const lastAge = lastUpdated === null ? null : ageLabel(lastUpdated);
  const squareOffDisabled =
    openPositions === null || openPositions === 0 || guard.isPending || data === null;

  return (
    <>
      <Card
        title="PORTFOLIO CAPITAL & MARGIN DESK"
        subtitle="Real-time margin allocation and aggregate MTM accounting"
        headerAction={
          <button
            type="button"
            onClick={() => {
              setActionError(null);
              setActionNotice(null);
              setPartialWarning(null);
              setSquareOffModal(true);
            }}
            disabled={squareOffDisabled}
            className="px-2.5 py-1 rounded bg-down-wash hover:opacity-80 border border-down-line text-down-strong font-mono text-xs font-semibold disabled:opacity-40"
          >
            Square Off All
          </button>
        }
      >
        <div className="space-y-4 font-mono text-xs">
          {actionError && (
            <div
              role="alert"
              className="rounded border border-down-line bg-down-wash px-2.5 py-1.5 text-down-strong"
            >
              {actionError}
            </div>
          )}
          {actionNotice && (
            <div
              role="status"
              className="rounded border border-up-line bg-up-wash px-2.5 py-1.5 text-up-strong"
            >
              {actionNotice}
            </div>
          )}
          {partialWarning && (
            <div
              role="alert"
              className="rounded border border-warn-line bg-warn-wash px-2.5 py-1.5 text-warn-strong"
            >
              {partialWarning}
            </div>
          )}

          {data === null ? (
            <div className="p-3 rounded-lg bg-surface-subtle border border-border text-ink-3">
              {loadError ? (
                <span role="alert" className="text-down-strong">
                  Paper portfolio unavailable — {loadError}
                </span>
              ) : (
                'Loading paper portfolio…'
              )}
            </div>
          ) : (
            <>
              {loadError && (
                <div
                  role="alert"
                  className="rounded border border-warn-line bg-warn-wash px-2.5 py-1.5 text-warn-strong"
                >
                  Portfolio refresh failed — showing last known values
                  {lastAge ? ` (${lastAge})` : ''}: {loadError}
                </div>
              )}

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div className="p-2.5 rounded-lg bg-surface-subtle border border-border">
                  <div className="text-[10px] text-ink-3 uppercase">Total Capital</div>
                  <div className="text-sm font-bold text-ink mt-0.5">{money(capital)}</div>
                </div>

                <div className="p-2.5 rounded-lg bg-surface-subtle border border-border">
                  <div className="text-[10px] text-ink-3 uppercase">Available Margin</div>
                  <div className="text-sm font-bold text-primary mt-0.5">{money(availableMargin)}</div>
                </div>

                <div className="p-2.5 rounded-lg bg-surface-subtle border border-border">
                  <div className="text-[10px] text-ink-3 uppercase">Unrealized MTM</div>
                  <div
                    className={`text-sm font-bold mt-0.5 ${
                      unrealizedPnl === null
                        ? 'text-ink-3'
                        : unrealizedPnl >= 0
                          ? 'text-up-strong'
                          : 'text-down-strong'
                    }`}
                  >
                    {unrealizedPnl === null
                      ? '—'
                      : `${unrealizedPnl >= 0 ? '+' : ''}${money(unrealizedPnl)}`}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-surface-subtle border border-border">
                  <div className="text-[10px] text-ink-3 uppercase">Realized P&amp;L</div>
                  <div
                    className={`text-sm font-bold mt-0.5 ${
                      realizedPnl === null
                        ? 'text-ink-3'
                        : realizedPnl >= 0
                          ? 'text-up-strong'
                          : 'text-down-strong'
                    }`}
                  >
                    {realizedPnl === null
                      ? '—'
                      : `${realizedPnl >= 0 ? '+' : ''}${money(realizedPnl)}`}
                  </div>
                </div>
              </div>

              {marginPct === null ? (
                <div className="p-2.5 rounded-lg bg-surface-subtle border border-border text-ink-3">
                  Gross margin utilization unavailable — backend did not report margin figures.
                </div>
              ) : (
                <Gauge
                  value={marginPct}
                  label="Gross Margin Utilization"
                  sublabel={
                    usedMargin === null
                      ? 'Allocated margin not reported'
                      : `${money(usedMargin)} allocated across ${
                          openPositions ?? '—'
                        } active position(s)`
                  }
                  thresholds={{ warning: 60, danger: 85 }}
                />
              )}
            </>
          )}
        </div>
      </Card>

      <ConfirmDialog
        isOpen={squareOffModal}
        onClose={() => setSquareOffModal(false)}
        onConfirm={handleSquareOffAll}
        title="SQUARE OFF ALL PAPER POSITIONS"
        message={
          <div className="space-y-2 font-mono text-xs">
            <p>
              Exit <span className="font-bold text-ink">{openPositions ?? 0} open paper position(s)</span>{' '}
              immediately at current market prices?
            </p>
            <dl className="rounded border border-border bg-surface-subtle p-2.5 space-y-1">
              <div className="flex justify-between gap-3">
                <dt className="text-ink-3">Desk</dt>
                <dd className="text-ink-2">PAPER</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-3">Positions to close</dt>
                <dd className="font-semibold text-ink">{openPositions ?? '—'}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-3">Unrealized MTM at risk</dt>
                <dd
                  className={
                    unrealizedPnl === null
                      ? 'text-ink-3'
                      : unrealizedPnl >= 0
                        ? 'text-up-strong'
                        : 'text-down-strong'
                  }
                >
                  {money(unrealizedPnl)}
                </dd>
              </div>
            </dl>
            <p className="text-ink-3">
              All exits are sent to the paper desk at once; the result is verified before the book is
              updated.
            </p>
          </div>
        }
        confirmLabel="SQUARE OFF ALL"
        destructive={true}
      />
    </>
  );
};
