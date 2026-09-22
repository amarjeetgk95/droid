'use client';

import { useCallback, useMemo, useState } from 'react';
import { Radar } from 'lucide-react';
import { useInstrument } from '@/context/InstrumentContext';
import { useMarketSession } from '@/context/MarketSessionContext';
import { useSignalDesk } from '@/hooks/useSignalDesk';
import { usePaperLedger } from '@/hooks/usePaperLedger';
import { useNow } from '@/hooks/useNow';
import {
  executionEligibility,
  fmtDist,
  isTodayIST,
  startOfTodayISTMs,
  type ActiveRow,
  type DeskScope,
} from '@/lib/signalsNormalize';
import { SIGNAL_STAGES, matchPosition, stageOf, type SignalStageId } from '@/lib/signalStages';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { safeNum } from '@/lib/utils';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/toast';

import { SignalChecklistCard } from './SignalChecklistCard';
import { SignalDetailDrawer } from './SignalDetailDrawer';
import { LedgerPanel } from '@/components/ledger/LedgerPanel';
import { VortexSnapHUD } from './VortexSnapHUD';
import { SignalFunnelDiagnostics } from './SignalFunnelDiagnostics';

type ModuleTab = 'today' | 'history' | 'ledger' | 'vortex' | 'funnel';
type DeskFilter = DeskScope | 'ALL';
type ViewFilter = 'ALL' | 'LIVE' | 'CLOSED';

const STAGE_WEIGHT: Record<SignalStageId, number> = {
  EXECUTED: 0,
  TRIGGERED: 1,
  ARMED: 2,
  DETECTED: 3,
  CLOSED: 4,
};

/** Compact age text for the scanner badge ("12s ago", "3m ago"). */
function formatAgeFromMs(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m ago`;
}

export function SignalsModule() {
  const { instrument } = useInstrument();
  const { isOpen } = useMarketSession();
  const { push } = useToast();
  const now = useNow(1000);
  const [tab, setTab] = useState<ModuleTab>('today');
  const [deskFilter, setDeskFilter] = useState<DeskFilter>('ALL');
  const [viewFilter, setViewFilter] = useState<ViewFilter>('ALL');
  const [pendingExecute, setPendingExecute] = useState<ActiveRow | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ActiveRow | null>(null);
  const [confirmClearHistory, setConfirmClearHistory] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [busySignalId, setBusySignalId] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);

  const desk = useSignalDesk(
    { instrument, desk: deskFilter },
    { safetyRefreshMs: isOpen ? 15_000 : null, includeClosed: true },
  );
  const ledger = usePaperLedger({ safetyRefreshMs: isOpen ? 30_000 : null });

  const marketClosed = !isOpen;
  // `now` ticks every second via useNow; isTodayIST falls back to Date.now()
  // internally while it is still 0 on first paint (keeps render pure).
  const nowMs = now;

  // Main screen shows today's IST trading day only; older signals live
  // under the History tab so the operator always sees a fresh book.
  const { todayRows, historyRows } = useMemo(() => {
    const today: ActiveRow[] = [];
    const history: ActiveRow[] = [];
    for (const row of desk.rows) {
      if (isTodayIST(row.timeMs, nowMs)) today.push(row);
      else history.push(row);
    }
    return { todayRows: today, historyRows: history };
  }, [desk.rows, nowMs]);

  const stageCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const stage of SIGNAL_STAGES) counts[stage] = 0;
    for (const row of todayRows) counts[stageOf(row.state)] += 1;
    return counts;
  }, [todayRows]);

  const liveToday = useMemo(
    () => todayRows.filter((row) => stageOf(row.state) !== 'CLOSED').length,
    [todayRows],
  );

  const executableToday = useMemo(
    () => todayRows.filter((row) => executionEligibility(row.state, marketClosed).eligible).length,
    [todayRows, marketClosed],
  );

  const scopeRows = tab === 'history' ? historyRows : todayRows;

  const visibleRows = useMemo(() => {
    const filtered = scopeRows.filter((row) => {
      const stage = stageOf(row.state);
      if (viewFilter === 'LIVE') return stage !== 'CLOSED';
      if (viewFilter === 'CLOSED') return stage === 'CLOSED';
      return true;
    });
    return filtered.sort((a, b) => {
      const weight = STAGE_WEIGHT[stageOf(a.state)] - STAGE_WEIGHT[stageOf(b.state)];
      if (weight !== 0) return weight;
      return (b.timeMs ?? 0) - (a.timeMs ?? 0);
    });
  }, [scopeRows, viewFilter]);

  const workerRunning = desk.worker.running;
  // Freshness comes from the desk hook (ageMs/stale); the badge never claims
  // LIVE when the last payload is stale or its age is unknown.
  const scanAgeSuffix = ` · last scan ${
    desk.ageMs !== null ? formatAgeFromMs(desk.ageMs) : 'age unknown'
  }`;
  const scannerStale = desk.stale;
  const workerClass =
    workerRunning === true && !scannerStale
      ? 'b-bull'
      : workerRunning === false || (workerRunning === true && scannerStale)
        ? 'b-warn'
        : 'b-neut';
  const workerLabel =
    workerRunning === true
      ? scannerStale
        ? `SCANNER STALE${scanAgeSuffix}`
        : `AUTO SCANNER LIVE${scanAgeSuffix}`
      : workerRunning === false
        ? `WORKER OFFLINE${scanAgeSuffix}`
        : `WORKER UNKNOWN${scanAgeSuffix}`;

  const handleScanNow = useCallback(async () => {
    setScanning(true);
    try {
      const result = await desk.runScan(deskFilter === 'ALL' ? 'ALL' : deskFilter);
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setScanning(false);
    }
  }, [desk, deskFilter, push]);

  const handleExecute = useCallback(async () => {
    if (!pendingExecute) return;
    setBusySignalId(pendingExecute.id);
    try {
      const result = await desk.executePaper(pendingExecute.id, { riskPercent: 2 });
      push(result.ok ? 'success' : 'error', result.message);
      if (result.ok) setTab('ledger');
    } finally {
      setBusySignalId(null);
      setPendingExecute(null);
    }
  }, [desk, pendingExecute, push]);

  const handleDelete = useCallback(async () => {
    if (!pendingDelete) return;
    setBusySignalId(pendingDelete.id);
    try {
      const result = await desk.removeSignal(pendingDelete.id);
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setBusySignalId(null);
      setPendingDelete(null);
    }
  }, [desk, pendingDelete, push]);

  const handleClearHistory = useCallback(async () => {
    setClearingHistory(true);
    try {
      const beforeMs = startOfTodayISTMs(Date.now());
      const result = await api.bulkDeleteSignals(
        beforeMs !== null ? { before_ms: beforeMs } : { delete_all: false },
      );
      push('success', result.message || `Cleared ${result.deleted_count} old signal(s).`);
      setConfirmClearHistory(false);
      await desk.refresh();
    } catch (err) {
      push('error', errorMessage(err, 'Clear history failed'));
    } finally {
      setClearingHistory(false);
    }
  }, [desk, push]);

  const inHistory = tab === 'history';
  const emptyMessage = desk.loading
    ? 'Loading signals…'
    : inHistory
      ? 'No older signals — everything on the books is from today.'
      : viewFilter === 'LIVE'
        ? 'No live signals today — the scanner will populate them on the next candle close while the market is open.'
        : 'No signals today yet. The automated worker registers them as setups confirm.';

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar">
        <div className="ds-title">
          <h2>Signals · Today</h2>
          <span
            className={`badge ${workerClass}`}
            title={
              workerRunning === true
                ? scannerStale
                  ? 'Signal worker is running but its last payload is outside the freshness window — do not treat as live'
                  : 'Backend Automated Signal Worker (scanner + risk loops) — last payload fresh'
                : 'Backend Automated Signal Worker (scanner + risk loops)'
            }
          >
            {workerLabel}
          </span>
          <span className="card-meta">{instrument}</span>
          <span className="card-meta" title={marketClosed ? 'Market closed — paper execution is disabled' : 'Market open'}>
            {marketClosed ? 'market closed' : 'market open'}
          </span>
        </div>
        <div className="stat-chips" title="Counts scoped to today's IST trading day">
          <span className="stat-chip" title="Signals created today (IST)">
            today <b>{todayRows.length}</b>
          </span>
          <span className="stat-chip" title="Today's signals still live (not closed)">
            live <b>{liveToday}</b>
          </span>
          <span className="stat-chip" title="Today's closed signals">
            closed <b>{stageCounts.CLOSED ?? 0}</b>
          </span>
          <span className="stat-chip" title="Today's signals eligible for paper execution">
            executable <b>{executableToday}</b>
          </span>
          <span className="stat-chip" title="Signals from previous days — see the History tab">
            history <b>{historyRows.length}</b>
          </span>
        </div>
        <div className="ds-filters">
          <span className="seg" title="View filter">
            {(['ALL', 'LIVE', 'CLOSED'] as ViewFilter[]).map((option) => (
              <button
                key={option}
                type="button"
                className="seg-btn"
                data-active={viewFilter === option}
                onClick={() => setViewFilter(option)}
              >
                {option}
              </button>
            ))}
          </span>
          <span className="seg" title="Desk filter">
            {(['ALL', 'INTRADAY', 'SCALP'] as DeskFilter[]).map((option) => (
              <button
                key={option}
                type="button"
                className="seg-btn"
                data-active={deskFilter === option}
                onClick={() => setDeskFilter(option)}
              >
                {option}
              </button>
            ))}
          </span>
          <button
            type="button"
            className="btn btn-ic"
            disabled={scanning}
            title="Force an immediate backend scan pass on the selected desk"
            onClick={() => void handleScanNow()}
          >
            <Radar size={13} />
            {scanning ? 'Scanning…' : 'Scan now'}
          </button>
          <button
            type="button"
            className="btn"
            disabled={desk.refreshing}
            onClick={() => void desk.refresh()}
          >
            {desk.refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      <section className="tabbar w-fit" role="tablist" aria-label="Signals module sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'today'}
          className={`tab ${tab === 'today' ? 'is-active' : ''}`}
          onClick={() => setTab('today')}
        >
          Today <span className="n">{todayRows.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'history'}
          className={`tab ${tab === 'history' ? 'is-active' : ''}`}
          onClick={() => setTab('history')}
        >
          History <span className="n">{historyRows.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'ledger'}
          className={`tab ${tab === 'ledger' ? 'is-active' : ''}`}
          onClick={() => setTab('ledger')}
        >
          Ledger <span className="n">{ledger.totals.openCount}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'vortex'}
          className={`tab ${tab === 'vortex' ? 'is-active' : ''}`}
          onClick={() => setTab('vortex')}
        >
          VORTEX-SNAP HUD
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'funnel'}
          className={`tab ${tab === 'funnel' ? 'is-active' : ''}`}
          onClick={() => setTab('funnel')}
        >
          Funnel Diagnostics
        </button>
      </section>

      {desk.error ? <p className="sg-err">{desk.error}</p> : null}

      {tab === 'today' || tab === 'history' ? (
        <>
          <p className="sg-note">
            {inHistory
              ? 'Older signals (before today IST) — kept for review. They never mix with the live book.'
              : 'Today\u2019s book only — SCALP scans every 10s, INTRADAY every 30s, risk loop every 3s. Use Scan now to force a pass.'}
          </p>
          {inHistory && historyRows.length > 0 ? (
            <div className="flex items-center justify-between gap-2">
              <p className="sg-note">
                Showing {visibleRows.length} of {historyRows.length} older signal(s).
              </p>
              <button
                type="button"
                className="btn"
                disabled={clearingHistory}
                title="Delete all signals created before today (IST)"
                onClick={() => setConfirmClearHistory(true)}
              >
                {clearingHistory ? 'Clearing…' : 'Clear history'}
              </button>
            </div>
          ) : null}
          {visibleRows.length === 0 ? (
            tab === 'today' ? (
              <div className="flex flex-col gap-3">
                <div className="rounded-lg border border-warn-line bg-warn-wash p-3 text-center">
                  <div className="text-xs font-bold uppercase tracking-wider text-warn-ink">
                    No Active Signals On The Books Today
                  </div>
                  <p className="mt-1 text-xs text-ink-2">
                    {emptyMessage} The live diagnostic engine below outlines all scanned opportunities and exactly where setups were filtered.
                  </p>
                </div>
                <SignalFunnelDiagnostics
                  initialInstrument={instrument}
                  onRefreshParent={() => void desk.refresh()}
                  standalone
                />
              </div>
            ) : (
              <div className="panel">
                <p className="sg-empty">{emptyMessage}</p>
              </div>
            )
          ) : (
            <div className="flex flex-col gap-2">
              {visibleRows.map((row) => (
                <SignalChecklistCard
                  key={row.id}
                  row={row}
                  now={now}
                  position={matchPosition(row, ledger.positions)}
                  marketClosed={marketClosed}
                  busy={busySignalId === row.id}
                  onOpen={(next) => setDetailId(next.id)}
                  onExecute={setPendingExecute}
                  onDelete={setPendingDelete}
                />
              ))}
            </div>
          )}
        </>
      ) : null}


      {tab === 'ledger' ? <LedgerPanel ledger={ledger} marketClosed={marketClosed} /> : null}
      {tab === 'vortex' ? <VortexSnapHUD initialSymbol={instrument} /> : null}
      {tab === 'funnel' ? (
        <SignalFunnelDiagnostics
          initialInstrument={instrument}
          onRefreshParent={() => void desk.refresh()}
        />
      ) : null}

      <SignalDetailDrawer signalId={detailId} onClose={() => setDetailId(null)} />

      <ConfirmDialog
        open={pendingExecute !== null}
        onOpenChange={(open) => {
          if (!open) setPendingExecute(null);
        }}
        tone="primary"
        confirmLabel="Execute paper order"
        busy={busySignalId !== null}
        title={`Execute ${pendingExecute?.symbol ?? 'signal'} as a paper order?`}
        description="Sized from the paper wallet at 2% risk. Fills against the live option chain."
        intentRows={
          pendingExecute
            ? [
                { label: 'Strategy', value: pendingExecute.strategy },
                { label: 'State', value: pendingExecute.state },
                { label: 'Trigger', value: safeNum(pendingExecute.triggerLevel) },
                { label: 'Stop loss', value: safeNum(pendingExecute.sl) },
                { label: 'Distance', value: fmtDist(pendingExecute.triggerLevel, pendingExecute.spot) },
              ]
            : undefined
        }
        onConfirm={handleExecute}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        tone="danger"
        confirmLabel="Delete signal"
        busy={busySignalId !== null}
        title={`Delete ${pendingDelete?.symbol ?? 'signal'} and square off its paper position?`}
        description="The signal is removed from the FSM and audit ledger. Any open paper position is squared off first."
        onConfirm={handleDelete}
      />

      <ConfirmDialog
        open={confirmClearHistory}
        onOpenChange={(open) => {
          if (!open) setConfirmClearHistory(false);
        }}
        tone="danger"
        confirmLabel="Clear history"
        busy={clearingHistory}
        title={`Delete ${historyRows.length} signal(s) from before today?`}
        description="Only pre-today signals are removed. Today's book is untouched. This cannot be undone."
        onConfirm={handleClearHistory}
      />
    </div>
  );
}
