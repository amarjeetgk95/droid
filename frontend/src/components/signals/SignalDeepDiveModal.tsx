'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { formatDateTime, safeNum, safeStr } from '@/lib/signal-utils';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Gauge,
  ShieldAlert,
  X,
  Zap,
} from 'lucide-react';

interface Props {
  signalId: string | null;
  onClose: () => void;
  onPaperExecuted?: (result: any) => void;
}

function KV({ label, value, mono = true }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 border-b border-border/50 last:border-0">
      <span className="text-[11px] text-muted-foreground shrink-0 pt-0.5">{label}</span>
      <span className={`text-[11px] text-right break-all text-foreground ${mono ? 'font-mono' : ''}`}>{value ?? '—'}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-card/60 p-4 space-y-2">
      <div className="text-xs font-bold uppercase tracking-wider text-foreground border-b pb-2">{title}</div>
      {children}
    </div>
  );
}

function fmtVal(v: any): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') return Number.isFinite(v) ? v.toLocaleString('en-IN') : '—';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

export function SignalDeepDiveModal({ signalId, onClose, onPaperExecuted }: Props) {
  const market = useOptionalMarketDataContext();
  const isMarketClosed = market?.marketStatus?.session === 'CLOSED' || market?.marketStatus?.is_trading_day === false;

  const [data, setData] = useState<any>(null);
  const [audit, setAudit] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [customLots, setCustomLots] = useState<string>('2');
  const [paperResult, setPaperResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    if (!signalId) return;
    setLoading(true);
    setError(null);
    setAudit(null);
    api
      .getSignalDeepDive(signalId)
      .then((res) => {
        setData(res);
        if (res.signal?.paper_order) setPaperResult(res.signal.paper_order);
      })
      .catch((err) => setError(err.message || 'Failed to load signal deep dive'))
      .finally(() => setLoading(false));
    // Best-effort: single-signal audit ledger (PnL, fills, MTM). Never blocks dossier.
    api
      .getSingleSignalAudit(signalId)
      .then((res) => setAudit(res))
      .catch(() => setAudit(null));
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
  const fsmState = sig?.fsm_state || 'ARMED';
  const isExpired = ['EXPIRED', 'CLOSED', 'INVALIDATED', 'TARGET_2_HIT', 'STOP_LOSS_HIT', 'TIME_STOP_HIT', 'RUNNER_TIME_STOP_HIT'].includes(fsmState);
  const isCall = sig?.direction?.includes('CALL');
  const dirColor = isCall ? 'text-emerald-600 bg-emerald-500/10 border-emerald-500/30' : 'text-red-600 bg-red-500/10 border-red-500/30';
  const conf = data?.confluence ?? sig?.confluence_breakdown ?? {};
  const levels = data?.levels ?? {};
  const sizing = data?.position_sizing_preview ?? {};
  const fsmHistory: any[] = data?.fsm_history?.length ? data.fsm_history : (sig?.state_history ?? []);
  const opt = data?.option_contract ?? sig?.option_contract ?? null;
  const livePrice = data?.current_market_price;

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
                {sig?.created_at_utc ? (
                  <> • Generated: <span className="font-mono font-medium text-foreground" title="Generated Date & Time (IST)">{formatDateTime(sig.created_at_utc)}</span></>
                ) : null}
                {livePrice ? (
                  <> • Live: <span className="font-mono font-medium text-foreground">₹{Number(livePrice).toLocaleString('en-IN')}</span></>
                ) : null}
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
              {/* 1. KEY PRICE LEVELS BAR */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-xl border bg-secondary/30">
                  <span className="text-[11px] text-muted-foreground font-medium">Trigger / Entry Zone</span>
                  <div className="text-sm font-mono font-bold mt-1 text-foreground">₹{Number(sig.trigger).toLocaleString('en-IN')}</div>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    Range: {sig.entry_min} - {sig.entry_max}
                  </span>
                </div>
                <div className="p-3 rounded-xl border bg-destructive/10 border-destructive/20">
                  <span className="text-[11px] text-destructive font-medium">Stop Loss (SL)</span>
                  <div className="text-sm font-mono font-bold text-destructive mt-1">₹{Number(sig.stop_loss).toLocaleString('en-IN')}</div>
                  <span className="text-[10px] text-muted-foreground font-mono">Risk: -{Number(sig.risk_points).toFixed(1)} pts</span>
                </div>
                <div className="p-3 rounded-xl border bg-emerald-500/10 border-emerald-500/20">
                  <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">Target 1 (1.5R)</span>
                  <div className="text-sm font-mono font-bold text-emerald-600 dark:text-emerald-400 mt-1">₹{Number(sig.target_1).toLocaleString('en-IN')}</div>
                  <span className="text-[10px] text-muted-foreground font-mono">Book 50% (+{(Number(sig.risk_points) * 1.5).toFixed(1)} pts)</span>
                </div>
                <div className="p-3 rounded-xl border bg-emerald-600/10 border-emerald-600/30">
                  <span className="text-[11px] text-emerald-700 dark:text-emerald-300 font-medium">Target 2 (3.0R)</span>
                  <div className="text-sm font-mono font-bold text-emerald-700 dark:text-emerald-300 mt-1">₹{Number(sig.target_2).toLocaleString('en-IN')}</div>
                  <span className="text-[10px] text-muted-foreground font-mono">Runner (+{(Number(sig.risk_points) * 3.0).toFixed(1)} pts)</span>
                </div>
              </div>

              {/* 2. THE 6-STAGE SIGNAL GENERATION ARCHITECTURE PIPELINE */}
              <div className="rounded-2xl border border-border bg-card/60 p-4 space-y-3">
                <div className="flex items-center justify-between border-b pb-2">
                  <div className="flex items-center gap-2">
                    <Gauge className="w-4 h-4 text-primary" />
                    <span className="text-xs font-bold uppercase tracking-wider text-foreground">
                      Complete Signal Generation & Validation Pipeline
                    </span>
                  </div>
                  <Badge variant="outline" className="text-[10px] font-mono text-emerald-600 border-emerald-500/30 bg-emerald-500/10 font-bold">
                    {sig.confidence}% Fused Score
                  </Badge>
                </div>

                <div className="space-y-2.5 font-mono text-xs">
                  {/* Stage 1 */}
                  <div className="p-2.5 rounded-xl bg-muted/40 border space-y-1">
                    <div className="flex items-center justify-between text-foreground font-semibold">
                      <span className="flex items-center gap-2">
                        <span className="h-5 w-5 rounded-full bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center text-[10px] font-bold">1</span>
                        Live Market Tick Ingestion & Trust Gate
                      </span>
                      <span className={isExpired ? "text-amber-500 font-bold text-[11px]" : "text-emerald-600 dark:text-emerald-400 text-[11px]"}>
                        {isExpired ? `⚠ ${fsmState}` : "✓ Verified Live"}
                      </span>
                    </div>
                    <p className="text-muted-foreground text-[11px] pl-7">
                      {isExpired
                        ? `Signal timestamp: ${formatDateTime(sig?.created_at_utc)}. Market session has concluded (FSM Status: ${fsmState}).`
                        : `Tick received from live data stream${sig?.created_at_utc ? ` on ${formatDateTime(sig.created_at_utc)}` : ''}. Active market session validated (NSE Hours 09:15 - 15:30 IST).`}
                    </p>
                    {livePrice ? (
                      <p className="text-muted-foreground text-[11px] pl-7">
                        Current market: ₹{Number(livePrice).toLocaleString('en-IN')} • Trigger: ₹{Number(sig.trigger).toLocaleString('en-IN')}
                      </p>
                    ) : null}
                  </div>

                  {/* Stage 2 */}
                  <div className="p-2.5 rounded-xl bg-muted/40 border space-y-1">
                    <div className="flex items-center justify-between text-foreground font-semibold">
                      <span className="flex items-center gap-2">
                        <span className="h-5 w-5 rounded-full bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center text-[10px] font-bold">2</span>
                        Algorithmic Strategy Detection: {sig.strategy}
                      </span>
                      <span className="text-emerald-600 dark:text-emerald-400 text-[11px]">✓ Condition Met</span>
                    </div>
                    <p className="text-muted-foreground text-[11px] pl-7">
                      Spot price (₹{Number(sig.spot_price).toLocaleString('en-IN')}) matched {sig.timeframe || '5M'} quant strategy criteria with volume expansion.
                    </p>
                    {sig.rationale?.length > 0 && (
                      <ul className="pl-7 space-y-0.5 text-muted-foreground text-[10px] list-disc list-inside">
                        {sig.rationale.map((r: string, i: number) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {/* Stage 3 */}
                  <div className="p-2.5 rounded-xl bg-muted/40 border space-y-1">
                    <div className="flex items-center justify-between text-foreground font-semibold">
                      <span className="flex items-center gap-2">
                        <span className="h-5 w-5 rounded-full bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center text-[10px] font-bold">3</span>
                        Trigger Integrity & Edge Gate
                      </span>
                      <span className="text-emerald-600 dark:text-emerald-400 text-[11px]">✓ Edge Verified</span>
                    </div>
                    <p className="text-muted-foreground text-[11px] pl-7">
                      Trigger set at ₹{Number(sig.trigger).toLocaleString('en-IN')}. Verified minimum edge gap (&gt; 0.05% of spot) to eliminate born-triggered noise.
                    </p>
                  </div>

                  {/* Stage 4 */}
                  <div className="p-2.5 rounded-xl bg-muted/40 border space-y-2">
                    <div className="flex items-center justify-between text-foreground font-semibold">
                      <span className="flex items-center gap-2">
                        <span className="h-5 w-5 rounded-full bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center text-[10px] font-bold">4</span>
                        5-Factor Confluence Fusion Engine
                      </span>
                      <span className="text-emerald-600 dark:text-emerald-400 text-[11px] font-bold">{sig.confidence}% Fused</span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5 pl-7 text-[10px]">
                      <div className="p-1.5 rounded-lg border bg-secondary/30">
                        <div className="text-muted-foreground">Technical (40%)</div>
                        <div className="font-bold text-foreground mt-0.5">{conf?.technical ?? sig.confluence_breakdown?.technical ?? '—'}%</div>
                      </div>
                      <div className="p-1.5 rounded-lg border bg-secondary/30">
                        <div className="text-muted-foreground">Multi-TF (20%)</div>
                        <div className="font-bold text-foreground mt-0.5">{conf?.mtf ?? sig.confluence_breakdown?.mtf ?? '—'}%</div>
                      </div>
                      <div className="p-1.5 rounded-lg border bg-secondary/30">
                        <div className="text-muted-foreground">F&O OI/PCR (20%)</div>
                        <div className="font-bold text-foreground mt-0.5">{conf?.fno ?? sig.confluence_breakdown?.fno ?? '—'}%</div>
                      </div>
                      <div className="p-1.5 rounded-lg border bg-secondary/30">
                        <div className="text-muted-foreground">Regime (10%)</div>
                        <div className="font-bold text-foreground mt-0.5">{conf?.regime ?? sig.confluence_breakdown?.regime ?? '—'}%</div>
                      </div>
                      <div className="p-1.5 rounded-lg border bg-secondary/30">
                        <div className="text-muted-foreground">AI Advisory (10%)</div>
                        <div className="font-bold text-foreground mt-0.5">{conf?.ai ?? sig.confluence_breakdown?.ai ?? '—'}%</div>
                      </div>
                    </div>
                    {conf && Object.keys(conf).length > 0 && (
                      <p className="text-muted-foreground text-[10px] pl-7 font-mono break-all">
                        Full breakdown: {JSON.stringify(conf)}
                      </p>
                    )}
                  </div>

                  {/* Stage 5 */}
                  <div className="p-2.5 rounded-xl bg-muted/40 border space-y-1">
                    <div className="flex items-center justify-between text-foreground font-semibold">
                      <span className="flex items-center gap-2">
                        <span className="h-5 w-5 rounded-full bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center text-[10px] font-bold">5</span>
                        Option Contract Master & 2% Risk Model
                      </span>
                      <span className="text-emerald-600 dark:text-emerald-400 text-[11px]">✓ Resolved</span>
                    </div>
                    <p className="text-muted-foreground text-[11px] pl-7">
                      Matched <code className="text-foreground font-bold">{opt?.broker_symbol || `${sig.underlying} ATM`}</code> ({opt?.lot_size || 75} Qty/Lot, Expiry: {opt?.expiry_date || 'Weekly'}). Position sized to 2% portfolio risk capital.
                    </p>
                  </div>

                  {/* Stage 6 */}
                  <div className="p-2.5 rounded-xl bg-muted/40 border space-y-1">
                    <div className="flex items-center justify-between text-foreground font-semibold">
                      <span className="flex items-center gap-2">
                        <span className="h-5 w-5 rounded-full bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center text-[10px] font-bold">6</span>
                        Deterministic FSM Lifecycle
                      </span>
                      <span className={isExpired ? "text-muted-foreground text-[11px]" : "text-emerald-600 dark:text-emerald-400 text-[11px]"}>
                        State: {fsmState}
                      </span>
                    </div>
                    <p className="text-muted-foreground text-[11px] pl-7">
                      {isExpired
                        ? `Signal has concluded its lifecycle and transitioned to ${fsmState}. No further automated or paper executions permitted.`
                        : `Active state machine tracking with TTL (${sig?.ttl_seconds || 300}s). T1 hit automatically triggers 50% profit booking and moves Stop Loss to cost (Breakeven).`}
                    </p>
                  </div>
                </div>
              </div>

              {/* 3. FULL SIGNAL DETAIL — identity, timing, risk */}
              <Section title="Signal Detail — Identity & Timing">
                <div className="grid sm:grid-cols-2 gap-x-6">
                  <div>
                    <KV label="Signal ID" value={safeStr(sig.signal_id)} />
                    <KV label="Underlying" value={safeStr(sig.underlying)} />
                    <KV label="Strategy" value={safeStr(sig.strategy)} />
                    <KV label="Direction" value={safeStr(sig.direction)} />
                    <KV label="Timeframe" value={safeStr(sig.timeframe)} />
                    <KV label="Signal type / Desk" value={`${safeStr(sig.signal_type)}${sig.is_scalp ? ' / SCALP' : ''}`} />
                    <KV label="Confidence" value={`${safeStr(sig.confidence)}%`} />
                  </div>
                  <div>
                    <KV label="Spot at creation" value={`₹${safeNum(sig.spot_price)}`} />
                    <KV label="Entry range" value={`₹${safeNum(sig.entry_min)} – ₹${safeNum(sig.entry_max)}`} />
                    <KV label="Risk points" value={`${safeNum(sig.risk_points, 1)} pts`} />
                    <KV label="R:R T1 / T2" value={`${safeNum(sig.risk_reward_t1, 2)} / ${safeNum(sig.risk_reward_t2, 2)}`} />
                    <KV label="Risk R (1R)" value={fmtVal(sig.risk_r)} />
                    <KV label="TTL" value={`${safeStr(sig.ttl_seconds)}s`} />
                    <KV label="Created" value={formatDateTime(sig.created_at_utc)} />
                    <KV label="Expires" value={formatDateTime(sig.expires_at_utc)} />
                    <KV label="Triggered" value={sig.triggered_at_utc ? formatDateTime(sig.triggered_at_utc) : '—'} />
                    <KV label="Confirmed" value={sig.confirmed_at_utc ? formatDateTime(sig.confirmed_at_utc) : '—'} />
                    <KV label="Last updated" value={sig.last_updated_utc ? formatDateTime(sig.last_updated_utc) : '—'} />
                  </div>
                </div>
                {sig.rationale?.length > 0 && (
                  <div className="pt-2">
                    <div className="text-[11px] font-semibold text-foreground mb-1">Why this signal fired (rationale)</div>
                    <ul className="space-y-1 text-[11px] text-muted-foreground list-disc list-inside">
                      {sig.rationale.map((r: string, i: number) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </Section>

              {/* 4. OPTION CONTRACT — full master */}
              <Section title="Option Contract — Full Master">
                {opt && typeof opt === 'object' && Object.keys(opt).length > 0 ? (
                  <div className="grid sm:grid-cols-2 gap-x-6">
                    <div>
                      <KV label="Broker symbol" value={safeStr(opt.broker_symbol)} />
                      <KV label="Instrument ID" value={safeStr(opt.instrument_id)} />
                      <KV label="Underlying" value={safeStr(opt.underlying ?? sig.underlying)} />
                      <KV label="Strike" value={safeStr(opt.strike)} />
                      <KV label="Option type" value={safeStr(opt.option_type)} />
                      <KV label="Exchange" value={safeStr(opt.exchange)} />
                    </div>
                    <div>
                      <KV label="Expiry" value={safeStr(opt.expiry_date)} />
                      <KV label="Expiry type" value={safeStr(opt.expiry_type)} />
                      <KV label="Lot size" value={safeStr(opt.lot_size)} />
                      <KV label="Tick size" value={safeStr(opt.tick_size)} />
                      <KV label="Strike interval" value={safeStr(opt.strike_interval)} />
                      <KV label="Active" value={opt.active === undefined ? '—' : opt.active ? 'Yes' : 'No'} />
                    </div>
                  </div>
                ) : (
                  <p className="text-[11px] text-muted-foreground font-mono">No option contract resolved for this signal.</p>
                )}
              </Section>

              {/* 5. SIZING, RISK, LEVELS */}
              <Section title="Position Sizing, Risk & Levels">
                <div className="grid sm:grid-cols-2 gap-x-6">
                  <div>
                    <KV label="Lots" value={fmtVal(sig.lots)} />
                    <KV label="Quantity" value={fmtVal(sig.quantity)} />
                    <KV label="Max rupee loss" value={sig.max_rupee_loss ? `₹${Number(sig.max_rupee_loss).toLocaleString('en-IN')}` : '—'} />
                    <KV label="Current market" value={livePrice ? `₹${Number(livePrice).toLocaleString('en-IN')}` : '—'} />
                    <KV label="Entry range (API)" value={levels?.entry_range ? levels.entry_range.map((x: number) => `₹${Number(x).toLocaleString('en-IN')}`).join(' – ') : '—'} />
                  </div>
                  <div>
                    <KV label="Trigger (API)" value={levels?.trigger !== undefined ? `₹${Number(levels.trigger).toLocaleString('en-IN')}` : '—'} />
                    <KV label="Stop (API)" value={levels?.stop_loss !== undefined ? `₹${Number(levels.stop_loss).toLocaleString('en-IN')}` : '—'} />
                    <KV label="T1 / T2 (API)" value={levels?.target_1 !== undefined ? `₹${Number(levels.target_1).toLocaleString('en-IN')} / ₹${Number(levels.target_2).toLocaleString('en-IN')}` : '—'} />
                    <KV label="1L account sizing" value={sizing?.account_1lakh ? JSON.stringify(sizing.account_1lakh) : '—'} />
                    <KV label="5L account sizing" value={sizing?.account_5lakh ? JSON.stringify(sizing.account_5lakh) : '—'} />
                  </div>
                </div>
              </Section>

              {/* 6. EXECUTION & OUTCOME */}
              <Section title="Execution, Breakeven & Outcome">
                <div className="grid sm:grid-cols-2 gap-x-6">
                  <div>
                    <KV label="FSM state" value={safeStr(sig.fsm_state)} />
                    <KV label="Outcome status" value={safeStr(sig.outcome_status)} />
                    <KV label="Terminal outcome" value={safeStr(sig.terminal_outcome)} />
                    <KV label="Entry price (fill domain)" value={fmtVal(sig.entry_price)} />
                    <KV label="Actual fill price" value={fmtVal(sig.actual_fill_price)} />
                    <KV label="Exit price" value={fmtVal(sig.exit_price)} />
                    <KV label="Realized R" value={fmtVal(sig.realized_rr)} />
                    <KV label="Realized R gross / net" value={`${fmtVal(sig.realized_rr_gross)} / ${fmtVal(sig.realized_rr_net)}`} />
                  </div>
                  <div>
                    <KV label="Initial SL" value={fmtVal(sig.initial_stop_loss)} />
                    <KV label="Current SL" value={fmtVal(sig.current_stop_loss)} />
                    <KV label="Breakeven active" value={sig.breakeven_activated ? 'Yes' : 'No'} />
                    <KV label="BE trigger / activation" value={`${fmtVal(sig.breakeven_trigger_price)} / ${fmtVal(sig.breakeven_activation_price)}`} />
                    <KV label="T1 hit / fill time" value={`${fmtVal(sig.t1_hit)}${sig.t1_fill_timestamp ? ` @ ${formatDateTime(sig.t1_fill_timestamp)}` : ''}`} />
                    <KV label="T2 hit" value={fmtVal(sig.t2_hit)} />
                    <KV label="T1 realized qty" value={fmtVal(sig.t1_realized_qty)} />
                    <KV label="Intended / remaining qty" value={`${fmtVal(sig.intended_qty)} / ${fmtVal(sig.remaining_qty)}`} />
                    <KV label="Time stop (s / at)" value={`${fmtVal(sig.time_stop_seconds)}${sig.time_stop_at_utc ? ` @ ${formatDateTime(sig.time_stop_at_utc)}` : ''}`} />
                    <KV label="Runner stop at" value={sig.runner_time_stop_at_utc ? formatDateTime(sig.runner_time_stop_at_utc) : '—'} />
                    <KV label="Regime at confirm" value={safeStr(sig.regime_at_confirmation)} />
                  </div>
                </div>
                {sig.cost_breakdown_r && (
                  <p className="text-[10px] font-mono text-muted-foreground break-all pt-1">
                    Cost breakdown (R): {JSON.stringify(sig.cost_breakdown_r)}
                  </p>
                )}
                {(sig.greeks || sig.expected_move || sig.ai_research || sig.path_simulation) && (
                  <div className="pt-1 space-y-1">
                    {sig.greeks && <p className="text-[10px] font-mono text-muted-foreground break-all">Greeks: {JSON.stringify(sig.greeks)}</p>}
                    {sig.expected_move && <p className="text-[10px] font-mono text-muted-foreground break-all">Expected move: {JSON.stringify(sig.expected_move)}</p>}
                    {sig.ai_research && <p className="text-[10px] font-mono text-muted-foreground break-all">AI research: {JSON.stringify(sig.ai_research)}</p>}
                    {sig.path_simulation && <p className="text-[10px] font-mono text-muted-foreground break-all">Path sim: {JSON.stringify(sig.path_simulation)}</p>}
                  </div>
                )}
              </Section>

              {/* 7. FSM HISTORY TIMELINE */}
              <Section title={`FSM History — ${fsmHistory.length} transitions`}>
                {fsmHistory.length === 0 ? (
                  <p className="text-[11px] text-muted-foreground font-mono">No state transitions recorded.</p>
                ) : (
                  <div className="space-y-2">
                    {fsmHistory.map((h: any, i: number) => (
                      <div key={h.transition_id ?? i} className="flex items-start gap-3 text-[11px] font-mono">
                        <span className="mt-0.5 h-2 w-2 rounded-full bg-primary shrink-0" />
                        <div className="flex-1">
                          <div className="text-foreground font-semibold">
                            {safeStr(h.from_state)} → {safeStr(h.to_state)}
                          </div>
                          <div className="text-muted-foreground">
                            {safeStr(h.reason_code)} • {h.processed_timestamp ? formatDateTime(h.processed_timestamp) : safeStr(h.timestamp)}
                            {h.market_price ? ` • @ ₹${h.market_price}` : ''}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Section>

              {/* 8. AUDIT LEDGER RECORD */}
              <Section title="Audit Ledger — Paper P&L Record">
                {!audit ? (
                  <p className="text-[11px] text-muted-foreground font-mono">No audit record yet (signal not paper-executed, or ledger pending).</p>
                ) : (
                  <div className="grid sm:grid-cols-2 gap-x-6">
                    <div>
                      <KV label="Audit ID" value={safeStr(audit.audit_id)} />
                      <KV label="Status" value={safeStr(audit.status)} />
                      <KV label="Outcome" value={safeStr(audit.outcome_label ?? audit.exit_reason)} />
                      <KV label="Side / qty" value={`${safeStr(audit.paper_side)} / ${fmtVal(audit.quantity)}`} />
                      <KV label="Fill price" value={audit.actual_fill_price ? `₹${safeNum(audit.actual_fill_price)}` : '—'} />
                      <KV label="Exit price" value={audit.exit_price ? `₹${safeNum(audit.exit_price)}` : '—'} />
                    </div>
                    <div>
                      <KV label="Realized P&L" value={audit.actual_pnl_inr !== undefined ? `₹${Number(audit.actual_pnl_inr).toLocaleString('en-IN')} (${safeNum(audit.actual_pnl_points, 1)} pts)` : '—'} />
                      <KV label="Unrealized / MTM" value={audit.unrealized_pnl_inr !== undefined ? `₹${Number(audit.unrealized_pnl_inr).toLocaleString('en-IN')}` : '—'} />
                      <KV label="Total P&L" value={audit.total_pnl_inr !== undefined ? `₹${Number(audit.total_pnl_inr).toLocaleString('en-IN')}` : '—'} />
                      <KV label="Holding time" value={safeStr(audit.holding_time_str ?? audit.live_duration_str)} />
                      <KV label="Executed" value={audit.executed_at_utc ? formatDateTime(audit.executed_at_utc) : '—'} />
                      <KV label="Exited" value={audit.exited_at_utc ? formatDateTime(audit.exited_at_utc) : '—'} />
                    </div>
                  </div>
                )}
                {paperResult && (
                  <p className="text-[10px] font-mono text-muted-foreground break-all pt-1">
                    Paper order: {JSON.stringify(paperResult)}
                  </p>
                )}
              </Section>

              {/* 9. EXECUTION CONTROLS & STATUS */}
              <div className="rounded-xl border p-4 bg-muted/20 flex flex-col sm:flex-row items-center justify-between gap-4">
                {paperResult ? (
                  <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300 font-mono text-xs bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-3 w-full">
                    <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
                    <div>
                      <div className="font-bold">Paper Trade Active: {paperResult.side || 'BUY'} {paperResult.quantity} Qty @ ₹{Number(paperResult.fill_price || sig.trigger).toLocaleString('en-IN')}</div>
                      <div className="text-[11px] text-muted-foreground">Order ID: {paperResult.order_id || 'simulated'} • Live MTM updating in Ledger</div>
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
                        ({(parseInt(customLots, 10) || 1) * (opt?.lot_size || 75)} Qty)
                      </span>
                    </div>
                    <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
                      <Button
                        size="sm"
                        className={`${isMarketClosed ? 'bg-muted text-muted-foreground cursor-not-allowed' : 'bg-emerald-600 hover:bg-emerald-700 text-white'} gap-1.5 w-full sm:w-auto`}
                        onClick={handleExecute}
                        disabled={executing || isMarketClosed}
                        title={isMarketClosed ? 'Market is closed. Orders cannot be executed.' : 'Execute 1-Click Paper Order'}
                      >
                        <Zap className="w-3.5 h-3.5" />
                        {executing ? 'Executing Paper Order…' : isMarketClosed ? 'Market Closed' : '⚡ Execute 1-Click Paper Order'}
                      </Button>
                    </div>
                  </>
                )}
              </div>

              {/* 10. RAW JSON FOR LEARNING */}
              <div className="rounded-2xl border border-border bg-muted/20 p-3">
                <button
                  onClick={() => setShowRaw((v) => !v)}
                  className="text-[11px] font-mono font-bold text-primary hover:underline"
                >
                  {showRaw ? '▾ Hide full raw signal JSON (for learning)' : '▸ Show full raw signal JSON (for learning)'}
                </button>
                {showRaw && (
                  <pre className="mt-2 max-h-96 overflow-auto text-[10px] font-mono bg-background border rounded-lg p-3 whitespace-pre-wrap break-all">
                    {JSON.stringify(data, null, 2)}
                  </pre>
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
