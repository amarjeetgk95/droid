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
  Gauge,
  Zap,
} from 'lucide-react';
import { useSwingData } from './useSwingData';
import { SwingSetupCard } from './SwingSetupCard';
import { SwingPositionsTable } from './SwingPositionsTable';
import { TelemetryStrip, TelemetryItem } from '@/components/ui/desk';

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

  const getRegimeBadge = (r: string) => {
    switch (r) {
      case 'BULL':
        return <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-emerald-500/10 text-emerald-500 border border-emerald-500/30">BULL REGIME</span>;
      case 'DISTRIBUTION':
        return <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-amber-500/10 text-amber-500 border border-amber-500/30">DISTRIBUTION (CAUTION)</span>;
      case 'BEAR':
        return <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-rose-500/10 text-rose-500 border border-rose-500/30">BEAR (CALLS RESTRICTED)</span>;
      case 'HIGH_VOLATILITY':
        return <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-orange-500/10 text-orange-500 border border-orange-500/30">HIGH VOLATILITY</span>;
      default:
        return <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-muted text-muted-foreground border border-border">NEUTRAL REGIME</span>;
    }
  };

  return (
    <div className="space-y-3 pb-8">
      {/* Top Header / Telemetry Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-3 rounded-md border border-border bg-card shadow-xs">
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-lg font-bold tracking-tight text-foreground flex items-center gap-1.5">
              <TrendingUp className="w-4 h-4 text-primary" />
              Index Options Swing Desk
            </h1>
            {regime && getRegimeBadge(regime.regime)}
            {regime && (
              <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-sky-500/10 text-sky-400 border border-sky-500/30">
                IV Rank: {regime.iv_percentile?.toFixed(0) || 50}% ({regime.iv_regime || 'NORMAL'})
              </span>
            )}
          </div>
          <p className="text-[11.5px] text-muted-foreground">
            Long index options swing setups — Positional (2–20 days) &amp; Intraday (same-day 15M/ORB). Dual-layer stops with Greek risk limits.
          </p>
        </div>

        {/* Action button */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => triggerScan(true, selectedHorizon !== 'ALL' ? selectedHorizon : undefined)}
            disabled={scanning}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 shadow-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
            <span>{scanning ? 'Scanning…' : 'Scan Index Options'}</span>
          </button>
        </div>
      </div>

      {/* Telemetry Metric Ribbon */}
      <TelemetryStrip>
        <TelemetryItem
          label="Portfolio Heat"
          value={`${portfolioRisk ? portfolioRisk.portfolio_heat_pct.toFixed(1) : '0.0'}%`}
          sub={`max ${portfolioRisk?.max_heat_pct || 5.0}%`}
          tone={(portfolioRisk?.portfolio_heat_pct || 0) > 4.0 ? 'bear' : 'bull'}
        />
        <TelemetryItem
          label="Net Greeks"
          value={`Δ ${portfolioRisk ? portfolioRisk.net_delta.toFixed(2) : '0.00'}`}
          sub={`Θ -₹${portfolioRisk ? Math.abs(portfolioRisk.net_theta_day).toFixed(0) : '0'}/d · Vega ₹${portfolioRisk ? portfolioRisk.net_vega.toFixed(0) : '0'}`}
        />
        <TelemetryItem
          label="Active Positions"
          value={`${openPositions.length} / ${portfolioRisk?.max_positions_count || 6}`}
          sub={`Deployed ₹${portfolioRisk ? (portfolioRisk.total_premium_deployed / 1000).toFixed(1) : '0'}k`}
        />
        <TelemetryItem
          label="Discovered Setups"
          value={`${setups.length}`}
          sub={`${setups.filter((s) => s.signal_state === 'READY' || s.signal_state === 'TRIGGERED').length} actionable`}
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
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-2 rounded-xl border border-border bg-card shadow-xs">
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
                    ? 'bg-sky-500/15 text-sky-400 border border-sky-500/30 shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <span>📅 Positional (2–20D)</span>
              </button>
              <button
                onClick={() => setSelectedHorizon('INTRADAY')}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-all ${
                  selectedHorizon === 'INTRADAY'
                    ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30 shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>⚡ Intraday Swing (Same-Day)</span>
              </button>
            </div>

            <div className="text-xs text-muted-foreground px-2">
              {selectedHorizon === 'INTRADAY' ? (
                <span className="text-amber-400 font-medium">⚡ 15M / ORB Same-Day Trades • 15:15 IST Mandatory Square-Off</span>
              ) : selectedHorizon === 'POSITIONAL' ? (
                <span className="text-sky-400 font-medium">📅 Multi-Day Trend & Pullback Setups • Held 2–20 Days</span>
              ) : (
                <span>Dual-Horizon Trading: Positional Multi-Day & Intraday Momentum</span>
              )}
            </div>
          </div>

          {/* Intraday HUD Banner */}
          {selectedHorizon === 'INTRADAY' && (
            <div className="p-3.5 rounded-xl border border-amber-500/30 bg-amber-500/5 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400">
                  <Zap className="w-4 h-4" />
                </div>
                <div>
                  <div className="font-bold text-amber-400 flex items-center gap-2">
                    <span>⚡ INTRADAY SWING DESK (SAME-DAY ACTIVE)</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-300 font-mono">15M BARS</span>
                  </div>
                  <p className="text-muted-foreground text-[11px] mt-0.5">
                    Zero overnight gap risk. Fast break-even shift at +1.0R. Mandatory auto-exit triggered at 15:15:00 IST.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 font-mono text-[11px]">
                <span className="px-2 py-1 rounded bg-background border border-amber-500/30 text-amber-300">
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
                  <optgroup label="Intraday Strategies (15M)">
                    <option value="INTRADAY_PULLBACK_CE">⚡ Intraday Pullback CE (15M)</option>
                    <option value="INTRADAY_PULLBACK_PE">⚡ Intraday Pullback PE (15M)</option>
                    <option value="INTRADAY_ORB_CE">⚡ Intraday ORB CE (30M)</option>
                    <option value="INTRADAY_ORB_PE">⚡ Intraday ORB PE (30M)</option>
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
            </span>
          </div>

          {/* Setups Cards Grid */}
          {loading ? (
            <div className="flex items-center justify-center py-20 text-muted-foreground text-xs gap-2">
              <RefreshCw className="w-5 h-5 animate-spin text-primary" />
              <span>Scanning live index options chains...</span>
            </div>
          ) : setups.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground text-xs rounded-xl border border-dashed border-border p-8 text-center gap-2">
              <Shield className="w-8 h-8 opacity-40" />
              <span className="text-sm font-semibold text-foreground">No options setups meet current filter criteria.</span>
              <span>
                Rule §2: Abstention is a first-class outcome. If no high-quality, IV-favorable setups pass the 4-layer validity gate, zero forced trades are generated.
              </span>
              <button
                onClick={() => triggerScan(true)}
                className="mt-3 px-3 py-1.5 text-xs font-medium rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
              >
                Scan Universe
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
          onExitPosition={async (pid, premium, reason) => {
            await exitTrade(pid, premium, reason);
          }}
        />
      )}

      {/* Tab: Sectors / Indices */}
      {activeTab === 'sectors' && (
        <div className="rounded-xl border border-border bg-card text-card-foreground shadow-xs overflow-hidden">
          <div className="p-4 border-b border-border bg-muted/20">
            <h3 className="text-sm font-semibold text-foreground">Index Relative Strength & Momentum (§10)</h3>
            <p className="text-xs text-muted-foreground">
              Tracks underlying index momentum relative to NIFTY benchmark to confirm directional options bias.
            </p>
          </div>
          <div className="overflow-x-auto">
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
                    <td className="py-3 px-3 font-mono font-medium">{sec.relative_strength?.toFixed(1) || '50.0'} / 100</td>
                    <td className="py-3 px-3 font-mono">
                      <span className={(sec.return_20d_pct || 0) >= 0 ? 'text-emerald-500' : 'text-rose-500'}>
                        {(sec.return_20d_pct || 0) >= 0 ? '+' : ''}{(sec.return_20d_pct || 0).toFixed(2)}%
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
