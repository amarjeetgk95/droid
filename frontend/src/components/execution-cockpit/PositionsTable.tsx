'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { usePaperTradingData } from '@/context/PaperTradingContext';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { errorMessage } from '@/lib/errors';
import type { AlgoPosition } from '@/lib/api/algo';
import type { VirtualPosition } from '@/lib/types';
import { ageLabel } from '@/lib/feedState';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

type Desk = 'PAPER' | 'ALGO';

interface CockpitPosition {
  position_id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  average_price: number | null;
  ltp: number | null;
  unrealized_pnl: number | null;
  product: string | null;
  is_open: boolean;
  source: Desk;
}

function mapPaper(p: VirtualPosition): CockpitPosition {
  return {
    position_id: p.position_id,
    symbol: p.symbol,
    side: p.side,
    quantity: toNumber(p.quantity) ?? 0,
    average_price: toNumber(p.average_price),
    ltp: toNumber(p.ltp),
    unrealized_pnl: toNumber(p.unrealized_pnl),
    product: p.product ?? null,
    is_open: p.is_open !== false,
    source: 'PAPER',
  };
}

function mapAlgo(p: AlgoPosition): CockpitPosition {
  const raw = p as AlgoPosition & { ltp?: unknown };
  return {
    position_id: p.position_id,
    symbol: p.symbol,
    side: p.side === 'SELL' ? 'SELL' : 'BUY',
    quantity: toNumber(p.quantity) ?? 0,
    average_price: toNumber(p.average_price),
    ltp: toNumber(raw.ltp) ?? toNumber(p.current_price),
    unrealized_pnl: toNumber(p.unrealized_pnl),
    product: p.product ?? null,
    is_open: true,
    source: 'ALGO',
  };
}

const money = (value: number | null): string =>
  value === null
    ? '—'
    : `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const PositionsTable: React.FC = () => {
  const {
    positions: paperPositions,
    loading: paperLoading,
    positionsError: paperError,
    squareOffPosition,
    refresh: refreshPaper,
    lastUpdated: paperLastUpdated,
  } = usePaperTradingData({ pollIntervalMs: 4000 });

  const [algoPositions, setAlgoPositions] = useState<AlgoPosition[]>([]);
  const [algoLoaded, setAlgoLoaded] = useState(false);
  const [algoError, setAlgoError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const [exitTarget, setExitTarget] = useState<CockpitPosition | null>(null);
  const [closingId, setClosingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const action = useAsyncAction({
    errorFallback: 'Unknown execution error',
    busyMessage: 'An exit is already in progress. Wait for it to finish.',
  });

  const refreshAlgo = useCallback(async () => {
    try {
      const res = await api.getAlgoPositions();
      if (Array.isArray(res?.data)) {
        setAlgoPositions(res.data);
        setAlgoError(null);
      } else {
        setAlgoError('algo desk returned an invalid payload');
      }
    } catch (err) {
      setAlgoError(`algo desk: ${errorMessage(err, 'Unknown execution error')}`);
    } finally {
      setAlgoLoaded(true);
    }
  }, []);

  usePolling(refreshAlgo, 4000);

  const loaded = !paperLoading || algoLoaded;

  const positions = useMemo(() => {
    const merged: CockpitPosition[] = [];
    paperPositions.forEach((p) => {
      if (p.is_open !== false) merged.push(mapPaper(p));
    });
    algoPositions.forEach((p) => {
      merged.push(mapAlgo(p));
    });
    return merged;
  }, [paperPositions, algoPositions]);

  const failures: string[] = [];
  if (paperError) failures.push(`paper desk: ${paperError}`);
  if (algoError) failures.push(algoError);
  const loadError = failures.length > 0 ? failures.join(' · ') : null;

  useEffect(() => {
    if (!loaded) return;
    setAnnouncement(
      positions.length === 0
        ? 'Position book updated — no open positions'
        : `Position book updated — ${positions.length} open position(s)`,
    );
  }, [positions, loaded]);

  const handleExitConfirm = async () => {
    const target = exitTarget;
    if (!target) return;
    setActionError(null);
    setActionNotice(null);
    setClosingId(target.position_id);

    const outcome = await action.run(async () => {
      if (target.source === 'ALGO') {
        const res = await api.exitAlgoPosition(target.position_id);
        const data = res?.data as { closed?: boolean } | undefined;
        if (data?.closed !== true) {
          throw new Error(
            `Broker did not confirm the exit for ${target.symbol} (closed: ${String(
              data?.closed,
            )}). The position remains open.`,
          );
        }
      } else {
        const res = (await squareOffPosition(target.position_id)) as
          | { data?: unknown; error?: string }
          | undefined;
        const data = res?.data as unknown as
          | { closed?: boolean; is_open?: boolean }
          | undefined;
        const confirmed =
          data?.closed === true || (data?.closed === undefined && data?.is_open === false);
        if (!confirmed) {
          throw new Error(
            `Paper desk did not confirm the close for ${target.symbol}. The position remains open.`,
          );
        }
      }
      return true;
    });

    setClosingId(null);
    if (!outcome.ok) {
      setActionError(outcome.message);
      throw new Error(outcome.message);
    }

    if (target.source === 'ALGO') {
      await refreshAlgo();
    } else {
      await refreshPaper();
    }
    setActionNotice(`Exit confirmed for ${target.symbol} (${target.source} desk).`);
  };

  const lastUpdated = paperLastUpdated ? paperLastUpdated.getTime() : null;
  const formatAge = lastUpdated === null ? null : ageLabel(lastUpdated);

  return (
    <Card
      title={`OPEN POSITIONS (${positions.length})`}
      subtitle="Unified live position book across Paper and Algo execution desks"
    >
      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>

      {(loadError || actionError || actionNotice) && (
        <div className="mb-2 space-y-1.5 font-mono text-[11px]">
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
          {loadError && (
            <div className="rounded border border-warn-line bg-warn-wash px-2.5 py-1.5 text-warn-strong">
              Position refresh problem: {loadError}
              {lastUpdated !== null && formatAge ? ` · last known rows ${formatAge}` : ''}
            </div>
          )}
        </div>
      )}

      <div className="overflow-x-auto w-full font-mono text-xs">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-border bg-surface-subtle text-ink-3 text-[10px] uppercase">
              <th className="py-2.5 px-3">Contract</th>
              <th className="py-2.5 px-3">Desk</th>
              <th className="py-2.5 px-3">Side</th>
              <th className="py-2.5 px-3">Qty</th>
              <th className="py-2.5 px-3">Avg Price</th>
              <th className="py-2.5 px-3">LTP</th>
              <th className="py-2.5 px-3 text-right">P&amp;L</th>
              <th className="py-2.5 px-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {!loaded ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-ink-3">
                  Loading open positions…
                </td>
              </tr>
            ) : positions.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-ink-3">
                  {loadError ? 'Open positions unavailable.' : 'No active open positions.'}
                </td>
              </tr>
            ) : (
              positions.map((pos) => {
                const pnl = pos.unrealized_pnl;
                const isProfit = pnl !== null && pnl >= 0;

                return (
                  <tr key={`${pos.source}-${pos.position_id}`} className="hover:bg-muted transition-colors">
                    <td className="py-2 px-3 font-bold text-ink">{pos.symbol}</td>
                    <td className="py-2 px-3">
                      <Badge variant={pos.source === 'ALGO' ? 'danger' : 'info'} size="xs">
                        {pos.source}
                      </Badge>
                    </td>
                    <td className="py-2 px-3">
                      <Badge variant={pos.side === 'BUY' ? 'bull' : 'bear'} size="xs">
                        {pos.side}
                      </Badge>
                    </td>
                    <td className="py-2 px-3 text-ink-2">{pos.quantity}</td>
                    <td className="py-2 px-3 text-ink-2">{money(pos.average_price)}</td>
                    <td className="py-2 px-3 text-ink font-semibold">{money(pos.ltp)}</td>
                    <td
                      className={`py-2 px-3 text-right font-bold ${
                        pnl === null ? 'text-ink-3' : isProfit ? 'text-up-strong' : 'text-down-strong'
                      }`}
                    >
                      {pnl === null ? '—' : `${isProfit ? '+' : ''}${money(pnl)}`}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <button
                        type="button"
                        onClick={() => {
                          setActionError(null);
                          setActionNotice(null);
                          setExitTarget(pos);
                        }}
                        disabled={action.isPending || closingId === pos.position_id}
                        className="px-2.5 py-1 rounded bg-down-wash hover:opacity-80 border border-down-line text-down-strong text-[11px] font-semibold transition-all disabled:opacity-50"
                      >
                        {closingId === pos.position_id ? 'Exiting…' : 'Exit'}
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        isOpen={exitTarget !== null}
        onClose={() => setExitTarget(null)}
        onConfirm={handleExitConfirm}
        title={exitTarget ? `EXIT POSITION — ${exitTarget.symbol}` : 'EXIT POSITION'}
        message={
          exitTarget ? (
            <div className="space-y-2 font-mono text-xs">
              <p>
                Close this{' '}
                <span className="font-bold text-ink">
                  {exitTarget.source === 'ALGO' ? 'algo' : 'paper'}
                </span>{' '}
                position at the current market price?
              </p>
              <dl className="rounded border border-border bg-surface-subtle p-2.5 space-y-1">
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Instrument</dt>
                  <dd className="font-semibold text-ink">{exitTarget.symbol}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Desk</dt>
                  <dd className="text-ink-2">{exitTarget.source}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Direction</dt>
                  <dd className="text-ink-2">
                    {exitTarget.side} · {exitTarget.quantity} qty
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Avg / LTP</dt>
                  <dd className="text-ink-2">
                    {money(exitTarget.average_price)} · {money(exitTarget.ltp)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Unrealized P&amp;L</dt>
                  <dd
                    className={
                      exitTarget.unrealized_pnl === null
                        ? 'text-ink-3'
                        : exitTarget.unrealized_pnl >= 0
                          ? 'text-up-strong'
                          : 'text-down-strong'
                    }
                  >
                    {money(exitTarget.unrealized_pnl)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Position ID</dt>
                  <dd className="text-ink-2">{exitTarget.position_id}</dd>
                </div>
              </dl>
              <p className="text-ink-3">
                The exit is sent to the live desk and cannot be cancelled once acknowledged.
              </p>
            </div>
          ) : null
        }
        confirmLabel="CONFIRM EXIT"
        destructive={true}
      />
    </Card>
  );
};
