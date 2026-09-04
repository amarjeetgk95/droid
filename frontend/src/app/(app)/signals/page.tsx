'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { SignalCard, type SignalDTO } from '@/components/signals/SignalCard';
import { SignalScannerTable } from '@/components/signals/SignalScannerTable';
import { SignalPerformanceView } from '@/components/signals/SignalPerformanceView';
import { GenerateSignalForm } from '@/components/signals/GenerateSignalForm';
import { SignalDeepDiveModal } from '@/components/signals/SignalDeepDiveModal';
import { SignalAuditTable, type AuditTradeRecord, type AuditSummary } from '@/components/signals/SignalAuditTable';
import {
  Activity,
  AlertTriangle,
  Award,
  Bell,
  BellOff,
  CheckCircle2,
  Clock,
  Crosshair,
  Grid,
  Layers,
  List,
  Radio,
  RefreshCw,
  Settings as SettingsIcon,
  Sparkles,
  Target,
  Volume2,
  VolumeX,
  Zap,
} from 'lucide-react';
import Link from 'next/link';

type FilterInstrument = 'ALL' | 'NIFTY' | 'BANKNIFTY' | 'SENSEX';
type FilterDesk = 'ALL' | 'SCALP' | 'INTRADAY';
type FilterStrategy =
  | 'ALL'
  | 'BREAKOUT'
  | 'MEAN_REVERSION'
  | 'TREND_PULLBACK'
  | 'GAMMA_SQUEEZE'
  | 'ORB'
  | 'VWAP_SCALP'
  | 'MICRO_MOMENTUM'
  | 'EMA_RIBBON'
  | 'GAMMA_SPIKE';

// Web Audio synthesizer chime for low-latency alerts without external mp3 files
function playAlertChime(isWin = false, isScalp = false) {
  try {
    const AudioContext = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    if (isScalp) {
      // High-frequency dual beep for fast scalping alerts
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(880.0, ctx.currentTime);
      osc.frequency.setValueAtTime(1174.66, ctx.currentTime + 0.08);
      gain.gain.setValueAtTime(0.18, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
    } else {
      osc.type = isWin ? 'triangle' : 'sine';
      osc.frequency.setValueAtTime(isWin ? 587.33 : 440.0, ctx.currentTime);
      if (isWin) {
        osc.frequency.exponentialRampToValueAtTime(880.0, ctx.currentTime + 0.15);
      } else {
        osc.frequency.exponentialRampToValueAtTime(659.25, ctx.currentTime + 0.12);
      }
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
    }

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + (isScalp ? 0.25 : 0.35));
  } catch {}
}

export default function SignalsPage() {
  const [active, setActive] = useState<SignalDTO[]>([]);
  const [scannerData, setScannerData] = useState<SignalDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [scannerLoading, setScannerLoading] = useState(false);

  const [filterDesk, setFilterDesk] = useState<FilterDesk>('ALL');
  const [filterInstr, setFilterInstr] = useState<FilterInstrument>('ALL');
  const [filterStrat, setFilterStrat] = useState<FilterStrategy>('ALL');
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');
  const [soundEnabled, setSoundEnabled] = useState<boolean>(true);

  const [inspectSignalId, setInspectSignalId] = useState<string | null>(null);
  const [perfSummary, setPerfSummary] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const [auditTrades, setAuditTrades] = useState<AuditTradeRecord[]>([]);
  const [auditSummary, setAuditSummary] = useState<AuditSummary | null>(null);
  const [auditLoading, setAuditLoading] = useState<boolean>(false);

  const knownSignalIds = useRef<Set<string>>(new Set());

  // Fetch active signals
  const fetchActive = useCallback(
    async (showLoading = true) => {
      if (showLoading) setLoading(true);
      setError(null);
      try {
        const res: any = await api.getSignalsActive({
          instrument: filterInstr !== 'ALL' ? filterInstr : undefined,
          strategy: filterStrat !== 'ALL' ? filterStrat : undefined,
          desk: filterDesk !== 'ALL' ? filterDesk : undefined,
        });
        const list: SignalDTO[] = res.signals || res.data?.signals || [];
        
        // Check if a truly new confirmed signal arrived -> play chime
        if (soundEnabled && knownSignalIds.current.size > 0) {
          const newConfirmed = list.filter(
            (s) => !knownSignalIds.current.has(s.signal_id) && (s.fsm_state === 'CONFIRMED' || s.fsm_state.includes('TARGET'))
          );
          if (newConfirmed.length > 0) {
            const isScalp = newConfirmed.some((s) => s.is_scalp || s.signal_type === 'SCALP');
            playAlertChime(true, isScalp);
          }
        }
        list.forEach((s) => knownSignalIds.current.add(s.signal_id));
        setActive(list);
      } catch (e: any) {
        setError(e.message || 'Failed to load quantitative signals');
      } finally {
        setLoading(false);
      }
    },
    [filterInstr, filterStrat, filterDesk, soundEnabled],
  );

  // Run full scanner
  const fetchScanner = useCallback(async () => {
    setScannerLoading(true);
    try {
      const res: any = await api.getSignalsScanner();
      const list: SignalDTO[] = res.active_signals || res.new_signals || [];
      setScannerData(list);
    } catch {
    } finally {
      setScannerLoading(false);
    }
  }, []);

  // Fetch Signal Audit Ledger without flickering background spinners
  const fetchAudit = useCallback(async (showLoading = false) => {
    if (showLoading) setAuditLoading(true);
    try {
      const res: any = await api.getSignalsAudit();
      setAuditTrades(res.trades || []);
      setAuditSummary(res.summary || null);
    } catch {
    } finally {
      if (showLoading) setAuditLoading(false);
    }
  }, []);

  // Quick stats
  useEffect(() => {
    api
      .getSignalsPerformance()
      .then((r) => setPerfSummary(r))
      .catch(() => {});
  }, []);

  // Polling with tab-visibility backoff (3s interval)
  useEffect(() => {
    fetchActive(true);
    fetchScanner();
    fetchAudit(true);

    let timer: ReturnType<typeof setInterval> | null = null;
    timer = setInterval(() => {
      if (!document.hidden) {
        void fetchActive(false);
        void fetchAudit(false);
      }
    }, 3000);

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [fetchActive, fetchScanner, fetchAudit]);

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto pb-12">
      {/* ── HEADER & LIVE COCKPIT STATUS ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <Radio className="w-5 h-5 text-primary" /> Signal Centre
            <Badge className="bg-primary text-primary-foreground font-mono text-[10px]">QUANT RADAR</Badge>
            <span className="text-xs font-normal text-muted-foreground ml-2 hidden md:inline">
              Deterministic Index Options Intelligence (NIFTY • BANKNIFTY • SENSEX)
            </span>
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Real-time multi-strategy scanner with FSM lifecycle management and FYERS execution parity.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSoundEnabled(!soundEnabled)}
            className={`h-8 text-xs gap-1 ${soundEnabled ? 'text-primary' : 'text-muted-foreground'}`}
            title={soundEnabled ? 'Audio Chime Alerts Enabled' : 'Audio Muted'}
          >
            {soundEnabled ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">{soundEnabled ? 'Audio Alerts' : 'Muted'}</span>
          </Button>

          <Button variant="outline" size="sm" onClick={() => fetchActive(true)} disabled={loading} className="h-8 text-xs gap-1">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>

          <Link href="/settings">
            <Button variant="ghost" size="sm" className="h-8 text-xs gap-1">
              <SettingsIcon className="w-3.5 h-3.5" /> Settings
            </Button>
          </Link>
        </div>
      </div>

      {/* ── TOP KPI SUMMARY STRIP (DUAL-DESK PERFORMANCE) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="bg-secondary/20">
          <CardContent className="p-3 flex items-center justify-between">
            <div>
              <span className="text-[11px] text-muted-foreground font-medium">Active Radar Setups</span>
              <div className="text-lg font-bold font-mono text-primary">{active.length} Signals</div>
            </div>
            <Activity className="w-5 h-5 text-primary/60" />
          </CardContent>
        </Card>

        <Card className="bg-amber-500/5 border-amber-500/20">
          <CardContent className="p-3 flex items-center justify-between">
            <div>
              <span className="text-[11px] text-amber-700 dark:text-amber-400 font-medium flex items-center gap-1">
                <Zap className="w-3 h-3 text-amber-500" /> ⚡ Scalp Win Rate (1M)
              </span>
              <div className="text-lg font-bold font-mono text-amber-600">
                {perfSummary?.scalp_summary?.win_rate_pct !== undefined
                  ? `${perfSummary.scalp_summary.win_rate_pct}%`
                  : perfSummary?.win_rate_pct !== undefined
                    ? `${perfSummary.win_rate_pct}%`
                    : '—'}
              </div>
            </div>
            <Target className="w-5 h-5 text-amber-500/60" />
          </CardContent>
        </Card>

        <Card className="bg-indigo-500/5 border-indigo-500/20">
          <CardContent className="p-3 flex items-center justify-between">
            <div>
              <span className="text-[11px] text-indigo-700 dark:text-indigo-400 font-medium flex items-center gap-1">
                <Layers className="w-3 h-3 text-indigo-500" /> 📊 Intraday Win Rate (5M)
              </span>
              <div className="text-lg font-bold font-mono text-indigo-600">
                {perfSummary?.intraday_summary?.win_rate_pct !== undefined
                  ? `${perfSummary.intraday_summary.win_rate_pct}%`
                  : perfSummary?.win_rate_pct !== undefined
                    ? `${perfSummary.win_rate_pct}%`
                    : '—'}
              </div>
            </div>
            <Award className="w-5 h-5 text-indigo-500/60" />
          </CardContent>
        </Card>

        <Card className="bg-secondary/20">
          <CardContent className="p-3 flex items-center justify-between">
            <div>
              <span className="text-[11px] text-muted-foreground font-medium">Profit Factor</span>
              <div className="text-lg font-bold font-mono">
                {perfSummary?.profit_factor !== undefined ? `${perfSummary.profit_factor}x` : '—'}
              </div>
            </div>
            <Crosshair className="w-5 h-5 text-primary/60" />
          </CardContent>
        </Card>
      </div>

      {/* ── 4 MODULAR TABS ── */}
      <Tabs defaultValue="active" className="w-full">
        <TabsList className="w-full justify-start flex-wrap h-auto bg-muted/60 p-1 rounded-xl">
          <TabsTrigger value="active" className="gap-1.5 text-xs font-semibold py-1.5 px-3">
            <Radio className="w-3.5 h-3.5" /> Active Radar ({active.length})
          </TabsTrigger>
          <TabsTrigger value="scanner" className="gap-1.5 text-xs font-semibold py-1.5 px-3">
            <Layers className="w-3.5 h-3.5" /> Multi-Strategy Scanner Matrix
          </TabsTrigger>
          <TabsTrigger value="studio" className="gap-1.5 text-xs font-semibold py-1.5 px-3">
            <Sparkles className="w-3.5 h-3.5" /> Signal Studio (Auto-Detect)
          </TabsTrigger>
          <TabsTrigger value="performance" className="gap-1.5 text-xs font-semibold py-1.5 px-3">
            <Award className="w-3.5 h-3.5" /> Performance & Attribution
          </TabsTrigger>
          <TabsTrigger value="audit" className="gap-1.5 text-xs font-semibold py-1.5 px-3">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Audit Ledger & Actual P&L
            {auditSummary?.total_pnl_inr !== undefined && (
              <Badge
                variant="outline"
                className={`ml-1 text-[10px] font-mono px-1 py-0 ${
                  auditSummary.total_pnl_inr >= 0
                    ? 'bg-emerald-500/15 text-emerald-600 border-emerald-500/30'
                    : 'bg-rose-500/15 text-rose-600 border-rose-500/30'
                }`}
              >
                {auditSummary.total_pnl_inr >= 0
                  ? `+₹${Math.round(auditSummary.total_pnl_inr).toLocaleString('en-IN')}`
                  : `-₹${Math.round(Math.abs(auditSummary.total_pnl_inr)).toLocaleString('en-IN')}`}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* ── TAB 1: ACTIVE RADAR ── */}
        <TabsContent value="active" className="space-y-4 pt-2">
          {/* Filters & View Toggle Bar */}
          <Card className="p-3 space-y-2.5">
            {/* Top Row: Desk Switcher */}
            <div className="flex items-center justify-between gap-2 pb-2 border-b flex-wrap">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-xs font-semibold text-muted-foreground mr-1">Trading Desk:</span>
                <button
                  onClick={() => {
                    setFilterDesk('ALL');
                    setFilterStrat('ALL');
                  }}
                  className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all ${
                    filterDesk === 'ALL'
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-secondary/60 hover:bg-secondary border-transparent'
                  }`}
                >
                  🌐 All Signals
                </button>
                <button
                  onClick={() => {
                    setFilterDesk('SCALP');
                    setFilterStrat('ALL');
                  }}
                  className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all flex items-center gap-1 ${
                    filterDesk === 'SCALP'
                      ? 'bg-amber-500 text-black border-amber-600 shadow-sm'
                      : 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-600 border-amber-500/30'
                  }`}
                >
                  <Zap className="w-3.5 h-3.5" /> ⚡ Scalp Desk (1M/3M)
                </button>
                <button
                  onClick={() => {
                    setFilterDesk('INTRADAY');
                    setFilterStrat('ALL');
                  }}
                  className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all flex items-center gap-1 ${
                    filterDesk === 'INTRADAY'
                      ? 'bg-indigo-600 text-white border-indigo-700 shadow-sm'
                      : 'bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-600 border-indigo-500/30'
                  }`}
                >
                  <Layers className="w-3.5 h-3.5" /> 📊 Core Intraday (5M/15M)
                </button>
              </div>

              <div className="flex items-center gap-2">
                <div className="flex items-center border rounded-lg overflow-hidden bg-background">
                  <button
                    onClick={() => setViewMode('grid')}
                    className={`p-1.5 ${viewMode === 'grid' ? 'bg-secondary text-primary' : 'text-muted-foreground'}`}
                    title="Grid Card View"
                  >
                    <Grid className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => setViewMode('table')}
                    className={`p-1.5 ${viewMode === 'table' ? 'bg-secondary text-primary' : 'text-muted-foreground'}`}
                    title="Pro Table View"
                  >
                    <List className="w-3.5 h-3.5" />
                  </button>
                </div>
                <span className="text-[11px] text-muted-foreground flex items-center gap-1 font-mono">
                  <Clock className="w-3 h-3" /> Live 3s SSE/Poll
                </span>
              </div>
            </div>

            {/* Bottom Row: Index and Dynamic Strategy Pills */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3 flex-wrap">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-semibold text-muted-foreground">Index:</span>
                  {(['ALL', 'NIFTY', 'BANKNIFTY', 'SENSEX'] as const).map((instr) => (
                    <button
                      key={instr}
                      onClick={() => setFilterInstr(instr)}
                      className={`px-2.5 py-1 text-xs font-bold rounded-lg border transition-all ${
                        filterInstr === instr
                          ? 'bg-primary text-primary-foreground border-primary'
                          : 'bg-secondary/60 hover:bg-secondary border-transparent'
                      }`}
                    >
                      {instr}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs font-semibold text-muted-foreground ml-2">Strategy:</span>
                  {(() => {
                    const scalpStrats = ['ALL', 'VWAP_SCALP', 'MICRO_MOMENTUM', 'EMA_RIBBON', 'GAMMA_SPIKE'] as const;
                    const intradayStrats = ['ALL', 'BREAKOUT', 'MEAN_REVERSION', 'TREND_PULLBACK', 'GAMMA_SQUEEZE', 'ORB'] as const;
                    const allStrats = [
                      'ALL',
                      'VWAP_SCALP',
                      'MICRO_MOMENTUM',
                      'EMA_RIBBON',
                      'GAMMA_SPIKE',
                      'BREAKOUT',
                      'MEAN_REVERSION',
                      'TREND_PULLBACK',
                      'GAMMA_SQUEEZE',
                      'ORB',
                    ] as const;

                    const activeList =
                      filterDesk === 'SCALP'
                        ? scalpStrats
                        : filterDesk === 'INTRADAY'
                          ? intradayStrats
                          : allStrats;

                    return activeList.map((strat) => (
                      <button
                        key={strat}
                        onClick={() => setFilterStrat(strat as FilterStrategy)}
                        className={`px-2 py-0.5 text-[11px] font-mono rounded-md border transition-all ${
                          filterStrat === strat
                            ? 'bg-primary text-primary-foreground border-primary font-bold'
                            : 'bg-secondary/60 hover:bg-secondary border-transparent'
                        }`}
                      >
                        {strat}
                      </button>
                    ));
                  })()}
                </div>
              </div>
            </div>
          </Card>

          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> {error}
            </div>
          )}

          {loading && active.length === 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <Card key={i} className="p-4 space-y-3 animate-pulse">
                  <div className="h-4 bg-muted rounded w-32" />
                  <div className="h-16 bg-muted rounded" />
                </Card>
              ))}
            </div>
          )}

          {!loading && active.length === 0 && !error && (
            <Card className="p-8 text-center space-y-2">
              <div className="text-sm font-semibold">No active setups match criteria</div>
              <p className="text-xs text-muted-foreground max-w-md mx-auto">
                No strategy conditions are currently triggered on {filterInstr} with {filterStrat}. Try running the Multi-Strategy Scanner or generating a setup in the Studio.
              </p>
              <Button size="sm" variant="outline" onClick={() => fetchScanner()} className="mt-2 text-xs gap-1">
                <Zap className="w-3 h-3" /> Scan Universe Now
              </Button>
            </Card>
          )}

          {active.length > 0 && (
            <>
              {viewMode === 'grid' ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {active.map((sig) => (
                    <SignalCard
                      key={sig.signal_id}
                      signal={sig}
                      onInspect={(id) => setInspectSignalId(id)}
                      onPaperExecuted={() => {
                        fetchActive(false);
                        fetchAudit();
                      }}
                    />
                  ))}
                </div>
              ) : (
                <SignalScannerTable
                  signals={active}
                  onInspect={(id) => setInspectSignalId(id)}
                  onRefresh={() => fetchActive(false)}
                  loading={loading}
                />
              )}
            </>
          )}
        </TabsContent>

        {/* ── TAB 2: MULTI-STRATEGY SCANNER MATRIX ── */}
        <TabsContent value="scanner" className="space-y-4 pt-2">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Layers className="w-4 h-4 text-primary" /> Multi-Strategy Radar Matrix
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Simultaneously scans NIFTY, BANKNIFTY, and SENSEX across Breakout, Mean Reversion, Trend Pullback, Gamma Squeeze, and ORB.
                  </CardDescription>
                </div>
                <Button size="sm" onClick={() => fetchScanner()} disabled={scannerLoading} className="h-8 text-xs gap-1">
                  <RefreshCw className={`w-3 h-3 ${scannerLoading ? 'animate-spin' : ''}`} />
                  {scannerLoading ? 'Scanning Universe…' : 'Run Full Scan'}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <SignalScannerTable
                signals={scannerData.length > 0 ? scannerData : active}
                onInspect={(id) => setInspectSignalId(id)}
                onRefresh={fetchScanner}
                loading={scannerLoading}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── TAB 3: SIGNAL STUDIO (BUILDER) ── */}
        <TabsContent value="studio" className="pt-2">
          <GenerateSignalForm
            onGenerated={() => {
              fetchActive(false);
              fetchScanner();
            }}
          />
        </TabsContent>

        {/* ── TAB 4: PERFORMANCE & ATTRIBUTION ── */}
        <TabsContent value="performance" className="pt-2">
          <SignalPerformanceView />
        </TabsContent>

        {/* ── TAB 5: AUDIT LEDGER & ACTUAL P&L ── */}
        <TabsContent value="audit" className="pt-2">
          <SignalAuditTable
            trades={auditTrades}
            summary={auditSummary}
            loading={auditLoading}
            onRefresh={fetchAudit}
            onSelectSignal={(sigId) => setInspectSignalId(sigId)}
          />
        </TabsContent>
      </Tabs>

      {/* ── SIGNAL DEEP DIVE MODAL / DRAWER ── */}
      {inspectSignalId && (
        <SignalDeepDiveModal
          signalId={inspectSignalId}
          onClose={() => setInspectSignalId(null)}
          onPaperExecuted={() => {
            fetchActive(false);
            fetchAudit();
          }}
        />
      )}
    </div>
  );
}
