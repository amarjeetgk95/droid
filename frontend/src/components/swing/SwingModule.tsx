'use client';

import { useCallback, useMemo, useState } from 'react';
import { Radar, RefreshCw } from 'lucide-react';
import type { SwingPositionDTO, SwingSetupDTO } from '@/lib/api/swing';
import { useInstrument } from '@/context/InstrumentContext';
import { useMarketSession } from '@/context/MarketSessionContext';
import { useSwingDesk } from '@/hooks/useSwingDesk';
import { fmtDateTimeMs } from '@/lib/signalsNormalize';
import { safeNum } from '@/lib/utils';
import {
  filterSwingSetups,
  type SwingDirectionFilter,
  type SwingHorizonFilter,
  type SwingSetupFilters,
} from '@/lib/swingDesk';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/toast';
import { SwingSetupsPanel } from './SwingSetupsPanel';
import { SwingPositionsPanel } from './SwingPositionsPanel';
import { SwingThesisModal } from './SwingThesisModal';

type ModuleTab = 'setups' | 'positions';

function regimeBadge(regime: string | null | undefined): { label: string; cls: string } {
  const r = String(regime ?? '').toUpperCase();
  if (!r) return { label: 'NO SCAN', cls: 'b-neut' };
  if (r.includes('UP') || r.includes('BULL')) return { label: r, cls: 'b-bull' };
  if (r.includes('DOWN') || r.includes('BEAR')) return { label: r, cls: 'b-bear' };
  return { label: r, cls: 'b-neut' };
}

export function SwingModule() {
  const { instrument } = useInstrument();
  const { isOpen } = useMarketSession();
  const { push } = useToast();
  const [tab, setTab] = useState<ModuleTab>('setups');
  const [horizon, setHorizon] = useState<SwingHorizonFilter>('ALL');
  const [direction, setDirection] = useState<SwingDirectionFilter>('ALL');
  const [scanning, setScanning] = useState(false);
  const [pendingEnter, setPendingEnter] = useState<SwingSetupDTO | null>(null);
  const [pendingExit, setPendingExit] = useState<SwingPositionDTO | null>(null);
  const [thesisSetup, setThesisSetup] = useState<SwingSetupDTO | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const desk = useSwingDesk({ safetyRefreshMs: isOpen ? 60_000 : null });

  const filters = useMemo<SwingSetupFilters>(
    () => ({
      underlying: instrument,
      horizon,
      direction,
      state: 'ALL',
      minScore: null,
    }),
    [instrument, horizon, direction],
  );

  const visibleSetups = useMemo(
    () => filterSwingSetups(desk.setups, filters),
    [desk.setups, filters],
  );

  const regime = useMemo(() => regimeBadge(desk.regime?.regime), [desk.regime?.regime]);

  const handleScan = useCallback(async () => {
    setScanning(true);
    try {
      const result = await desk.runScan();
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setScanning(false);
    }
  }, [desk, push]);

  const handleEnter = useCallback(async () => {
    if (!pendingEnter) return;
    setBusyId(pendingEnter.setup_id);
    try {
      const result = await desk.enterPosition(pendingEnter.setup_id);
      push(result.ok ? 'success' : 'error', result.message);
      if (result.ok) setTab('positions');
    } finally {
      setBusyId(null);
      setPendingEnter(null);
    }
  }, [desk, pendingEnter, push]);

  const handleExit = useCallback(async () => {
    if (!pendingExit) return;
    setBusyId(pendingExit.position_id);
    try {
      const result = await desk.exitPosition(pendingExit.position_id);
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setBusyId(null);
      setPendingExit(null);
    }
  }, [desk, pendingExit, push]);

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar">
        <div className="ds-title">
          <h2>Swing Options Desk</h2>
          <span className={`badge ${regime.cls}`} title="Market regime from the latest swing scan">
            {regime.label}
          </span>
          <span className="card-meta">{instrument}</span>
        </div>
        <div className="stat-chips">
          <span className="stat-chip">
            setups <b>{visibleSetups.length}</b>
          </span>
          <span className="stat-chip">
            open <b>{desk.openPositions.length}</b>
          </span>
          <span className="stat-chip" title="Premium at risk across the open swing book">
            at risk <b>{safeNum(desk.portfolioRisk?.premium_at_risk, '—', 0)}</b>
          </span>
          <span className="stat-chip" title="Portfolio heat vs the configured ceiling">
            heat <b>{safeNum(desk.portfolioRisk?.portfolio_heat_pct, '—', 1)}%</b>
          </span>
          <span className="stat-chip" title="IV regime and percentile from the latest scan">
            IV <b>{desk.regime?.iv_regime ?? '—'}</b> p{Math.round(desk.regime?.iv_percentile ?? 0)}
          </span>
          <span className="stat-chip">
            scan <b>{fmtDateTimeMs(desk.scanTimestampMs)}</b>
          </span>
          <span className="stat-chip">{isOpen ? 'market open' : 'market closed'}</span>
        </div>
        <div className="ds-filters">
          <span className="seg" title="Horizon filter">
            {(['ALL', 'POSITIONAL', 'INTRADAY'] as SwingHorizonFilter[]).map((option) => (
              <button
                key={option}
                type="button"
                className="seg-btn"
                data-active={horizon === option}
                onClick={() => setHorizon(option)}
              >
                {option}
              </button>
            ))}
          </span>
          <span className="seg" title="Direction filter">
            {(['ALL', 'BULLISH', 'BEARISH'] as SwingDirectionFilter[]).map((option) => (
              <button
                key={option}
                type="button"
                className="seg-btn"
                data-active={direction === option}
                onClick={() => setDirection(option)}
              >
                {option}
              </button>
            ))}
          </span>
          <button
            type="button"
            className="btn btn-ic"
            disabled={scanning}
            title="Run an on-demand universe scan (heavy: candles + option chains)"
            onClick={() => void handleScan()}
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
            <RefreshCw size={13} className={desk.refreshing ? 'animate-spin' : undefined} />
            {desk.refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      {desk.error ? <p className="sg-err">{desk.error}</p> : null}

      <p className="sg-note">
        The backend swing worker scans the NIFTY / BANKNIFTY / SENSEX option universe after the
        close (15:35 IST) and the risk gate revalidates every entry server-side — position sizing
        defaults to the 1% risk budget. Use Scan now to force a fresh pass.
        {!isOpen ? ' Market closed: entries and exits fill at the last scanner marks.' : ''}
      </p>

      <section className="tabbar w-fit" role="tablist" aria-label="Swing module sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'setups'}
          className={`tab ${tab === 'setups' ? 'is-active' : ''}`}
          onClick={() => setTab('setups')}
        >
          Setups <span className="n">{visibleSetups.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'positions'}
          className={`tab ${tab === 'positions' ? 'is-active' : ''}`}
          onClick={() => setTab('positions')}
        >
          Positions &amp; Risk <span className="n">{desk.openPositions.length}</span>
        </button>
      </section>

      {desk.loading ? (
        <div className="panel">
          <p className="sg-empty">Loading swing desk…</p>
        </div>
      ) : tab === 'setups' ? (
        <SwingSetupsPanel
          setups={visibleSetups}
          busySetupId={busyId}
          onEnter={setPendingEnter}
          onThesis={setThesisSetup}
        />
      ) : (
        <SwingPositionsPanel
          openPositions={desk.openPositions}
          closedPositions={desk.closedPositions}
          portfolioRisk={desk.portfolioRisk}
          busyPositionId={busyId}
          onExit={setPendingExit}
        />
      )}

      <SwingThesisModal
        setup={thesisSetup}
        onClose={() => setThesisSetup(null)}
        fetchThesis={desk.fetchThesis}
      />

      <ConfirmDialog
        open={pendingEnter !== null}
        onOpenChange={(open) => {
          if (!open) setPendingEnter(null);
        }}
        tone="primary"
        confirmLabel="Enter position"
        busy={busyId !== null}
        title={`Enter ${pendingEnter?.contract_symbol ?? 'setup'} into the swing book?`}
        description="Paper position. Lots default to the 1% risk budget; the backend revalidates validity, portfolio heat and fill premium before accepting."
        intentRows={
          pendingEnter
            ? [
                { label: 'Direction', value: `${pendingEnter.direction} (${pendingEnter.option_type})` },
                { label: 'Strategy', value: pendingEnter.strategy },
                { label: 'Entry premium', value: safeNum(pendingEnter.entry_premium) },
                { label: 'Stop premium', value: safeNum(pendingEnter.stop_premium) },
                { label: 'Targets', value: `${safeNum(pendingEnter.target_premium_1)} / ${safeNum(pendingEnter.target_premium_2)}` },
                { label: 'Risk / lot', value: `₹${safeNum(pendingEnter.premium_risk_per_lot, '—', 0)}` },
                { label: 'DTE', value: String(pendingEnter.dte) },
                { label: 'Score', value: safeNum(pendingEnter.score?.total, '—', 0) },
              ]
            : undefined
        }
        onConfirm={handleEnter}
      />

      <ConfirmDialog
        open={pendingExit !== null}
        onOpenChange={(open) => {
          if (!open) setPendingExit(null);
        }}
        tone="danger"
        confirmLabel="Exit position"
        busy={busyId !== null}
        title={`Exit ${pendingExit?.contract_symbol ?? 'position'}?`}
        description="Closes at the last scanner mark (stale while the market is closed). Realized P&L and the R multiple are recorded in the swing ledger."
        intentRows={
          pendingExit
            ? [
                { label: 'Lots', value: `${pendingExit.num_lots} × ${pendingExit.lot_size}` },
                { label: 'Entry', value: safeNum(pendingExit.entry_premium) },
                { label: 'Mark', value: safeNum(pendingExit.current_premium) },
                { label: 'Stop', value: safeNum(pendingExit.current_stop_premium) },
                { label: 'Unrealized', value: `₹${safeNum(pendingExit.unrealized_pnl, '—', 0)}` },
                { label: 'R', value: `${safeNum(pendingExit.r_multiple)}R` },
              ]
            : undefined
        }
        onConfirm={handleExit}
      />
    </div>
  );
}
