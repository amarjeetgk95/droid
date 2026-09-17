'use client';

import { useState, useMemo } from 'react';
import {
  TrendingUp,
  Shield,
  RefreshCw,
  SlidersHorizontal,
  Layers,
  AlertCircle,
  Briefcase,
  PieChart,
  Zap,
  X,
} from 'lucide-react';
import { useSwingData } from './useSwingData';
import { SwingSetupCard } from './SwingSetupCard';
import { SwingPositionsTable } from './SwingPositionsTable';
import { TelemetryStrip, TelemetryItem, fmtINR, fmtNum } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';

export function SwingDesk() {
  const [activeTab, setActiveTab] = useState<'setups' | 'positions' | 'sectors'>('setups');
  const [selectedHorizon, setSelectedHorizon] = useState<'ALL' | 'POSITIONAL' | 'INTRADAY'>('ALL');
  const [selectedStrategy, setSelectedStrategy] = useState<string>('ALL');
  const [selectedUnderlying, setSelectedUnderlying] = useState<string>('ALL');
  const [selectedDirection, setSelectedDirection] = useState<string>('ALL');
  const [minScore, setMinScore] = useState<number>(50);

  const filters = useMemo(() => {
    return {
      horizon: selectedHorizon !== 'ALL' ? selectedHorizon : undefined,
      strategy: selectedStrategy !== 'ALL' ? selectedStrategy : undefined,
      underlying: selectedUnderlying !== 'ALL' ? selectedUnderlying : undefined,
      direction: selectedDirection !== 'ALL' ? selectedDirection : undefined,
      min_score: minScore > 0 ? minScore : undefined,
    };
  }, [selectedHorizon, selectedStrategy, selectedUnderlying, selectedDirection, minScore]);

  const {
    loading,
    refreshing,
    scanning,
    stale,
    setups,
    openPositions,
    closedPositions,
    portfolioRisk,
    regime,
    sectors,
    error,
    setupsError,
    positionsError,
    regimeError,
    positionsUpdatedAt,
    regimeUpdatedAt,
    refresh,
    triggerScan,
    enterTrade,
    exitTrade,
    dismissError,
  } = useSwingData(filters);

  const scanHorizon = selectedHorizon !== 'ALL' ? selectedHorizon : undefined;
  const actionableSetups = setups.filter(
    (s) => s.signal_state === 'READY' || s.signal_state === 'TRIGGERED',
  ).length;

  // Never claim LIVE while a section's last fetch failed: a scan failure means
  // the scan snapshot is old (STALE), a data failure means the feed is down.
  const freshnessState = error
    ? error.kind === 'scan'
      ? 'STALE'
      : 'DOWN'
    : stale
      ? 'STALE'
      : undefined;

  const getRegimeBadge = (r: string) => {
    switch (r) {
      case 'BULL':
        return <span className="chip chip--up">Bull regime</span>;
      case 'DISTRIBUTION':
        return <span className="chip chip--warn">Distribution · caution</span>;
      case 'BEAR':
        return <span className="chip chip--down">Bear · calls restricted</span>;
      case 'HIGH_VOLATILITY':
        // A caution state, so it shares the amber family with DISTRIBUTION.
        // The label carries the distinction; a fifth hue would not.
        return <span className="chip chip--warn">High volatility</span>;
      default:
        return <span className="chip chip--neut">Neutral regime</span>;
    }
  };

  const returnToneClass = (v: unknown) => {
    const n = typeof v === 'number' && Number.isFinite(v) ? v : null;
    if (n === null || n === 0) return 'text-muted-foreground';
    return n > 0 ? 'text-up' : 'text-down';
  };

  return (
    <div className="space-y-3 pb-8">
      {/* Top Header / Telemetry Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-3 rounded-md border border-border bg-card shadow-xs">
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-[15px] font-semibold tracking-normal text-foreground flex items-center gap-1.5">
              <TrendingUp className="w-4 h-4 text-primary" />
              Index Options Swing Desk
            </h1>
            {regime && getRegimeBadge(regime.regime)}
            {regime && (
              <span className="chip chip--info num">
                IV rank{' '}
                {Number.isFinite(regime.iv_percentile)
                  ? `${fmtNum(regime.iv_percentile, 0)}%`
                  : '—'}{' '}
                · {regime.iv_regime ? regime.iv_regime : '—'}
              </span>
            )}
            <FreshnessClock
              state={freshnessState}
              lastAt={regimeUpdatedAt}
              fetching={loading || refreshing || scanning}
              sourceLabel="scan"
              note={scanning ? 'scanning' : undefined}
            />
          </div>
          <p className="text-[11.5px] text-muted-foreground">
            Long index options swing setups — Positional (2–20 days) &amp; Intraday (same-day 15M/ORB). Dual-layer stops with Greek risk limits.
          </p>
        </div>

        {/* Action button */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => void triggerScan(true, scanHorizon)}
            disabled={scanning}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 shadow-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
            <span>{scanning ? 'Scanning…' : 'Scan Index Options'}</span>
          </button>
        </div>
      </div>

      {/* Error / stale banner — dismissible, with retry */}
      {error && (
        <div
          role="alert"
          style={{ alignItems: 'flex-start' }}
          className={`notice gap-2.5 ${error.kind === 'scan' || !stale ? 'notice--down' : 'notice--warn'}`}
        >
          <AlertCircle
            className={`w-4 h-4 mt-0.5 shrink-0 ${error.kind === 'scan' || !stale ? 'text-down' : 'text-warn'}`}
          />
          <div className="flex-1 min-w-0">
            <div
              className={`text-[12px] font-semibold ${error.kind === 'scan' || !stale ? 'text-down' : 'text-warn'}`}
            >
              {error.kind === 'scan'
                ? 'Scan failed'
                : stale
                  ? 'Showing last known data'
                  : 'Swing data unavailable'}
            </div>
            <p className="text-[11px] text-ink-2 break-words">{error.message}</p>
          </div>
          <button
            type="button"
            onClick={error.kind === 'scan' ? () => void triggerScan(true, scanHorizon) : () => void refresh()}
            disabled={scanning || refreshing}
            className="btn shrink-0"
          >
            {error.kind === 'scan' ? 'Retry scan' : 'Retry'}
          </button>
          <button
            type="button"
            onClick={dismissError}
            aria-label="Dismiss error"
            className="p-1 rounded text-ink-3 hover:text-ink transition-colors shrink-0"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Telemetry Metric Ribbon */}
      <TelemetryStrip>
        <TelemetryItem
          label="Portfolio Heat"
          value={portfolioRisk ? `${fmtNum(portfolioRisk.portfolio_heat_pct, 1)}%` : '—'}
          sub={portfolioRisk ? `max ${fmtNum(portfolioRisk.max_heat_pct, 1)}%` : 'unavailable'}
          tone={
            portfolioRisk
              ? portfolioRisk.portfolio_heat_pct > 4.0
                ? 'bear'
                : 'bull'
              : undefined
          }
        />
        <TelemetryItem
          label="Net Greeks"
          value={portfolioRisk ? `Δ ${fmtNum(portfolioRisk.net_delta)}` : 'Δ —'}
          sub={
            portfolioRisk
              ? `Θ -${fmtINR(Math.abs(portfolioRisk.net_theta_day))}/d · Vega ${fmtINR(portfolioRisk.net_vega)}`
              : 'Θ — · Vega —'
          }
        />
        <TelemetryItem
          label="Active Positions"
          value={`${openPositions.length} / ${portfolioRisk ? portfolioRisk.max_positions_count : '—'}`}
          sub={portfolioRisk ? `Deployed ${fmtINR(portfolioRisk.total_premium_deployed)}` : 'Deployed —'}
        />
        <TelemetryItem
          label="Discovered Setups"
          value={`${setups.length}`}
          sub={`${actionableSetups} actionable`}
          tone={setups.length > 0 ? 'bull' : undefined}
        />
      </TelemetryStrip>

      {/* Main Tabs Navigation */}
      <div className="flex items-center justify-between border-b border-border">
        <div className="flex items-center gap-4">
          <button
            onClick={() => setActiveTab('setups')}
            className={`pb-3 text-sm font-semibold border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'setups'
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Layers className="w-4 h-4" />
            <span>Options Setups & Radar</span>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-muted text-muted-foreground">
              {setups.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab('positions')}
            className={`pb-3 text-sm font-semibold border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'positions'
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Briefcase className="w-4 h-4" />
            <span>Active Portfolio</span>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-muted text-muted-foreground">
              {openPositions.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab('sectors')}
            className={`pb-3 text-sm font-semibold border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'sectors'
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <PieChart className="w-4 h-4" />
            <span>Index Momentum & RS</span>
          </button>
        </div>
      </div>

      {/* Tab: Setups */}
      {activeTab === 'setups' && (
        <div className="space-y-4">
          {/* Horizon Segmented Switcher */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-2 rounded-md border border-border bg-card shadow-xs">
            <div className="flex items-center gap-1.5 p-1 bg-muted/60 rounded-lg">
              <button
                onClick={() => setSelectedHorizon('ALL')}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                  selectedHorizon === 'ALL'
                    ? 'bg-background text-foreground shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                All Horizons ({setups.length})
              </button>
              <button
                onClick={() => setSelectedHorizon('POSITIONAL')}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-all ${
                  selectedHorizon === 'POSITIONAL'
                    ? 'bg-accent/15 text-accent border border-accent/30 shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <span>Positional · 2–20D</span>
              </button>
              <button
                onClick={() => setSelectedHorizon('INTRADAY')}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-all ${
                  selectedHorizon === 'INTRADAY'
                    ? 'bg-warn/15 text-warn border border-warn/30 shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <Zap className="w-3.5 h-3.5 text-warn" />
                <span>Intraday · same-day</span>
              </button>
            </div>

            <div className="text-xs text-muted-foreground px-2">
              {selectedHorizon === 'INTRADAY' ? (
                <span className="text-warn font-medium">Intraday · 15m / ORB · square-off 15:15 IST</span>
              ) : selectedHorizon === 'POSITIONAL' ? (
                <span className="text-accent font-medium">Positional · multi-day trend and pullback · held 2–20 days</span>
              ) : (
                <span>Dual-horizon: positional multi-day and intraday momentum</span>
              )}
            </div>
          </div>

          {/* Intraday notice */}
          {selectedHorizon === 'INTRADAY' && (
            <div className="notice notice--warn flex-col md:flex-row items-start md:items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-warn/20 text-warn">
                  <Zap className="w-4 h-4" />
                </div>
                <div>
                  <div className="font-semibold text-warn flex items-center gap-2">
                    <span>Intraday desk · same-day active</span>
                    <span className="chip chip--warn num">15m bars</span>
                  </div>
                  <p className="text-muted-foreground text-[11px] mt-0.5">
                    Zero overnight gap risk. Fast break-even shift at +1.0R. Mandatory auto-exit triggered at 15:15:00 IST.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 font-mono text-[11px]">
                <span className="px-2 py-1 rounded bg-background border border-warn/30 text-warn">
                  Hard Square-Off: 15:15 IST
                </span>
                <span className="px-2 py-1 rounded bg-background border border-border text-muted-foreground">
                  Trail: 40% Peak @ 1.5R
                </span>
              </div>
            </div>
          )}

          {/* Filter Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg border border-border bg-muted/20 text-xs">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <SlidersHorizontal className="w-3.5 h-3.5" />
                <span>Underlying:</span>
                <select
                  value={selectedUnderlying}
                  onChange={(e) => setSelectedUnderlying(e.target.value)}
                  className="bg-background border border-border rounded-md px-2 py-1 text-foreground"
                >
                  <option value="ALL">All Underlyings</option>
                  <option value="NIFTY">NIFTY 50</option>
                  <option value="BANKNIFTY">BANK NIFTY</option>
                  <option value="SENSEX">SENSEX</option>
                </select>
              </div>

              <div className="flex items-center gap-1.5 text-muted-foreground">
                <span>Strategy:</span>
                <select
                  value={selectedStrategy}
                  onChange={(e) => setSelectedStrategy(e.target.value)}
                  className="bg-background border border-border rounded-md px-2 py-1 text-foreground"
                >
                  <option value="ALL">All Strategies</option>
                  <optgroup label="Positional Strategies (1D)">
                    <option value="TREND_BREAKOUT_CE">Trend Breakout CE</option>
                    <option value="TREND_BREAKOUT_PE">Trend Breakout PE</option>
                    <option value="PULLBACK_CE">20 EMA Pullback CE</option>
                    <option value="PULLBACK_PE">20 EMA Pullback PE</option>
                    <option value="STAGE2_CE">Stage 2 Breakout CE</option>
                    <option value="STAGE2_PE">Stage 4 Breakdown PE</option>
                    <option value="IV_DIRECTIONAL">IV Directional (Cheap Vol)</option>
                  </optgroup>
                  <optgroup label="Intraday strategies (15m)">
                    <option value="INTRADAY_PULLBACK_CE">Intraday pullback CE · 15m</option>
                    <option value="INTRADAY_PULLBACK_PE">Intraday pullback PE · 15m</option>
                    <option value="INTRADAY_ORB_CE">Intraday ORB CE · 30m</option>
                    <option value="INTRADAY_ORB_PE">Intraday ORB PE · 30m</option>
                  </optgroup>
                </select>
              </div>

              <div className="flex items-center gap-1.5 text-muted-foreground">
                <span>Direction:</span>
                <select
                  value={selectedDirection}
                  onChange={(e) => setSelectedDirection(e.target.value)}
                  className="bg-background border border-border rounded-md px-2 py-1 text-foreground"
                >
                  <option value="ALL">All Directions</option>
                  <option value="LONG_CALL">Long Call (CE)</option>
                  <option value="LONG_PUT">Long Put (PE)</option>
                </select>
              </div>

              <div className="flex items-center gap-1.5 text-muted-foreground">
                <span>Min Score:</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={5}
                  value={minScore}
                  onChange={(e) => setMinScore(Number(e.target.value))}
                  className="w-16 bg-background border border-border rounded-md px-2 py-1 text-foreground font-mono"
                />
              </div>
            </div>

            <span className="text-muted-foreground text-[11px]">
              Showing {setups.length} setups matching criteria
              {refreshing ? ' · updating…' : setupsError || stale ? ' · last known' : ''}
            </span>
          </div>

          {/* Setups Cards Grid */}
          {loading ? (
            <div className="flex items-center justify-center py-20 text-muted-foreground text-xs gap-2">
              <RefreshCw className="w-5 h-5 animate-spin text-primary" />
              <span>Scanning live index options chains...</span>
            </div>
          ) : setupsError && setups.length === 0 ? (
            <div
              role="alert"
              className="flex flex-col items-center justify-center py-8 text-muted-foreground text-xs rounded-md border border-dashed border-down/40 p-8 text-center gap-2"
            >
              <AlertCircle className="w-8 h-8 text-down opacity-70" />
              <span className="text-sm font-semibold text-foreground">Options setups unavailable.</span>
              <span>{setupsError}</span>
              <button
                onClick={() => void refresh()}
                disabled={refreshing}
                className="mt-3 px-3 py-1.5 text-xs font-medium rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors disabled:opacity-50"
              >
                {refreshing ? 'Retrying…' : 'Retry'}
              </button>
            </div>
          ) : setups.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground text-xs rounded-md border border-dashed border-border p-8 text-center gap-2">
              <Shield className="w-8 h-8 opacity-40" />
              <span className="text-sm font-semibold text-foreground">No options setups meet current filter criteria.</span>
              <span>
                Rule §2: Abstention is a first-class outcome. If no high-quality, IV-favorable setups pass the 4-layer validity gate, zero forced trades are generated.
              </span>
              <button
                onClick={() => void triggerScan(true, scanHorizon)}
                disabled={scanning}
                className="mt-3 px-3 py-1.5 text-xs font-medium rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors disabled:opacity-50"
              >
                {scanning ? 'Scanning…' : 'Scan Universe'}
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {setups.map((s) => (
                <SwingSetupCard
                  key={s.setup_id}
                  setup={s}
                  onEnterTrade={async (sid, premium) => {
                    await enterTrade(sid, premium);
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab: Positions */}
      {activeTab === 'positions' && (
        <SwingPositionsTable
          positions={openPositions}
          closedPositions={closedPositions}
          loading={loading}
          refreshing={refreshing}
          marksAt={positionsUpdatedAt}
          stale={Boolean(positionsError)}
          loadError={positionsError}
          onRetry={() => void refresh()}
          onExitPosition={async (pid, premium, reason) => {
            await exitTrade(pid, premium, reason);
          }}
        />
      )}

      {/* Tab: Sectors / Indices */}
      {activeTab === 'sectors' && (
        <div className="rounded-md border border-border bg-card text-card-foreground shadow-xs overflow-hidden">
          <div className="p-4 border-b border-border bg-muted/20 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-foreground">Index Relative Strength & Momentum (§10)</h3>
              <p className="text-xs text-muted-foreground">
                Tracks underlying index momentum relative to NIFTY benchmark to confirm directional options bias.
              </p>
            </div>
            <FreshnessClock
              state={regimeError ? (stale ? 'STALE' : 'DOWN') : stale ? 'STALE' : undefined}
              lastAt={regimeUpdatedAt}
              fetching={loading || refreshing || scanning}
              sourceLabel="scan"
            />
          </div>
          <div className="overflow-x-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12 text-muted-foreground text-xs gap-2">
                <RefreshCw className="w-5 h-5 animate-spin text-primary" />
                <span>Loading sector momentum...</span>
              </div>
            ) : regimeError && sectors.length === 0 ? (
              <div
                role="alert"
                className="flex flex-col items-center justify-center py-12 text-muted-foreground text-xs gap-2 text-center px-4"
              >
                <AlertCircle className="w-8 h-8 text-down opacity-70" />
                <span className="text-sm font-semibold text-foreground">Sector momentum unavailable.</span>
                <span>{regimeError}</span>
                <button
                  onClick={() => void refresh()}
                  disabled={refreshing}
                  className="mt-2 px-3 py-1.5 text-xs font-medium rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors disabled:opacity-50"
                >
                  {refreshing ? 'Retrying…' : 'Retry'}
                </button>
              </div>
            ) : sectors.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-xs gap-2">
                <PieChart className="w-8 h-8 opacity-40" />
                <span>No sector momentum snapshot yet — run a scan to populate it.</span>
              </div>
            ) : (
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-border/60 bg-muted/40 text-muted-foreground font-medium text-[11px]">
                    <th className="py-2.5 px-4">Underlying Index</th>
                    <th className="py-2.5 px-3">Momentum Status</th>
                    <th className="py-2.5 px-3">Relative Strength (vs NIFTY)</th>
                    <th className="py-2.5 px-3">20-Day Return</th>
                    <th className="py-2.5 px-4">Key Leaders / Movers</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {sectors.map((sec) => (
                    <tr key={sec.sector} className="hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-4 font-semibold text-foreground">{sec.sector}</td>
                      <td className="py-3 px-3">
                        <span
                          className={`px-2 py-0.5 text-[10px] font-semibold rounded ${
                            sec.trend === 'LEADING'
                              ? 'bg-up/10 text-up border border-up/20'
                              : sec.trend === 'IMPROVING'
                                ? 'bg-accent/10 text-accent border border-accent/20'
                                : sec.trend === 'LAGGING'
                                  ? 'bg-down/10 text-down border border-down/20'
                                  : 'bg-muted text-muted-foreground border border-border'
                          }`}
                        >
                          {sec.trend || '—'}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-mono font-medium">
                        {Number.isFinite(sec.relative_strength)
                          ? `${fmtNum(sec.relative_strength, 1)} / 100`
                          : '—'}
                      </td>
                      <td className="py-3 px-3 font-mono">
                        <span className={returnToneClass(sec.return_20d_pct)}>
                          {Number.isFinite(sec.return_20d_pct)
                            ? `${sec.return_20d_pct > 0 ? '+' : ''}${fmtNum(sec.return_20d_pct, 2)}%`
                            : '—'}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-muted-foreground">
                        {sec.leading_stocks?.join(', ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
