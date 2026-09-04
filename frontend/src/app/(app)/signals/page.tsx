'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { withJitter } from '@/lib/signal-utils';
import { useSignalStream } from '@/hooks/useSignalStream';
import { SignalCard, type SignalDTO } from '@/components/signals/SignalCard';
import { SignalScannerTable } from '@/components/signals/SignalScannerTable';
import { SignalPerformanceView } from '@/components/signals/SignalPerformanceView';
import { GenerateSignalForm } from '@/components/signals/GenerateSignalForm';
import { SignalDeepDiveModal } from '@/components/signals/SignalDeepDiveModal';
import { SignalAuditTable, type AuditTradeRecord, type AuditSummary } from '@/components/signals/SignalAuditTable';
import { SignalErrorBoundary } from '@/components/signals/SignalErrorBoundary';
import { CryptoSignalsCard } from '@/components/crypto/CryptoSignalsCard';
import type { CryptoSignal } from '@/lib/types';
import {
  Activity,
  AlertTriangle,
  Award,
  CheckCircle2,
  Clock,
  Coins,
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
type FilterAssetClass = 'ALL' | 'INDEX' | 'CRYPTO';
type OppSource = 'live' | 'scanner';
type TrackView = 'performance' | 'ledger';
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

interface ScanDiagnostics {
  underlying?: string;
  data_quality?: string;
  reasons?: string[];
  candidates_found?: number;
  error?: string | null;
}

// Shared AudioContext — created once, reused for every chime (no per-alert leak)
let sharedAudioCtx: AudioContext | null = null;
function playAlertChime(isWin = false, isScalp = false) {
  try {
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    if (!sharedAudioCtx || sharedAudioCtx.state === 'closed') {
      sharedAudioCtx = new AC();
    }
    const ctx = sharedAudioCtx;
    if (ctx.state === 'suspended') void ctx.resume();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    if (isScalp) {
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
    osc.onended = () => {
      try {
        osc.disconnect();
        gain.disconnect();
      } catch {}
    };
  } catch {}
}

function upsertSignal(list: SignalDTO[], incoming: SignalDTO): SignalDTO[] {
  if (!incoming?.signal_id) return list;
  const idx = list.findIndex((s) => s.signal_id === incoming.signal_id);
  if (idx >= 0) {
    const next = list.slice();
    next[idx] = { ...next[idx], ...incoming };
    return next;
  }
  return [incoming, ...list].slice(0, 100);
}

export default function SignalsPage() {
  const [active, setActive] = useState<SignalDTO[]>([]);
  const [activeQuality, setActiveQuality] = useState<string>('LIVE');
  const [scannerData, setScannerData] = useState<SignalDTO[]>([]);
  const [scanDiagnostics, setScanDiagnostics] = useState<ScanDiagnostics[]>([]);
  const [scanQuality, setScanQuality] = useState<string>('LIVE');
  const [loading, setLoading] = useState(false);
  const [scannerLoading, setScannerLoading] = useState(false);

  const [filterDesk, setFilterDesk] = useState<FilterDesk>('ALL');
  const [filterInstr, setFilterInstr] = useState<FilterInstrument>('ALL');
  const [filterStrat, setFilterStrat] = useState<FilterStrategy>('ALL');
  const [assetClass, setAssetClass] = useState<FilterAssetClass>('ALL');
  const [oppSource, setOppSource] = useState<OppSource>('live');
  const [trackView, setTrackView] = useState<TrackView>('ledger');
  const [cryptoSignals, setCryptoSignals] = useState<CryptoSignal[]>([]);
  const [cryptoLoading, setCryptoLoading] = useState(false);
  const [cryptoError, setCryptoError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');
  const [soundEnabled, setSoundEnabled] = useState<boolean>(true);

  const [inspectSignalId, setInspectSignalId] = useState<string | null>(null);
  const [perfSummary, setPerfSummary] = useState<any>(null);
  const [activeError, setActiveError] = useState<string | null>(null);
  const [scannerError, setScannerError] = useState<string | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);

  const [auditTrades, setAuditTrades] = useState<AuditTradeRecord[]>([]);
  const [auditSummary, setAuditSummary] = useState<AuditSummary | null>(null);
  const [auditLoading, setAuditLoading] = useState<boolean>(false);

  const knownSignalIds = useRef<Set<string>>(new Set());
  const activeInFlight = useRef(false);
  const auditInFlight = useRef(false);
  const scannerInFlight = useRef(false);
  const cryptoInFlight = useRef(false);
  const sseRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch active signals — single-flight guarded so polls never stack
  const fetchActive = useCallback(
    async (showLoading = true) => {
      if (activeInFlight.current) return;
      activeInFlight.current = true;
      if (showLoading) setLoading(true);
      setActiveError(null);
      try {
        const res: any = await api.getSignalsActive({
          instrument: filterInstr !== 'ALL' ? filterInstr : undefined,
          strategy: filterStrat !== 'ALL' ? filterStrat : undefined,
          desk: filterDesk !== 'ALL' ? filterDesk : undefined,
        });
        const list: SignalDTO[] = res.signals || res.data?.signals || [];
        setActiveQuality(res.data_quality || res.data?.data_quality || 'LIVE');

        if (soundEnabled && knownSignalIds.current.size > 0) {
          const newConfirmed = list.filter(
            (s) => s?.signal_id && !knownSignalIds.current.has(s.signal_id) && (s.fsm_state === 'CONFIRMED' || String(s.fsm_state || '').includes('TARGET'))
          );
          if (newConfirmed.length > 0) {
            const isScalp = newConfirmed.some((s) => s.is_scalp || s.signal_type === 'SCALP');
            playAlertChime(true, isScalp);
          }
        }
        list.forEach((s) => {
          if (s?.signal_id) knownSignalIds.current.add(s.signal_id);
        });
        setActive(list);
      } catch (e: any) {
        setActiveError(e.message || 'Failed to load quantitative signals');
      } finally {
        setLoading(false);
        activeInFlight.current = false;
      }
    },
    [filterInstr, filterStrat, filterDesk, soundEnabled],
  );

  // Run scanner — manual + slow poll; results carry diagnostics explaining emptiness
  const fetchScanner = useCallback(async (showLoading = true) => {
    if (scannerInFlight.current) return;
    scannerInFlight.current = true;
    if (showLoading) setScannerLoading(true);
    setScannerError(null);
    try {
      const res: any = await api.getSignalsScanner();
      const list: SignalDTO[] = res.active_signals || res.new_signals || [];
      setScannerData(list);
      setScanDiagnostics(res.diagnostics || res.scalp_desk?.diagnostics || []);
      setScanQuality(res.data_quality || 'LIVE');
      if (res.errors && Object.keys(res.errors).length > 0) {
        setScannerError(
          Object.entries(res.errors)
            .map(([u, msg]) => `${u}: ${msg}`)
            .join(' • ')
            .slice(0, 300)
        );
      }
    } catch (e: any) {
      setScannerError(e.message || 'Scanner unavailable');
    } finally {
      setScannerLoading(false);
      scannerInFlight.current = false;
    }
  }, []);

  // Fetch crypto quant signals (BTC/ETH) — auto-only, no FSM/paper backend
  const fetchCrypto = useCallback(async (showLoading = true) => {
    if (cryptoInFlight.current) return;
    cryptoInFlight.current = true;
    if (showLoading) setCryptoLoading(true);
    setCryptoError(null);
    try {
      const res: any = await api.getCryptoSignals();
      const list: CryptoSignal[] = res?.data?.signals || res?.signals || [];
      setCryptoSignals(Array.isArray(list) ? list : []);
    } catch (e: any) {
      setCryptoError(e.message || 'Crypto signals unavailable');
    } finally {
      if (showLoading) setCryptoLoading(false);
      cryptoInFlight.current = false;
    }
  }, []);

  // Fetch Signal Audit Ledger without flickering background spinners
  const fetchAudit = useCallback(async (showLoading = false) => {
    if (auditInFlight.current) return;
    auditInFlight.current = true;
    if (showLoading) setAuditLoading(true);
    setAuditError(null);
    try {
      const res: any = await api.getSignalsAudit();
      setAuditTrades(res.trades || []);
      setAuditSummary(res.summary || null);
    } catch (e: any) {
      setAuditError(e.message || 'Audit ledger unavailable');
    } finally {
      if (showLoading) setAuditLoading(false);
      auditInFlight.current = false;
    }
  }, []);

  // SSE-first live updates: patch the active list locally, debounce full refetch
  const scheduleSseRefresh = useCallback(() => {
    if (sseRefreshTimer.current) return;
    sseRefreshTimer.current = setTimeout(() => {
      sseRefreshTimer.current = null;
      if (!document.hidden) {
        void fetchActive(false);
        void fetchAudit(false);
      }
    }, 1500);
  }, [fetchActive, fetchAudit]);

  const handleStreamEvent = useCallback(
    (e: { type: string; payload: unknown }) => {
      const t = e.type;
      const p = e.payload as Record<string, unknown>;
      const signal = (p?.signal || p) as SignalDTO | undefined;
      if (t === 'signal_deleted' && typeof p?.signal_id === 'string') {
        setActive((prev) => prev.filter((s) => s.signal_id !== p.signal_id));
        return;
      }
      if (signal?.signal_id && (t.includes('signal') || t.includes('paper') || t.includes('execution') || t.includes('outcome') || t.includes('staged'))) {
        setActive((prev) => upsertSignal(prev, signal));
        knownSignalIds.current.add(signal.signal_id);
        if (soundEnabled && (signal.fsm_state === 'CONFIRMED' || String(signal.fsm_state || '').includes('TARGET'))) {
          playAlertChime(true, Boolean(signal.is_scalp));
        }
        return;
      }
      if (t === 'scanner_update') {
        scheduleSseRefresh();
      }
    },
    [scheduleSseRefresh, soundEnabled]
  );

  const { streamState } = useSignalStream(true, handleStreamEvent);

  // Quick stats
  useEffect(() => {
    api
      .getSignalsPerformance()
      .then((r) => setPerfSummary(r))
      .catch(() => {});
  }, []);

  // Polling fallback with jitter + hidden-tab pause (SSE owns realtime; poll is safety net)
  useEffect(() => {
    void fetchActive(true);
    void fetchScanner(true);
    void fetchAudit(true);
    void fetchCrypto(true);

    let timeout: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;
    const loop = () => {
      if (stopped) return;
      timeout = setTimeout(() => {
        if (!document.hidden) {
          void fetchActive(false);
          void fetchAudit(false);
          void fetchCrypto(false);
        }
        loop();
      }, withJitter(8000));
    };
    // Scanner is expensive (full universe TA) — poll it 4x slower than active list
    let scanTimeout: ReturnType<typeof setTimeout> | null = null;
    const scanLoop = () => {
      if (stopped) return;
      scanTimeout = setTimeout(() => {
        if (!document.hidden) void fetchScanner(false);
        scanLoop();
      }, withJitter(32000));
    };
    loop();
    scanLoop();

    return () => {
      stopped = true;
      if (timeout) clearTimeout(timeout);
      if (scanTimeout) clearTimeout(scanTimeout);
      if (sseRefreshTimer.current) clearTimeout(sseRefreshTimer.current);
    };
  }, [fetchActive, fetchScanner, fetchAudit, fetchCrypto]);

  const degraded = activeQuality !== 'LIVE' || scanQuality !== 'LIVE';
  const emptyReasons = scanDiagnostics
    .filter((d) => d?.reasons?.length)
    .slice(0, 3)
    .flatMap((d) => (d.reasons || []).slice(0, 1).map((r) => `${d.underlying || '?'}: ${r}`));

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto pb-12">
      {/* ── HEADER & LIVE COCKPIT STATUS ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <Radio className="w-5 h-5 text-primary" /> Signal Centre
            <Badge className="bg-primary text-primary-foreground font-mono text-[10px]">QUANT RADAR</Badge>
            <span className="text-xs font-normal text-muted-foreground ml-2 hidden md:inline">
              Unified Index + Crypto Intelligence (NIFTY • BANKNIFTY • SENSEX • BTC • ETH)
            </span>
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2 flex-wrap">
            Real-time multi-strategy scanner with FSM lifecycle (index) + order-book signals (crypto).
            <span
              className={`inline-flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 rounded border ${
                streamState === 'CONNECTED'
                  ? 'text-emerald-600 border-emerald-500/30 bg-emerald-500/10'
                  : 'text-amber-600 border-amber-500/30 bg-amber-500/10'
              }`}
              title="SSE live stream state — polling continues as fallback"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${streamState === 'CONNECTED' ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
              {streamState === 'CONNECTED' ? 'LIVE STREAM' : `STREAM ${streamState} • POLL FALLBACK`}
            </span>
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

          <Button variant="outline" size="sm" onClick={() => { void fetchActive(true); void fetchScanner(true); void fetchCrypto(true); }} disabled={loading} className="h-8 text-xs gap-1">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>

          <Link href="/settings">
            <Button variant="ghost" size="sm" className="h-8 text-xs gap-1">
              <SettingsIcon className="w-3.5 h-3.5" /> Settings
            </Button>
          </Link>
        </div>
      </div>

      {degraded && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5" />
          <div>
            <p className="font-semibold text-amber-700 dark:text-amber-400">
              Market data degraded (signals {activeQuality} / scanner {scanQuality}) — prices and distances may be stale. No signals are fabricated; empty means no confirmed setup.
            </p>
            {emptyReasons.length > 0 && (
              <ul className="text-muted-foreground mt-1 space-y-0.5">
                {emptyReasons.map((r, i) => (
                  <li key={i} className="font-mono text-[11px]">• {r}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* ── TOP KPI SUMMARY STRIP (UNIFIED INDEX + CRYPTO) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="bg-secondary/20">
          <CardContent className="p-3 flex items-center justify-between">
            <div>
              <span className="text-[11px] text-muted-foreground font-medium">Opportunities ({assetClass === 'ALL' ? 'Index + Crypto' : assetClass})</span>
              <div className="text-lg font-bold font-mono text-primary">{active.length + cryptoSignals.length} Signals</div>
              <div className="text-[10px] font-mono text-muted-foreground">{active.length} index • {cryptoSignals.length} crypto</div>
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

      {/* ── 3 UNIFIED TABS: Opportunities / Create / Track ── */}
      <Tabs defaultValue="opportunities" className="w-full">
        <TabsList className="w-full justify-start flex-wrap h-auto bg-muted/60 p-1 rounded-xl">
          <TabsTrigger value="opportunities" className="gap-1.5 text-xs font-semibold py-1.5 px-3">
            <Radio className="w-3.5 h-3.5" /> Opportunities ({active.length + cryptoSignals.length})
          </TabsTrigger>
          <TabsTrigger value="create" className="gap-1.5 text-xs font-semibold py-1.5 px-3">
            <Sparkles className="w-3.5 h-3.5" /> Create
          </TabsTrigger>
          <TabsTrigger value="track" className="gap-1.5 text-xs font-semibold py-1.5 px-3">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Track Record
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

        {/* ── TAB 1: OPPORTUNITIES (Index Live+Scanner + Crypto merged) ── */}
        <TabsContent value="opportunities" className="space-y-4 pt-2">
          {/* Filters & View Toggle Bar */}
          <Card className="p-3 space-y-2.5">
            {/* Row 0: Asset class + Source (3-tab merge) */}
            <div className="flex items-center justify-between gap-2 pb-2 border-b flex-wrap">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-xs font-semibold text-muted-foreground mr-1">Market:</span>
                {(['ALL', 'INDEX', 'CRYPTO'] as const).map((a) => (
                  <button
                    key={a}
                    onClick={() => setAssetClass(a)}
                    className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all flex items-center gap-1 ${
                      assetClass === a
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-secondary/60 hover:bg-secondary border-transparent'
                    }`}
                  >
                    {a === 'CRYPTO' && <Coins className="w-3.5 h-3.5" />}
                    {a === 'ALL' ? '🌐 All Markets' : a === 'INDEX' ? 'NIFTY • BANK • SENSEX' : 'BTC • ETH'}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-xs font-semibold text-muted-foreground mr-1">Source:</span>
                <button
                  onClick={() => setOppSource('live')}
                  className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all ${
                    oppSource === 'live'
                      ? 'bg-emerald-600 text-white border-emerald-700'
                      : 'bg-secondary/60 hover:bg-secondary border-transparent'
                  }`}
                >
                  Live Setups
                </button>
                <button
                  onClick={() => setOppSource('scanner')}
                  disabled={assetClass === 'CRYPTO'}
                  className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all ${
                    oppSource === 'scanner'
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-secondary/60 hover:bg-secondary border-transparent disabled:opacity-40'
                  }`}
                  title={assetClass === 'CRYPTO' ? 'Scanner is index-only; crypto is auto-streamed' : 'Full-universe scan'}
                >
                  Scanner Feed
                </button>
              </div>
            </div>
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
                  <Clock className="w-3 h-3" /> {streamState === 'CONNECTED' ? 'SSE live + 8s safety poll' : '8s poll (SSE reconnecting)'}
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

          {assetClass !== 'CRYPTO' && activeError && oppSource === 'live' && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive flex items-center gap-2 flex-wrap">
              <AlertTriangle className="w-4 h-4" /> {activeError}
              <Button size="sm" variant="outline" className="h-7 text-[11px] ml-auto" onClick={() => void fetchActive(true)}>
                Retry
              </Button>
            </div>
          )}

          {(loading || scannerLoading) && active.length === 0 && scannerData.length === 0 && assetClass !== 'CRYPTO' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <Card key={i} className="p-4 space-y-3 animate-pulse">
                  <div className="h-4 bg-muted rounded w-32" />
                  <div className="h-16 bg-muted rounded" />
                </Card>
              ))}
            </div>
          )}

          {assetClass !== 'CRYPTO' && (
            <>
              {(() => {
                const oppSignals = oppSource === 'live' ? active : scannerData.length > 0 ? scannerData : active;
                const isScannerMode = oppSource === 'scanner';
                return (
                  <>
                    {isScannerMode && (
                      <Card className="p-3">
                        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
                          <div className="text-xs font-semibold flex items-center gap-2">
                            <Layers className="w-3.5 h-3.5 text-primary" /> Scanner Feed
                            <Badge variant="outline" className={`text-[10px] font-mono ${scanQuality === 'LIVE' ? 'text-emerald-600 border-emerald-500/30' : 'text-amber-600 border-amber-500/30'}`}>
                              {scanQuality}
                            </Badge>
                          </div>
                          <Button size="sm" onClick={() => void fetchScanner(true)} disabled={scannerLoading} className="h-7 text-xs gap-1">
                            <RefreshCw className={`w-3 h-3 ${scannerLoading ? 'animate-spin' : ''}`} />
                            {scannerLoading ? 'Scanning…' : 'Run Full Scan'}
                          </Button>
                        </div>
                        {scannerError && (
                          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-2 text-[11px] text-amber-700 flex items-center gap-2 mb-2">
                            <AlertTriangle className="w-3.5 h-3.5" /> {scannerError}
                          </div>
                        )}
                        {scanDiagnostics.length > 0 && (
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                            {scanDiagnostics.slice(0, 3).map((d, i) => (
                              <div key={i} className="text-[11px] font-mono border rounded-lg p-2 bg-secondary/30">
                                <span className="font-bold">{d.underlying || '?'}</span>
                                <span className={`ml-1.5 ${d.data_quality === 'LIVE' ? 'text-emerald-600' : 'text-amber-600'}`}>{d.data_quality || '?'}</span>
                                <span className="text-muted-foreground ml-1.5">{d.candidates_found ?? 0} candidates</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </Card>
                    )}
                    {oppSignals.length > 0 ? (
                      <>
                        {viewMode === 'grid' ? (
                          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {oppSignals.map((sig) => (
                              <SignalErrorBoundary key={sig.signal_id} label={sig.underlying || 'Signal'}>
                                <SignalCard
                                  signal={sig}
                                  onInspect={(id) => setInspectSignalId(id)}
                                  onPaperExecuted={() => {
                                    void fetchActive(false);
                                    void fetchAudit(false);
                                  }}
                                />
                              </SignalErrorBoundary>
                            ))}
                          </div>
                        ) : (
                          <SignalErrorBoundary label="Scanner table">
                            <SignalScannerTable
                              signals={oppSignals}
                              onInspect={(id) => setInspectSignalId(id)}
                              onRefresh={() => (isScannerMode ? void fetchScanner(false) : void fetchActive(false))}
                              loading={isScannerMode ? scannerLoading : loading}
                            />
                          </SignalErrorBoundary>
                        )}
                      </>
                    ) : (
                      !loading && !scannerLoading && (
                        <Card className="p-8 text-center space-y-2">
                          <div className="text-sm font-semibold">No {isScannerMode ? 'scanner' : 'active'} index setups match criteria</div>
                          <p className="text-xs text-muted-foreground max-w-md mx-auto">
                            No strategy conditions on {filterInstr} with {filterStrat}. Empty is honest — only validated breakouts register.
                          </p>
                        </Card>
                      )
                    )}
                  </>
                );
              })()}
            </>
          )}

          {assetClass !== 'INDEX' && (
            <div className="space-y-2">
              {cryptoError && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-2.5 text-[11px] text-amber-700 flex items-center gap-2">
                  <AlertTriangle className="w-3.5 h-3.5" /> Crypto feed degraded: {cryptoError}
                  <Button size="sm" variant="outline" className="h-6 text-[10px] ml-auto" onClick={() => void fetchCrypto(true)}>
                    Retry
                  </Button>
                </div>
              )}
              <SignalErrorBoundary label="Crypto signals">
                <CryptoSignalsCard signals={cryptoSignals} loading={cryptoLoading} selectedAsset="BTC" onSelectAsset={() => {}} />
              </SignalErrorBoundary>
              <p className="text-[11px] text-muted-foreground font-mono px-1">
                Crypto signals are auto-derived from Binance order-book + funding (read-only, copy-plan). Paper execution + audit ledger remain index-only.
              </p>
            </div>
          )}
        </TabsContent>

        {/* ── TAB 2: CREATE ── */}
        <TabsContent value="create" className="pt-2 space-y-3">
          <GenerateSignalForm
            onGenerated={() => {
              void fetchActive(false);
              void fetchScanner(true);
            }}
          />
          <p className="text-[11px] text-muted-foreground font-mono px-1">
            Manual creation is index-only (NIFTY/BANKNIFTY/SENSEX). Crypto setups are fully automated — see Opportunities → Crypto.
          </p>
        </TabsContent>

        {/* ── TAB 3: TRACK RECORD (Performance + Ledger) ── */}
        <TabsContent value="track" className="pt-2 space-y-4">
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setTrackView('ledger')}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg border transition-all flex items-center gap-1.5 ${
                trackView === 'ledger' ? 'bg-primary text-primary-foreground border-primary' : 'bg-secondary/60 hover:bg-secondary border-transparent'
              }`}
            >
              <CheckCircle2 className="w-3.5 h-3.5" /> Ledger & P&L
            </button>
            <button
              onClick={() => setTrackView('performance')}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg border transition-all flex items-center gap-1.5 ${
                trackView === 'performance' ? 'bg-primary text-primary-foreground border-primary' : 'bg-secondary/60 hover:bg-secondary border-transparent'
              }`}
            >
              <Award className="w-3.5 h-3.5" /> Performance
            </button>
            <span className="text-[11px] text-muted-foreground font-mono ml-2 hidden sm:inline">Index paper trades only • crypto is read-only</span>
          </div>

          {trackView === 'performance' ? (
            <SignalPerformanceView />
          ) : (
            <>
              {auditError && (
                <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive flex items-center gap-2 flex-wrap">
                  <AlertTriangle className="w-4 h-4" /> {auditError}
                  <Button size="sm" variant="outline" className="h-7 text-[11px] ml-auto" onClick={() => void fetchAudit(true)}>
                    Retry
                  </Button>
                </div>
              )}
              <SignalAuditTable
                trades={auditTrades}
                summary={auditSummary}
                loading={auditLoading}
                onRefresh={() => void fetchAudit(true)}
                onSelectSignal={(sigId) => setInspectSignalId(sigId)}
              />
            </>
          )}
        </TabsContent>
      </Tabs>

      {/* ── SIGNAL DEEP DIVE MODAL / DRAWER ── */}
      {inspectSignalId && (
        <SignalDeepDiveModal
          signalId={inspectSignalId}
          onClose={() => setInspectSignalId(null)}
          onPaperExecuted={() => {
            void fetchActive(false);
            void fetchAudit(false);
          }}
        />
      )}
    </div>
  );
}
