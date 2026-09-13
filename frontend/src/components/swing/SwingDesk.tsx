'use client';

import { useState, useMemo } from 'react';
import {
  TrendingUp,
  Shield,
  RefreshCw,
  SlidersHorizontal,
  Layers,
  AlertCircle,
  CheckCircle2,
  Activity,
  Flame,
  Briefcase,
  PieChart,
} from 'lucide-react';
import { useSwingData } from './useSwingData';
import { SwingSetupCard } from './SwingSetupCard';
import { SwingPositionsTable } from './SwingPositionsTable';

export function SwingDesk() {
  const [activeTab, setActiveTab] = useState<'setups' | 'positions' | 'sectors'>('setups');
  const [selectedStrategy, setSelectedStrategy] = useState<string>('ALL');
  const [selectedSector, setSelectedSector] = useState<string>('ALL');
  const [minScore, setMinScore] = useState<number>(50);

  const filters = useMemo(() => {
    return {
      strategy: selectedStrategy !== 'ALL' ? selectedStrategy : undefined,
      sector: selectedSector !== 'ALL' ? selectedSector : undefined,
      min_score: minScore > 0 ? minScore : undefined,
    };
  }, [selectedStrategy, selectedSector, minScore]);

  const {
    loading,
    scanning,
    setups,
    openPositions,
    closedPositions,
    portfolioRisk,
    regime,
    sectors,
    error,
    refresh,
    triggerScan,
    enterTrade,
    exitTrade,
  } = useSwingData(filters);

  const uniqueSectors = useMemo(() => {
    const list = sectors.map((s) => s.sector);
    return ['ALL', ...Array.from(new Set(list))];
  }, [sectors]);

  const getRegimeBadge = (r: string) => {
    switch (r) {
      case 'BULL':
        return <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-emerald-500/10 text-emerald-500 border border-emerald-500/30">BULL (NORMAL RISK)</span>;
      case 'DISTRIBUTION':
        return <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-amber-500/10 text-amber-500 border border-amber-500/30">DISTRIBUTION (CAUTION)</span>;
      case 'BEAR':
        return <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-rose-500/10 text-rose-500 border border-rose-500/30">BEAR (LONGS RESTRICTED)</span>;
      case 'HIGH_VOLATILITY':
        return <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-orange-500/10 text-orange-500 border border-orange-500/30">HIGH VOLATILITY</span>;
      default:
        return <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-muted text-muted-foreground border border-border">NEUTRAL REGIME</span>;
    }
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Top Header / Telemetry Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 rounded-xl border border-border bg-card shadow-xs">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-primary" />
              Swing Trading Desk
            </h1>
            {regime && getRegimeBadge(regime.regime)}
          </div>
          <p className="text-xs text-muted-foreground">
            Multi-day positional setups (2–20 days) across Top 50 Indian F&O equities. Structural stops with ATR floor.
          </p>
        </div>

        {/* Action button */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => triggerScan(true)}
            disabled={scanning}
            className="flex items-center gap-2 px-3.5 py-2 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 shadow-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
            <span>{scanning ? 'Running EOD Scan...' : 'Run Scan'}</span>
          </button>
        </div>
      </div>

      {/* Telemetry Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>Portfolio Heat</span>
            <Flame className="w-4 h-4 text-amber-500" />
          </div>
          <div className="text-xl font-bold font-mono text-foreground mt-1">
            {portfolioRisk ? portfolioRisk.portfolio_heat_pct.toFixed(1) : '0.0'}%
            <span className="text-xs font-normal text-muted-foreground"> / {portfolioRisk?.max_heat_pct || 5.0}%</span>
          </div>
          <div className="w-full bg-muted rounded-full h-1.5 mt-2 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                (portfolioRisk?.portfolio_heat_pct || 0) > 4.0 ? 'bg-rose-500' : 'bg-primary'
              }`}
              style={{ width: `${Math.min(100, ((portfolioRisk?.portfolio_heat_pct || 0) / (portfolioRisk?.max_heat_pct || 5.0)) * 100)}%` }}
            />
          </div>
        </div>

        <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>Active Positions</span>
            <Briefcase className="w-4 h-4 text-primary" />
          </div>
          <div className="text-xl font-bold font-mono text-foreground mt-1">
            {openPositions.length}
            <span className="text-xs font-normal text-muted-foreground"> / {portfolioRisk?.max_positions_count || 6} max</span>
          </div>
          <div className="text-[11px] text-muted-foreground mt-1">
            Open Cap: ₹{portfolioRisk ? (portfolioRisk.open_capital / 100000).toFixed(2) : '0.0'}L
          </div>
        </div>

        <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>Discovered Setups</span>
            <Layers className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-xl font-bold font-mono text-foreground mt-1">
            {setups.length}
          </div>
          <div className="text-[11px] text-muted-foreground mt-1">
            {setups.filter((s) => s.signal_state === 'READY' || s.signal_state === 'TRIGGERED').length} actionable now
          </div>
        </div>

        <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>Leading Sectors</span>
            <Activity className="w-4 h-4 text-sky-500" />
          </div>
          <div className="flex flex-wrap gap-1 mt-1.5">
            {sectors
              .filter((s) => s.trend === 'LEADING')
              .slice(0, 2)
              .map((s) => (
                <span key={s.sector} className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                  {s.sector} ({s.return_20d_pct > 0 ? '+' : ''}{s.return_20d_pct}%)
                </span>
              ))}
            {sectors.filter((s) => s.trend === 'LEADING').length === 0 && (
              <span className="text-xs text-muted-foreground">No leading sectors</span>
            )}
          </div>
        </div>
      </div>

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
            <span>Setups & Radar</span>
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
            <span>Sector Relative Strength</span>
          </button>
        </div>
      </div>

      {/* Tab: Setups */}
      {activeTab === 'setups' && (
        <div className="space-y-4">
          {/* Filter Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg border border-border bg-muted/20 text-xs">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <SlidersHorizontal className="w-3.5 h-3.5" />
                <span>Strategy:</span>
                <select
                  value={selectedStrategy}
                  onChange={(e) => setSelectedStrategy(e.target.value)}
                  className="bg-background border border-border rounded-md px-2 py-1 text-foreground"
                >
                  <option value="ALL">All Strategies</option>
                  <option value="VCP_BREAKOUT">VCP Breakout</option>
                  <option value="TREND_PULLBACK_20EMA">20 EMA Pullback</option>
                  <option value="STAGE2_BREAKOUT">Stage 2 Breakout</option>
                </select>
              </div>

              <div className="flex items-center gap-1.5 text-muted-foreground">
                <span>Sector:</span>
                <select
                  value={selectedSector}
                  onChange={(e) => setSelectedSector(e.target.value)}
                  className="bg-background border border-border rounded-md px-2 py-1 text-foreground"
                >
                  {uniqueSectors.map((sec) => (
                    <option key={sec} value={sec}>
                      {sec}
                    </option>
                  ))}
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
            </span>
          </div>

          {/* Setups Cards Grid */}
          {loading ? (
            <div className="flex items-center justify-center py-20 text-muted-foreground text-xs gap-2">
              <RefreshCw className="w-5 h-5 animate-spin text-primary" />
              <span>Loading swing setups...</span>
            </div>
          ) : setups.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground text-xs rounded-xl border border-dashed border-border p-8 text-center gap-2">
              <Shield className="w-8 h-8 opacity-40" />
              <span className="text-sm font-semibold text-foreground">No setups meet current filter criteria.</span>
              <span>
                Rule §2: Abstention is a first-class outcome. If no high-quality setups exist, the system safely generates zero forced trades.
              </span>
              <button
                onClick={() => triggerScan(true)}
                className="mt-3 px-3 py-1.5 text-xs font-medium rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
              >
                Trigger Fresh Universe Scan
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {setups.map((s) => (
                <SwingSetupCard
                  key={s.setup_id}
                  setup={s}
                  onEnterTrade={async (sid, price) => {
                    await enterTrade(sid, price);
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
          onExitPosition={async (pid, price) => {
            await exitTrade(pid, price);
          }}
        />
      )}

      {/* Tab: Sectors */}
      {activeTab === 'sectors' && (
        <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm overflow-hidden">
          <div className="p-4 border-b border-border bg-muted/20">
            <h3 className="text-sm font-semibold text-foreground">Sector Relative Strength & Breadth (§10)</h3>
            <p className="text-xs text-muted-foreground">
              Sector momentum acts as a confirmation filter for swing setups, preventing counter-trend entries.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border/60 bg-muted/40 text-muted-foreground font-medium text-[11px]">
                  <th className="py-2.5 px-4">Sector</th>
                  <th className="py-2.5 px-3">Momentum Status</th>
                  <th className="py-2.5 px-3">Relative Strength (vs NIFTY)</th>
                  <th className="py-2.5 px-3">20-Day Return</th>
                  <th className="py-2.5 px-4">Top Constituent Leaders</th>
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
                            ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                            : sec.trend === 'IMPROVING'
                            ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                            : sec.trend === 'LAGGING'
                            ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20'
                            : 'bg-muted text-muted-foreground border border-border'
                        }`}
                      >
                        {sec.trend}
                      </span>
                    </td>
                    <td className="py-3 px-3 font-mono font-medium">{sec.relative_strength.toFixed(1)} / 100</td>
                    <td className="py-3 px-3 font-mono">
                      <span className={sec.return_20d_pct >= 0 ? 'text-emerald-500' : 'text-rose-500'}>
                        {sec.return_20d_pct >= 0 ? '+' : ''}{sec.return_20d_pct.toFixed(2)}%
                      </span>
                    </td>
                    <td className="py-3 px-4 text-muted-foreground">
                      {sec.leading_stocks?.join(', ') || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
