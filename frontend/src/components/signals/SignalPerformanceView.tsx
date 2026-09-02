'use client';

import { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import {
  Activity,
  Award,
  CheckCircle2,
  Percent,
  RefreshCw,
  Scale,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
  XCircle,
} from 'lucide-react';

export function SignalPerformanceView() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const fetchPerformance = async () => {
    setLoading(true);
    try {
      const res = await api.getSignalsPerformance();
      setData(res);
    } catch {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPerformance();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold flex items-center gap-2">
            <Award className="w-5 h-5 text-primary" /> Quantitative Performance & Strategy Attribution
          </h2>
          <p className="text-xs text-muted-foreground">
            Evaluated against real market outcomes (Target 1: 1.5R, Target 2: 3.0R, Stop Loss: -1.0R).
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchPerformance} disabled={loading} className="h-8 text-xs gap-1">
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Refresh Metrics
        </Button>
      </div>

      {/* Top 4 KPI Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="bg-emerald-500/5 border-emerald-500/20">
          <CardContent className="pt-4 space-y-1">
            <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
              <Percent className="w-4 h-4 text-emerald-600" /> Win Rate
            </span>
            <div className="text-2xl font-bold font-mono text-emerald-600">
              {data?.win_rate_pct !== undefined ? `${data.win_rate_pct}%` : '—'}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {data?.winning_signals || 0} Wins / {data?.completed_signals || 0} Completed
            </p>
          </CardContent>
        </Card>

        <Card className="bg-primary/5 border-primary/20">
          <CardContent className="pt-4 space-y-1">
            <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
              <Scale className="w-4 h-4 text-primary" /> Profit Factor
            </span>
            <div className="text-2xl font-bold font-mono text-primary">
              {data?.profit_factor !== undefined ? `${data.profit_factor}x` : '—'}
            </div>
            <p className="text-[11px] text-muted-foreground">Gross Gains vs Losses</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4 space-y-1">
            <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
              <TrendingUp className="w-4 h-4 text-emerald-600" /> Expectancy / Trade
            </span>
            <div className="text-2xl font-bold font-mono text-foreground">
              {data?.expectancy_r !== undefined ? `+${data.expectancy_r} R` : '—'}
            </div>
            <p className="text-[11px] text-muted-foreground">Average R:R {data?.average_rr || '2.25'}x</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4 space-y-1">
            <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
              <Target className="w-4 h-4 text-primary" /> Target 2 Full Wins
            </span>
            <div className="text-2xl font-bold font-mono text-emerald-700">
              {data?.target_2_hits || 0}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {data?.target_1_hits || 0} T1 Hits • {data?.stop_loss_hits || 0} SL Hits
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Strategy Breakdown Table */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Strategy Win-Rate Breakdown</CardTitle>
            <CardDescription className="text-xs">Performance partitioned across the 5 quant strategies</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-muted/60 border-b text-muted-foreground font-semibold">
                  <tr>
                    <th className="p-2.5 text-left">Strategy</th>
                    <th className="p-2.5 text-center">Total</th>
                    <th className="p-2.5 text-center">Wins</th>
                    <th className="p-2.5 text-center">Losses</th>
                    <th className="p-2.5 text-right">Win Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y font-mono">
                  {Object.entries(data?.strategy_breakdown || {}).length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-4 text-center text-muted-foreground font-sans">
                        No trade outcomes recorded yet.
                      </td>
                    </tr>
                  ) : (
                    Object.entries(data?.strategy_breakdown || {}).map(([strat, stats]: any) => (
                      <tr key={strat}>
                        <td className="p-2.5 font-bold font-sans">{strat}</td>
                        <td className="p-2.5 text-center">{stats.total}</td>
                        <td className="p-2.5 text-center text-emerald-600 font-bold">{stats.wins}</td>
                        <td className="p-2.5 text-center text-destructive">{stats.losses}</td>
                        <td className="p-2.5 text-right font-bold text-primary">{stats.win_rate}%</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Underlying Index Attribution</CardTitle>
            <CardDescription className="text-xs">Performance across NIFTY, BANKNIFTY, SENSEX</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-muted/60 border-b text-muted-foreground font-semibold">
                  <tr>
                    <th className="p-2.5 text-left">Index</th>
                    <th className="p-2.5 text-center">Total</th>
                    <th className="p-2.5 text-center">Wins</th>
                    <th className="p-2.5 text-center">Losses</th>
                    <th className="p-2.5 text-right">Win Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y font-mono">
                  {Object.entries(data?.underlying_breakdown || {}).length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-4 text-center text-muted-foreground font-sans">
                        No index outcomes recorded yet.
                      </td>
                    </tr>
                  ) : (
                    Object.entries(data?.underlying_breakdown || {}).map(([idx, stats]: any) => (
                      <tr key={idx}>
                        <td className="p-2.5 font-bold font-sans">{idx}</td>
                        <td className="p-2.5 text-center">{stats.total}</td>
                        <td className="p-2.5 text-center text-emerald-600 font-bold">{stats.wins}</td>
                        <td className="p-2.5 text-center text-destructive">{stats.losses}</td>
                        <td className="p-2.5 text-right font-bold text-primary">{stats.win_rate}%</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
