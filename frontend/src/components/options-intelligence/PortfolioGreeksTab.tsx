'use client';

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Scale, ShieldCheck, Activity, AlertTriangle, Layers } from 'lucide-react';
import { PortfolioGreeksSummary } from './options-types';

interface PortfolioGreeksTabProps {
  portfolioGreeks: PortfolioGreeksSummary | null;
}

export const PortfolioGreeksTab: React.FC<PortfolioGreeksTabProps> = ({ portfolioGreeks }) => {
  const delta = portfolioGreeks?.total_delta ?? 0.0;
  const gamma = portfolioGreeks?.total_gamma ?? 0.0;
  const theta = portfolioGreeks?.total_theta_day ?? 0.0;
  const vega = portfolioGreeks?.total_vega ?? 0.0;
  const openPositions = portfolioGreeks?.total_open_positions ?? 0;

  return (
    <div className="space-y-5">
      {/* 1. Consolidated Greek Risk Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {/* Total Delta */}
        <Card className="bg-card/80 border-border/60 shadow-xs">
          <CardHeader className="pb-2">
            <CardDescription className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Portfolio Delta (ΣΔ)
            </CardDescription>
            <CardTitle className="text-2xl font-bold font-mono text-primary mt-0.5">
              {delta > 0 ? `+${delta.toFixed(2)}` : delta.toFixed(2)}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">Net directional shares equivalent</div>
            <div className="mt-2 text-[10px] font-mono text-muted-foreground flex justify-between">
              <span>Risk Boundary:</span>
              <span className="text-foreground font-semibold">±150.0 Δ</span>
            </div>
          </CardContent>
        </Card>

        {/* Total Gamma */}
        <Card className="bg-card/80 border-border/60 shadow-xs">
          <CardHeader className="pb-2">
            <CardDescription className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Portfolio Gamma (ΣΓ)
            </CardDescription>
            <CardTitle className="text-2xl font-bold font-mono text-foreground mt-0.5">
              {gamma.toFixed(4)}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">Second-order curvature exposure</div>
            <div className="mt-2 text-[10px] font-mono text-muted-foreground flex justify-between">
              <span>Acceleration:</span>
              <span className="text-foreground font-semibold">Bounded</span>
            </div>
          </CardContent>
        </Card>

        {/* Daily Theta Burn */}
        <Card className="bg-card/80 border-border/60 shadow-xs">
          <CardHeader className="pb-2">
            <CardDescription className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Daily Theta Burn (ΣΘ)
            </CardDescription>
            <CardTitle className="text-2xl font-bold font-mono text-rose-400 mt-0.5">
              ₹{Math.abs(theta).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}/day
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">Consolidated overnight decay cost</div>
            <div className="mt-2 text-[10px] font-mono text-muted-foreground flex justify-between">
              <span>Daily Decay Cap:</span>
              <span className="text-foreground font-semibold">₹15,000</span>
            </div>
          </CardContent>
        </Card>

        {/* Portfolio Vega */}
        <Card className="bg-card/80 border-border/60 shadow-xs">
          <CardHeader className="pb-2">
            <CardDescription className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Portfolio Vega (ΣV)
            </CardDescription>
            <CardTitle className="text-2xl font-bold font-mono text-foreground mt-0.5">
              ₹{vega.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">Exposure per 1% IV shift</div>
            <div className="mt-2 text-[10px] font-mono text-muted-foreground flex justify-between">
              <span>Vol Regime:</span>
              <span className="text-emerald-400 font-semibold">Normal</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 2. Cross-Horizon Compounding Exposure Harmonizer (§51) */}
      <Card className="bg-card/80 border-border/60 shadow-xs">
        <CardHeader className="pb-3 border-b border-border/40">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <CardTitle className="text-sm font-bold text-foreground flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-primary" />
                Cross-Horizon Compounding Exposure Harmonizer (§51)
              </CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Prevents hidden compounding risk when Scalp, Intraday, and Swing strategies trigger simultaneously on the same underlying.
              </CardDescription>
            </div>
            <Badge variant="outline" className="text-emerald-400 border-emerald-500/30 text-xs font-mono self-start sm:self-auto">
              HARMONIZED &amp; BOUNDED
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="p-4 space-y-3.5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="p-3 bg-muted/25 rounded-xl border border-border/40">
              <div className="text-[11px] font-medium text-muted-foreground">Open Strategy Positions</div>
              <div className="text-lg font-bold font-mono text-foreground mt-1">
                {openPositions} Active Contracts
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5">Below 6 concurrent position limit</div>
            </div>

            <div className="p-3 bg-muted/25 rounded-xl border border-border/40">
              <div className="text-[11px] font-medium text-muted-foreground">Directional Alignment</div>
              <div className="text-lg font-bold font-mono text-emerald-400 mt-1">
                Synchronized
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5">No opposing intraday vs scalp conflict</div>
            </div>

            <div className="p-3 bg-muted/25 rounded-xl border border-border/40">
              <div className="text-[11px] font-medium text-muted-foreground">Expiry Concentration</div>
              <div className="text-lg font-bold font-mono text-foreground mt-1">
                Balanced
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5">Distributed across weekly &amp; monthly</div>
            </div>
          </div>

          <div className="p-3 bg-muted/20 border border-border/40 rounded-lg text-xs text-muted-foreground flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary shrink-0" />
            <span>
              <strong>Cross-Horizon Rule:</strong> When active Delta on any single underlying index exceeds ±100, new Scalping entries require automated approval from the portfolio ledger.
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
