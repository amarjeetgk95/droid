'use client';

import { useCallback, useMemo, useState } from 'react';
import { useMarketSession } from '@/context/MarketSessionContext';
import { useTradeOps } from '@/hooks/useTradeOps';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/toast';
import { fmtInr, pnlClass } from '@/lib/ledger';
import { safeNum, safeStr } from '@/lib/utils';
import { shortId } from '@/lib/signalsNormalize';
import { modeBadgeClass, type TradeOrder, type TradePosition } from '@/lib/tradeOps';
import { OrdersPanel } from './OrdersPanel';
import { PositionsPanel } from './PositionsPanel';
import { SizingPanel } from './SizingPanel';
import { AuditPanel } from './AuditPanel';
import { HealthPanel } from './HealthPanel';

type ModuleTab = 'orders' | 'positions' | 'sizing' | 'audit' | 'health';

export function TradeModule() {
  const { isOpen } = useMarketSession();
  const { push } = useToast();
  const [tab, setTab] = useState<ModuleTab>('orders');
  const [pendingCancel, setPendingCancel] = useState<TradeOrder | null>(null);
  const [pendingReconcile, setPendingReconcile] = useState<TradeOrder | null>(null);
  const [pendingExit, setPendingExit] = useState<TradePosition | null>(null);
  const [exitAllOpen, setExitAllOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Read-only polling: 20s while the market is open, idle otherwise.
  const ops = useTradeOps({ safetyRefreshMs: isOpen ? 20_000 : null });

  const openPositions = useMemo(
    () => ops.positions.filter((position) => position.isOpen !== false),
    [ops.positions],
  );

  const handleCancel = useCallback(async () => {
    if (!pendingCancel) return;
    setBusyId(pendingCancel.id);
    try {
      const result = await ops.cancelOrder(pendingCancel.id);
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setBusyId(null);
      setPendingCancel(null);
    }
  }, [ops, pendingCancel, push]);

  const handleReconcile = useCallback(async () => {
    if (!pendingReconcile) return;
    setBusyId(pendingReconcile.id);
    try {
      const result = await ops.reconcileOrder(pendingReconcile.id);
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setBusyId(null);
      setPendingReconcile(null);
    }
  }, [ops, pendingReconcile, push]);

  const handleExit = useCallback(async () => {
    if (!pendingExit) return;
    setBusyId(pendingExit.id);
    try {
      const result = await ops.exitPosition(pendingExit.id);
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setBusyId(null);
      setPendingExit(null);
    }
  }, [ops, pendingExit, push]);

  const handleExitAll = useCallback(async () => {
    setBusyId('exit-all');
    try {
      const result = await ops.exitAll();
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setBusyId(null);
      setExitAllOpen(false);
    }
  }, [ops, push]);

  const modeBadge = `badge ${modeBadgeClass(ops.mode)}`;

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar">
        <div className="ds-title">
          <h2>Trade Ops</h2>
          <span
            className={modeBadge}
            title="Broker account mode. LIVE touches a real broker account — every action asks for confirmation."
          >
            {ops.mode === 'UNKNOWN' ? 'MODE UNKNOWN' : `${ops.mode} MODE`}
          </span>
          {ops.account?.killed === true ? (
            <span className="badge b-bear" title={`Kill switch active: ${ops.account.killLevel ?? 'unknown level'}`}>
              KILL ACTIVE
            </span>
          ) : null}
          <span className="card-meta">
            {safeStr(ops.account?.displayName, ops.account?.accountId ? shortId(ops.account.accountId) : '—')}
          </span>
        </div>
        <div className="stat-chips">
          <span className="stat-chip">
            open orders <b>{ops.orders.length}</b>
          </span>
          <span className="stat-chip">
            open positions <b>{openPositions.length}</b>
          </span>
          <span className="stat-chip">
            gross exposure <b>{fmtInr(ops.exposure?.gross)}</b>
          </span>
          <span className="stat-chip">
            buying power <b>{fmtInr(ops.account?.available)}</b>
          </span>
          <span className="stat-chip" title="algo command section: live stream vs REST fallback">
            {ops.ordersSource === 'stream' ? 'stream ~2s' : 'rest fallback'}
          </span>
          <span className="stat-chip">{isOpen ? 'market open' : 'market closed'}</span>
        </div>
        <div className="ds-filters">
          <button
            type="button"
            className="btn"
            disabled={ops.refreshing}
            onClick={() => void ops.refresh()}
          >
            {ops.refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      <div className="pnl-strip">
        <span className="ps">
          <span className="ps-l">Buying power</span>
          <span className="ps-v">{fmtInr(ops.account?.available)}</span>
        </span>
        <span className="ps">
          <span className="ps-l">Deployed</span>
          <span className="ps-v">{fmtInr(ops.account?.deployed)}</span>
        </span>
        <span className="ps">
          <span className="ps-l">Reserved</span>
          <span className="ps-v">{fmtInr(ops.account?.reserved)}</span>
        </span>
        <span className="ps">
          <span className="ps-l">Limit</span>
          <span className="ps-v">{fmtInr(ops.account?.investmentLimit)}</span>
        </span>
        <span className="ps">
          <span className="ps-l">Daily loss</span>
          <span className={`ps-v ${pnlClass(ops.account?.dailyLoss ? -ops.account.dailyLoss : null)}`}>
            {ops.account?.dailyLoss !== null && ops.account?.dailyLoss !== undefined
              ? `${fmtInr(ops.account.dailyLoss)} / ${fmtInr(ops.account.dailyLossLimit)}`
              : '—'}
          </span>
        </span>
        <span className="ps">
          <span className="ps-l">Net exposure</span>
          <span className="ps-v">{fmtInr(ops.exposure?.net, true)}</span>
        </span>
        <span className="ps">
          <span className="ps-l">Consent</span>
          <span className="ps-v">
            {ops.account?.consentOk === true ? 'OK' : ops.account?.consentOk === false ? 'MISSING' : '—'}
          </span>
        </span>
      </div>

      {ops.account?.unavailable ? (
        <p className="sg-err">
          Account snapshot unavailable ({ops.account.unavailableReason ?? 'no store'}) — fail-closed:
          no capital numbers are shown rather than invented ones.
        </p>
      ) : null}

      <section className="tabbar w-fit" role="tablist" aria-label="Trade ops sections">
        {(['orders', 'positions', 'sizing', 'audit', 'health'] as ModuleTab[]).map((option) => (
          <button
            key={option}
            type="button"
            role="tab"
            aria-selected={tab === option}
            className={`tab ${tab === option ? 'is-active' : ''}`}
            onClick={() => setTab(option)}
          >
            {option}
          </button>
        ))}
      </section>

      {ops.error ? <p className="sg-err">{ops.error}</p> : null}

      {tab === 'orders' ? (
        <>
          <p className="sg-note">
            Working orders reconcile against the broker on read. Cancelling a working order releases its
            reserved capital; partially filled orders need an explicit position exit instead.
          </p>
          <OrdersPanel
            orders={ops.orders}
            mode={ops.mode}
            loading={ops.loading}
            busyId={busyId}
            onCancel={setPendingCancel}
            onReconcile={setPendingReconcile}
          />
        </>
      ) : null}

      {tab === 'positions' ? (
        <>
          <p className="sg-note">
            Exits route through the exit engine as emergency orders against the {ops.mode} broker account.
            Exit-all triggers every open position and cannot be undone.
          </p>
          <PositionsPanel
            positions={ops.positions}
            mode={ops.mode}
            loading={ops.loading}
            busyId={busyId}
            onExit={setPendingExit}
            onExitAll={() => setExitAllOpen(true)}
          />
        </>
      ) : null}

      {tab === 'sizing' ? (
        <SizingPanel defaultAvailable={ops.account?.available ?? null} previewSizing={ops.previewSizing} />
      ) : null}

      {tab === 'audit' ? <AuditPanel rows={ops.audit} loading={ops.loading} /> : null}

      {tab === 'health' ? (
        <HealthPanel
          consent={ops.consent}
          capital={ops.capital}
          strategies={ops.strategies}
          aiModels={ops.aiModels}
          drift={ops.drift}
          slo={ops.slo}
          brokerCaps={ops.brokerCaps}
          greeks={ops.greeks}
          killSwitch={ops.killSwitch}
        />
      ) : null}

      <ConfirmDialog
        open={pendingCancel !== null}
        onOpenChange={(open) => {
          if (!open) setPendingCancel(null);
        }}
        tone="primary"
        confirmLabel="Cancel order"
        busy={busyId !== null}
        title={`Cancel ${pendingCancel?.symbol ?? 'order'} on ${ops.mode}?`}
        description="The working order is cancelled with the broker and its reserved capital is released."
        intentRows={
          pendingCancel
            ? [
                { label: 'Mode', value: ops.mode },
                { label: 'Contract', value: pendingCancel.symbol },
                { label: 'Side', value: pendingCancel.side ?? '—' },
                { label: 'Quantity', value: String(pendingCancel.quantity ?? '—') },
                { label: 'Status', value: pendingCancel.status },
              ]
            : undefined
        }
        onConfirm={handleCancel}
      />

      <ConfirmDialog
        open={pendingReconcile !== null}
        onOpenChange={(open) => {
          if (!open) setPendingReconcile(null);
        }}
        tone="primary"
        confirmLabel="Reconcile order"
        busy={busyId !== null}
        title={`Reconcile ${pendingReconcile?.symbol ?? 'order'} on ${ops.mode}?`}
        description="Polls the broker for the latest order state and updates the internal record. Read-only against positions."
        intentRows={
          pendingReconcile
            ? [
                { label: 'Mode', value: ops.mode },
                { label: 'Contract', value: pendingReconcile.symbol },
                { label: 'Quantity', value: String(pendingReconcile.quantity ?? '—') },
                { label: 'Status', value: pendingReconcile.status },
              ]
            : undefined
        }
        onConfirm={handleReconcile}
      />

      <ConfirmDialog
        open={pendingExit !== null}
        onOpenChange={(open) => {
          if (!open) setPendingExit(null);
        }}
        tone="danger"
        confirmLabel="Exit position"
        busy={busyId !== null}
        title={`Exit ${pendingExit?.symbol ?? 'position'} on ${ops.mode}?`}
        description="Triggers an emergency exit order against the broker account. This cannot be undone."
        intentRows={
          pendingExit
            ? [
                { label: 'Mode', value: ops.mode },
                { label: 'Contract', value: pendingExit.symbol },
                { label: 'Side', value: pendingExit.side ?? '—' },
                { label: 'Quantity', value: String(pendingExit.quantity ?? '—') },
                { label: 'Avg entry', value: safeNum(pendingExit.avgEntry) },
                { label: 'LTP', value: safeNum(pendingExit.currentPrice) },
              ]
            : undefined
        }
        onConfirm={handleExit}
      />

      <ConfirmDialog
        open={exitAllOpen}
        onOpenChange={setExitAllOpen}
        tone="danger"
        confirmLabel="Exit all positions"
        requireTypedConfirmation="EXIT"
        busy={busyId !== null}
        title={`Exit every open position on ${ops.mode}?`}
        description="Triggers emergency exit on all open positions. Realized P&L is booked at the fill. This cannot be undone."
        intentRows={[
          { label: 'Mode', value: ops.mode },
          { label: 'Open positions', value: String(openPositions.length) },
        ]}
        onConfirm={handleExitAll}
      />
    </div>
  );
}
