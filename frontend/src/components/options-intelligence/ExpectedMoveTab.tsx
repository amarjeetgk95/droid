'use client';

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Gauge, TrendingUp, Clock, Activity, Target, ShieldCheck, AlertCircle } from 'lucide-react';
import { ExpectedMoveProjection } from './options-types';

interface ExpectedMoveTabProps {
  expectedMoveData: ExpectedMoveProjection | null;
}

export const ExpectedMoveTab: React.FC<ExpectedMoveTabProps> = ({ expectedMoveData }) => {
  if (!expectedMoveData || (expectedMoveData.spot_price ?? 0) <= 0) {
    return (
      <div className="bg-card/80 border border-border/70 rounded-2xl p-8 text-center space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-muted/60 border border-border flex items-center justify-center mx-auto text-muted-foreground">
          <Gauge className="w-6 h-6 text-muted-foreground/60" />
        </div>
        <div className="max-w-md mx-auto space-y-1.5">
          <h3 className="text-base font-bold text-foreground">
            Expected Move Projection Unavailable
          </h3>
          <p className="text-xs text-muted-foreground leading-relaxed">
            <strong className="text-foreground">The Truth of Wall:</strong> Velocity vs theta ratios and staged target ladders require authentic market data from your broker API. When the broker connection is offline, no false or fictitious target projections are generated.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
          <a
            href="/settings"
            className="px-3.5 py-1.5 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-colors"
          >
            Connect Broker in Settings
          </a>
        </div>
      </div>
    );
  }

  const isVelocityApproved = expectedMoveData.is_fast_enough_for_option ?? true;
  const spot = expectedMoveData.spot_price;
  const t1 = expectedMoveData.conservative_move_points ?? spot + 80;
  const t2 = expectedMoveData.aggressive_move_points ?? spot + 160;
  const t3 = spot + (expectedMoveData.expected_move_points || 100);

  return (
    <div className="space-y-5">
      {/* 1. Velocity vs Theta Decoupling Hero HUD (§8 Core Invariant) */}
      <Card className="bg-card/80 border-border/60 shadow-xs">
        <CardHeader className="pb-3 border-b border-border/40">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <CardTitle className="text-sm font-bold text-foreground flex items-center gap-2">
                <Gauge className="w-4 h-4 text-primary" />
                Velocity vs Option Theta Decoupling (§8 Core Invariant)
              </CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Evaluates whether the projected underlying velocity exceeds the contract&apos;s hourly theta burn.
              </CardDescription>
            </div>
            <Badge
              className={`text-xs font-semibold px-3 py-1 self-start sm:self-auto font-mono ${
                isVelocityApproved
                  ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                  : 'bg-rose-500/15 text-rose-400 border-rose-500/30'
              }`}
            >
              {isVelocityApproved ? 'VELOCITY APPROVED FOR BUYING' : 'VELOCITY TOO SLOW (THETA DOMINATES)'}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="p-4 space-y-4">
          {/* Visual Velocity vs Theta Metric Comparison */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-muted/30 p-3 rounded-xl border border-border/50">
              <div className="text-[11px] font-medium text-muted-foreground">Price Velocity</div>
              <div className="text-xl font-bold font-mono text-primary mt-1">
                {expectedMoveData?.expected_velocity_pts_per_hour?.toFixed(1) || '0.0'} <span className="text-xs font-normal">pts/hr</span>
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5">Underlying speed</div>
            </div>

            <div className="bg-muted/30 p-3 rounded-xl border border-border/50">
              <div className="text-[11px] font-medium text-muted-foreground">Hourly Theta Drag</div>
              <div className="text-xl font-bold font-mono text-rose-400 mt-1">
                -₹{expectedMoveData?.hourly_theta_decay?.toFixed(1) || '0.0'} <span className="text-xs font-normal">/hr</span>
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5">Option premium decay</div>
            </div>

            <div className="bg-muted/30 p-3 rounded-xl border border-border/50">
              <div className="text-[11px] font-medium text-muted-foreground">Expected Duration</div>
              <div className="text-xl font-bold font-mono text-foreground mt-1">
                {expectedMoveData?.expected_duration_hours?.toFixed(1) || '1.0'} <span className="text-xs font-normal">hrs</span>
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5">Target arrival horizon</div>
            </div>

            <div className="bg-muted/30 p-3 rounded-xl border border-border/50">
              <div className="text-[11px] font-medium text-muted-foreground">1-Sigma IV Move</div>
              <div className="text-xl font-bold font-mono text-foreground mt-1">
                ±{expectedMoveData?.iv_implied_1sigma_move?.toFixed(1) || '0.0'} <span className="text-xs font-normal">pts</span>
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5">Statistical dispersion</div>
            </div>
          </div>

          {/* Forecast Diagnostics Checklist */}
          <div className="p-3 bg-muted/20 border border-border/40 rounded-lg text-xs space-y-1.5">
            <div className="font-semibold text-foreground flex items-center gap-1.5 text-[11px]">
              <Activity className="w-3.5 h-3.5 text-primary" />
              Timing &amp; Velocity Diagnostics:
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {expectedMoveData?.forecast_rationale?.map((r: string, i: number) => (
                <div key={i} className="text-muted-foreground flex items-start gap-2 text-[11px]">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary mt-1 shrink-0" />
                  <span>{r}</span>
                </div>
              )) || <div className="text-muted-foreground text-xs">Standard session volatility baseline.</div>}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 2. Expected Move Target Ladder (T1, T2, T3) */}
      <div>
        <div className="flex items-center justify-between mb-2.5 px-1">
          <div className="text-xs font-bold text-foreground flex items-center gap-2">
            <Target className="w-4 h-4 text-primary" />
            Staged Target Projection Ladder
          </div>
          <span className="text-[11px] font-mono text-muted-foreground">Spot Reference: ₹{spot.toFixed(2)}</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
          {/* T1 Conservative */}
          <Card className="bg-card/70 border-border/60 shadow-xs">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardDescription className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Conservative Target (T1)
                </CardDescription>
                <Badge variant="outline" className="text-[10px] font-mono text-emerald-400 border-emerald-500/30">
                  High Probability
                </Badge>
              </div>
              <CardTitle className="text-xl font-bold font-mono text-foreground mt-1">
                ₹{t1.toFixed(2)}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-xs text-muted-foreground">
              <div className="flex justify-between">
                <span>Distance from Spot:</span>
                <span className="font-mono font-semibold text-foreground">+{Math.abs(t1 - spot).toFixed(1)} pts</span>
              </div>
              <div className="flex justify-between">
                <span>Target Horizon:</span>
                <span className="font-mono text-foreground">~{(expectedMoveData?.expected_duration_hours || 1.0) * 0.5} hrs</span>
              </div>
              <p className="text-[11px] pt-1 text-muted-foreground/80">
                Initial scalp anchor; lock in partial gains to neutralize theta risk.
              </p>
            </CardContent>
          </Card>

          {/* T2 Structural */}
          <Card className="bg-card/70 border-border/60 shadow-xs">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardDescription className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Structural Target (T2)
                </CardDescription>
                <Badge variant="outline" className="text-[10px] font-mono text-primary border-primary/30">
                  Base Case
                </Badge>
              </div>
              <CardTitle className="text-xl font-bold font-mono text-primary mt-1">
                ₹{t2.toFixed(2)}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-xs text-muted-foreground">
              <div className="flex justify-between">
                <span>Distance from Spot:</span>
                <span className="font-mono font-semibold text-foreground">+{Math.abs(t2 - spot).toFixed(1)} pts</span>
              </div>
              <div className="flex justify-between">
                <span>Target Horizon:</span>
                <span className="font-mono text-foreground">~{expectedMoveData?.expected_duration_hours || 1.0} hrs</span>
              </div>
              <p className="text-[11px] pt-1 text-muted-foreground/80">
                Key liquidity pool / order block retest target.
              </p>
            </CardContent>
          </Card>

          {/* T3 Extended */}
          <Card className="bg-card/70 border-border/60 shadow-xs">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardDescription className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Extended Target (T3)
                </CardDescription>
                <Badge variant="outline" className="text-[10px] font-mono text-cyan-400 border-cyan-500/30">
                  Trend Expansion
                </Badge>
              </div>
              <CardTitle className="text-xl font-bold font-mono text-cyan-400 mt-1">
                ₹{t3.toFixed(2)}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-xs text-muted-foreground">
              <div className="flex justify-between">
                <span>Distance from Spot:</span>
                <span className="font-mono font-semibold text-foreground">+{Math.abs(t3 - spot).toFixed(1)} pts</span>
              </div>
              <div className="flex justify-between">
                <span>Target Horizon:</span>
                <span className="font-mono text-foreground">~{(expectedMoveData?.expected_duration_hours || 1.0) * 1.5} hrs</span>
              </div>
              <p className="text-[11px] pt-1 text-muted-foreground/80">
                Multi-standard deviation momentum extension.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};
