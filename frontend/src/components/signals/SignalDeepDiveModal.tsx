'use client';

import { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Crosshair,
  Gauge,
  Layers,
  ShieldAlert,
  Target,
  TrendingDown,
  TrendingUp,
  X,
  Zap,
} from 'lucide-react';

interface Props {
  signalId: string | null;
  onClose: () => void;
  onPaperExecuted?: (result: any) => void;
}

export function SignalDeepDiveModal({ signalId, onClose, onPaperExecuted }: Props) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [customLots, setCustomLots] = useState<string>('2');
  const [paperResult, setPaperResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!signalId) return;
    setLoading(true);
    setError(null);
    api
      .getSignalDeepDive(signalId)
      .then((res) => {
        setData(res);
        if (res.signal?.paper_order) setPaperResult(res.signal.paper_order);
      })
      .catch((err) => setError(err.message || 'Failed to load signal deep dive'))
      .finally(() => setLoading(false));
  }, [signalId]);

  // Escape dismisses the dossier (backdrop click also closes below).
  useEffect(() => {
    if (!signalId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [signalId, onClose]);

  if (!signalId) return null;

  const handleExecute = async () => {
    setExecuting(true);
    setError(null);
    try {
      const lotsNum = customLots ? parseInt(customLots, 10) : undefined;
      const res = await api.executeSignalPaper(signalId, lotsNum);
      if (res && res.success) {
        setPaperResult(res);
        onPaperExecuted?.(res);
      }
    } catch (e: any) {
      setError(e.message || 'Paper trade execution failed');
    } finally {
      setExecuting(false);
    }
  };

  const sig = data?.signal;
  const isCall = sig?.direction?.includes('CALL');
  const dirColor = isCall ? 'text-emerald-600 bg-emerald-500/10 border-emerald-500/30' : 'text-red-600 bg-red-500/10 border-red-500/30';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 overflow-y-auto"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="relative w-full max-w-4xl bg-card border rounded-xl shadow-2xl overflow-hidden my-8 max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        {/* Header */}
        <div className="p-4 border-b flex items-center justify-between bg-muted/30">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg border ${dirColor}`}>
              {isCall ? <ArrowUpRight className="w-6 h-6" /> : <ArrowDownRight className="w-6 h-6" />}
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg font-bold">{sig?.underlying || 'Signal'} Options Strategy</h2>
                <Badge variant="outline" className="font-mono text-xs">
                  {sig?.strategy}
                </Badge>
                <Badge className={dirColor}>{sig?.direction}</Badge>
                <Badge variant="secondary" className="font-mono text-xs">
                  {sig?.timeframe || '5M'}
                </Badge>
                <Badge variant="outline" className="text-xs bg-background">
                  FSM: {sig?.fsm_state || 'ARMED'}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Signal ID: <span className="font-mono">{sig?.signal_id}</span> • Spot: ₹{Number(sig?.spot_price || 0).toLocaleString('en-IN')}
              </p>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} className="h-8 w-8 p-0 rounded-full">
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6 overflow-y-auto flex-1">
          {loading && (
            <div className="py-12 text-center text-sm text-muted-foreground animate-pulse">
              Loading Quantitative Dossier & Market Snapshot…
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> {error}
            </div>
          )}

          {data && sig && (
            <>
              {/* 1. KEY PRICE LEVELS BAR & VISUALIZER */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-lg border bg-secondary/30">
                  <span className="text-[11px] text-muted-foreground font-medium">Trigger / Entry Zone</span>
                  <div className="text-sm font-mono font-bold mt-1">₹{Number(sig.trigger).toLocaleString('en-IN')}</div>
                  <span className="text-[10px] text-muted-foreground">
                    Range: {sig.entry_min} - {sig.entry_max}
                  </span>
                </div>
                <div className="p-3 rounded-lg border bg-destructive/10 border-destructive/20">
                  <span className="text-[11px] text-destructive font-medium">Stop Loss (SL)</span>
                  <div className="text-sm font-mono font-bold text-destructive mt-1">₹{Number(sig.stop_loss).toLocaleString('en-IN')}</div>
                  <span className="text-[10px] text-muted-foreground">Risk: {Number(sig.risk_points).toFixed(1)} pts</span>
                </div>
                <div className="p-3 rounded-lg border bg-emerald-500/10 border-emerald-500/20">
                  <span className="text-[11px] text-emerald-600 font-medium">Target 1 (1.5R)</span>
                  <div className="text-sm font-mono font-bold text-emerald-600 mt-1">₹{Number(sig.target_1).toLocaleString('en-IN')}</div>
                  <span className="text-[10px] text-muted-foreground">Reward: +{Number(sig.risk_points * 1.5).toFixed(1)} pts</span>
                </div>
                <div className="p-3 rounded-lg border bg-emerald-600/10 border-emerald-600/30">
                  <span className="text-[11px] text-emerald-700 font-medium">Target 2 (3.0R)</span>
                  <div className="text-sm font-mono font-bold text-emerald-700 mt-1">₹{Number(sig.target_2).toLocaleString('en-IN')}</div>
                  <span className="text-[10px] text-muted-foreground">Reward: +{Number(sig.risk_points * 3.0).toFixed(1)} pts</span>
                </div>
              </div>

              {/* 2. CONFLUENCE RADAR & GAUGE SUB-SCORES */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center justify-between">
                    <span className="flex items-center gap-2">
                      <Gauge className="w-4 h-4 text-primary" /> Confluence Breakdown ({sig.confidence}% Fused Confidence)
                    </span>
                    <Badge variant="outline" className="font-mono text-xs">
                      Tech 40% + MTF 20% + FNO 20% + Regime 10% + AI 10%
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
                    <div className="p-2 rounded border bg-secondary/20">
                      <div className="text-muted-foreground text-[10px]">Technical (40%)</div>
                      <div className="font-bold text-sm mt-0.5">{sig.confluence_breakdown?.technical || 80}%</div>
                    </div>
                    <div className="p-2 rounded border bg-secondary/20">
                      <div className="text-muted-foreground text-[10px]">Multi-TF (20%)</div>
                      <div className="font-bold text-sm mt-0.5">{sig.confluence_breakdown?.mtf || 75}%</div>
                    </div>
                    <div className="p-2 rounded border bg-secondary/20">
                      <div className="text-muted-foreground text-[10px]">F&O OI/PCR (20%)</div>
                      <div className="font-bold text-sm mt-0.5">{sig.confluence_breakdown?.fno || 75}%</div>
                    </div>
                    <div className="p-2 rounded border bg-secondary/20">
                      <div className="text-muted-foreground text-[10px]">Regime (10%)</div>
                      <div className="font-bold text-sm mt-0.5">{sig.confluence_breakdown?.regime || 80}%</div>
                    </div>
                    <div className="p-2 rounded border bg-secondary/20">
                      <div className="text-muted-foreground text-[10px]">AI Advisory (10%)</div>
                      <div className="font-bold text-sm mt-0.5">{sig.confluence_breakdown?.ai || 75}%</div>
                    </div>
                  </div>

                  {sig.rationale?.length > 0 && (
                    <div className="rounded-lg bg-muted/40 p-3 space-y-1 text-xs">
                      <span className="font-semibold text-muted-foreground text-[11px]">Strategy Rationale:</span>
                      <ul className="list-disc list-inside space-y-0.5 text-muted-foreground">
                        {sig.rationale.map((r: string, i: number) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* 3. DYNAMIC OPTION CONTRACT & POSITION SIZING */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Layers className="w-4 h-4 text-primary" /> Dynamic Option Contract Master
                    </CardTitle>
                    <CardDescription className="text-xs">Resolved from FYERS Contract Master</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2 text-xs">
                    <div className="flex justify-between py-1 border-b">
                      <span className="text-muted-foreground">Broker Symbol</span>
                      <span className="font-mono font-bold">{sig.option_contract?.broker_symbol || '—'}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b">
                      <span className="text-muted-foreground">Strike & Type</span>
                      <span className="font-mono font-bold">
                        ₹{sig.option_contract?.strike} {sig.option_contract?.option_type}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b">
                      <span className="text-muted-foreground">Lot Size</span>
                      <span className="font-mono font-bold">{sig.option_contract?.lot_size || 75} Qty/Lot</span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-muted-foreground">Expiry Date</span>
                      <span className="font-mono">
                        {sig.option_contract?.expiry_date} ({sig.option_contract?.expiry_type})
                      </span>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Crosshair className="w-4 h-4 text-primary" /> Lot-Aware Position Sizing Engine
                    </CardTitle>
                    <CardDescription className="text-xs">Calculated based on 2% risk capital</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2 text-xs">
                    <div className="flex justify-between py-1 border-b">
                      <span className="text-muted-foreground">₹1,00,000 Capital (2% Risk ₹2k)</span>
                      <span className="font-mono font-bold">
                        {data.position_sizing_preview?.account_1lakh?.lots || 0} Lots ({data.position_sizing_preview?.account_1lakh?.quantity || 0} Qty)
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b">
                      <span className="text-muted-foreground">₹5,00,000 Capital (2% Risk ₹10k)</span>
                      <span className="font-mono font-bold">
                        {data.position_sizing_preview?.account_5lakh?.lots || 0} Lots ({data.position_sizing_preview?.account_5lakh?.quantity || 0} Qty)
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-muted-foreground">Max Loss per Lot</span>
                      <span className="font-mono font-bold text-destructive">
                        ₹{Number(data.position_sizing_preview?.account_5lakh?.risk_per_lot || 0).toLocaleString('en-IN')}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* 4. EXECUTION CONTROLS & STATUS */}
              <div className="rounded-xl border p-4 bg-muted/20 flex flex-col sm:flex-row items-center justify-between gap-4">
                {paperResult ? (
                  <div className="flex items-center gap-2 text-emerald-700 font-mono text-xs bg-emerald-100/80 border border-emerald-300 rounded-lg p-3 w-full">
                    <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
                    <div>
                      <div className="font-bold">Paper Trade Filled: {paperResult.side} {paperResult.quantity} Qty @ ₹{Number(paperResult.fill_price).toLocaleString('en-IN')}</div>
                      <div className="text-[11px] text-emerald-800">Order ID: {paperResult.order_id} • Track P&L in Paper Trading tab</div>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center gap-3 w-full sm:w-auto">
                      <label className="text-xs font-medium text-muted-foreground whitespace-nowrap">Lots to Trade:</label>
                      <input
                        type="number"
                        min="1"
                        max="20"
                        value={customLots}
                        onChange={(e) => setCustomLots(e.target.value)}
                        className="w-20 h-8 rounded border px-2 text-xs font-mono bg-background"
                      />
                      <span className="text-xs text-muted-foreground font-mono">
                        ({(parseInt(customLots, 10) || 1) * (sig.option_contract?.lot_size || 75)} Qty)
                      </span>
                    </div>
                    <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
                      <Button
                        size="sm"
                        className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5 w-full sm:w-auto"
                        onClick={handleExecute}
                        disabled={executing}
                      >
                        <Zap className="w-3.5 h-3.5" />
                        {executing ? 'Executing Paper Order…' : '⚡ Execute 1-Click Paper Order'}
                      </Button>
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t bg-muted/30 flex justify-between items-center text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <ShieldAlert className="w-3.5 h-3.5 text-primary" /> FSM Guard: Deterministic state-machine active (TTL {sig?.ttl_seconds || 300}s)
          </span>
          <Button variant="outline" size="sm" onClick={onClose} className="h-7 text-xs">
            Close Dossier
          </Button>
        </div>
      </div>
    </div>
  );
}
