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
  type ActiveRow,
  type DeskScope,
} from '@/lib/signalsNormalize';
import { SIGNAL_STAGES, matchPosition, stageOf, type SignalStageId } from '@/lib/signalStages';
import { safeNum } from '@/lib/utils';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/toast';
import { SignalGeneratorPanel } from './SignalGeneratorPanel';
import { SignalChecklistCard } from './SignalChecklistCard';
import { SignalDetailDrawer } from './SignalDetailDrawer';
import { LedgerPanel } from '@/components/ledger/LedgerPanel';

type ModuleTab = 'pipeline' | 'generate' | 'ledger';
type DeskFilter = DeskScope | 'ALL';
type ViewFilter = 'ALL' | 'LIVE' | 'CLOSED';

const STAGE_WEIGHT: Record<SignalStageId, number> = {
  EXECUTED: 0,
  TRIGGERED: 1,
  ARMED: 2,
  DETECTED: 3,
  CLOSED: 4,
};

export function SignalsModule() {
  const { instrument } = useInstrument();
  const { isOpen } = useMarketSession();
  const { push } = useToast();
  const now = useNow(1000);
  const [tab, setTab] = useState<ModuleTab>('pipeline');
  const [deskFilter, setDeskFilter] = useState<DeskFilter>('ALL');
  const [viewFilter, setViewFilter] = useState<ViewFilter>('ALL');
  const [pendingExecute, setPendingExecute] = useState<ActiveRow | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ActiveRow | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [busySignalId, setBusySignalId] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);

  const desk = useSignalDesk(
    { instrument, desk: deskFilter },
    { safetyRefreshMs: isOpen ? 15_000 : null, includeClosed: true },
  );
  const ledger = usePaperLedger({ safetyRefreshMs: isOpen ? 30_000 : null });

  const marketClosed = !isOpen;

  const stageCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const stage of SIGNAL_STAGES) counts[stage] = 0;
    for (const row of desk.rows) counts[stageOf(row.state)] += 1;
    return counts;
  }, [desk.rows]);

  const executableCount = useMemo(
    () => desk.rows.filter((row) => executionEligibility(row.state, marketClosed).eligible).length,
    [desk.rows, marketClosed],
  );

  const visibleRows = useMemo(() => {
    const filtered = desk.rows.filter((row) => {
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
  }, [desk.rows, viewFilter]);

  const workerRunning = desk.worker.running;
  const workerClass =
    workerRunning === true ? 'b-bull' : workerRunning === false ? 'b-warn' : 'b-neut';
  const workerLabel =
    workerRunning === true
      ? 'AUTO SCANNER LIVE'
      : workerRunning === false
        ? 'WORKER OFFLINE'
        : 'WORKER UNKNOWN';

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

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar">
        <div className="ds-title">
          <h2>Signal Automation</h2>
          <span className={`badge ${workerClass}`} title="Backend Automated Signal Worker (scanner + risk loops)">
            {workerLabel}
          </span>
          <span className="card-meta">{instrument}</span>
        </div>
        <div className="stat-chips">
          {SIGNAL_STAGES.map((stage) => (
            <span key={stage} className="stat-chip" title={`Pipeline stage: ${stage}`}>
              {stage.toLowerCase()} <b>{stageCounts[stage] ?? 0}</b>
            </span>
          ))}
          <span className="stat-chip">
            executable <b>{executableCount}</b>
          </span>
          <span className="stat-chip" title="Backend cadence: risk loop 3s, scalp scan 10s, intraday scan 30s">
            cadence <b>3s / 10s / 30s</b>
          </span>
          <span className="stat-chip">
            {marketClosed ? 'market closed' : 'market open'}
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
          <span className="seg">
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
          aria-selected={tab === 'pipeline'}
          className={`tab ${tab === 'pipeline' ? 'is-active' : ''}`}
          onClick={() => setTab('pipeline')}
        >
          Pipeline <span className="n">{desk.rows.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'generate'}
          className={`tab ${tab === 'generate' ? 'is-active' : ''}`}
          onClick={() => setTab('generate')}
        >
          Generate
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
      </section>

      {desk.error ? <p className="sg-err">{desk.error}</p> : null}

      {tab === 'pipeline' ? (
        <>
          <p className="sg-note">
            The backend worker scans automatically — SCALP every 10s and INTRADAY every 30s — and the risk loop
            (3s) arms triggers, confirms entries and auto-executes paper fills. Each signal card ticks its own
            stage checklist with the transition timestamp; use Scan now to force a pass.
          </p>
          {visibleRows.length === 0 ? (
            <div className="panel">
              <p className="sg-empty">
                {desk.loading
                  ? 'Loading signals…'
                  : viewFilter === 'LIVE'
                    ? 'No live signals right now — the scanner will populate them on the next candle close while the market is open.'
                    : 'No signals recorded for this filter yet. The automated worker registers them as setups confirm.'}
              </p>
            </div>
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

      {tab === 'generate' ? (
        <>
          <p className="sg-note">
            Manual generation registers the same FSM signal the scanner produces — the automated trigger and
            execution path applies from there.
          </p>
          <SignalGeneratorPanel desk={desk} />
        </>
      ) : null}

      {tab === 'ledger' ? <LedgerPanel ledger={ledger} marketClosed={marketClosed} /> : null}

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
    </div>
  );
}
