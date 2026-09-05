'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { PageTabs } from '@/components/ui/PageTabs';
import { useSignalEngine } from '@/components/signals/useSignalEngine';
import { SignalOpportunitiesTab } from '@/components/signals/SignalOpportunitiesTab';
import { SignalTrackRecordTab } from '@/components/signals/SignalTrackRecordTab';
import {
  AlertTriangle,
  CheckCircle2,
  Radio,
  RefreshCw,
  Settings as SettingsIcon,
  Sparkles,
  Volume2,
  VolumeX,
} from 'lucide-react';

const GenerateSignalForm = dynamic(
  () => import('@/components/signals/GenerateSignalForm').then((m) => m.GenerateSignalForm),
  { ssr: false, loading: () => <div className="bg-card border border-border rounded-xl p-5 h-48 animate-pulse" /> },
);

const SignalDeepDiveModal = dynamic(
  () => import('@/components/signals/SignalDeepDiveModal').then((m) => m.SignalDeepDiveModal),
  { ssr: false },
);

export default function SignalsPage() {
  const engine = useSignalEngine();

  const degraded = engine.activeQuality !== 'LIVE' || engine.scanQuality !== 'LIVE';
  const emptyReasons = engine.scanDiagnostics
    .filter((d) => d?.reasons?.length)
    .slice(0, 3)
    .flatMap((d) => (d.reasons || []).slice(0, 1).map((r) => `${d.underlying || '?'}: ${r}`));

  const totalSetups = engine.active.length + engine.cryptoSignals.length;

  const tabs = [
    {
      id: 'opportunities',
      label: 'Opportunities',
      icon: Radio,
      badge: totalSetups,
      content: (
        <SignalOpportunitiesTab
          active={engine.active}
          setActive={engine.setActive}
          scannerData={engine.scannerData}
          scanDiagnostics={engine.scanDiagnostics}
          scanQuality={engine.scanQuality}
          loading={engine.loading}
          scannerLoading={engine.scannerLoading}
          filterDesk={engine.filterDesk}
          setFilterDesk={engine.setFilterDesk}
          filterInstr={engine.filterInstr}
          setFilterInstr={engine.setFilterInstr}
          filterStrat={engine.filterStrat}
          setFilterStrat={engine.setFilterStrat}
          assetClass={engine.assetClass}
          setAssetClass={engine.setAssetClass}
          oppSource={engine.oppSource}
          setOppSource={engine.setOppSource}
          viewMode={engine.viewMode}
          setViewMode={engine.setViewMode}
          cryptoSignals={engine.cryptoSignals}
          cryptoLoading={engine.cryptoLoading}
          cryptoError={engine.cryptoError}
          selectMode={engine.selectMode}
          setSelectMode={engine.setSelectMode}
          selectedOppIds={engine.selectedOppIds}
          setSelectedOppIds={engine.setSelectedOppIds}
          bulkDeletingOpp={engine.bulkDeletingOpp}
          setBulkDeletingOpp={engine.setBulkDeletingOpp}
          cardsNowMs={engine.cardsNowMs}
          activeError={engine.activeError}
          scannerError={engine.scannerError}
          onInspectSignal={(id) => engine.setInspectSignalId(id)}
          onRefreshActive={() => void engine.fetchActive(true)}
          onRefreshScanner={() => void engine.fetchScanner(true)}
          onRefreshCrypto={() => void engine.fetchCrypto(true)}
        />
      ),
    },
    {
      id: 'create',
      label: 'Create',
      icon: Sparkles,
      content: (
        <div className="space-y-3">
          <GenerateSignalForm
            onGenerated={() => {
              void engine.fetchActive(false);
              void engine.fetchScanner(true);
            }}
          />
          <p className="text-[11px] text-muted-foreground font-mono px-1">
            Manual creation is index-only (NIFTY/BANKNIFTY/SENSEX). Crypto setups are fully automated — see Opportunities → Crypto.
          </p>
        </div>
      ),
    },
    {
      id: 'track',
      label: 'Track Record',
      icon: CheckCircle2,
      content: (
        <SignalTrackRecordTab
          trackView={engine.trackView}
          setTrackView={engine.setTrackView}
          auditTrades={engine.auditTrades}
          auditSummary={engine.auditSummary}
          auditLoading={engine.auditLoading}
          auditError={engine.auditError}
          onRefreshAudit={() => void engine.fetchAudit(true)}
          onSelectSignal={(sigId) => engine.setInspectSignalId(sigId)}
        />
      ),
    },
  ];

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
                engine.streamState === 'CONNECTED'
                  ? 'text-emerald-600 dark:text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
                  : 'text-amber-600 dark:text-amber-400 border-amber-500/30 bg-amber-500/10'
              }`}
              title="SSE live stream state — polling continues as fallback"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${engine.streamState === 'CONNECTED' ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
              {engine.streamState === 'CONNECTED' ? 'LIVE STREAM' : `STREAM ${engine.streamState} • POLL FALLBACK`}
            </span>
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={() => engine.setSoundEnabled(!engine.soundEnabled)}
            className={`h-8 text-xs gap-1 cursor-pointer ${engine.soundEnabled ? 'text-primary' : 'text-muted-foreground'}`}
            title={engine.soundEnabled ? 'Audio Chime Alerts Enabled' : 'Audio Muted'}
          >
            {engine.soundEnabled ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">{engine.soundEnabled ? 'Audio Alerts' : 'Muted'}</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void engine.fetchActive(true);
              void engine.fetchScanner(true);
              void engine.fetchCrypto(true);
            }}
            disabled={engine.loading}
            className="h-8 text-xs gap-1 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${engine.loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>

          <Link href="/settings">
            <Button variant="ghost" size="sm" className="h-8 text-xs gap-1 cursor-pointer">
              <SettingsIcon className="w-3.5 h-3.5" /> Settings
            </Button>
          </Link>
        </div>
      </div>

      {degraded && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold text-amber-700 dark:text-amber-400">
              Market data degraded (signals {engine.activeQuality} / scanner {engine.scanQuality}) — prices and distances may be stale. No signals are fabricated; empty means no confirmed setup.
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

      {/* ── SOBER TOP QUANT TICKER RIBBON ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-2.5 rounded-xl bg-secondary/50 border border-border text-xs font-mono">
        <div className="flex items-center gap-4 sm:gap-6 flex-wrap">
          <div>
            <span className="text-muted-foreground">Opportunities:</span>
            <span className="ml-1 font-bold text-foreground">{totalSetups} Setups</span>
            <span className="text-[10px] text-muted-foreground ml-1">({engine.active.length} index • {engine.cryptoSignals.length} crypto)</span>
          </div>
          <div>
            <span className="text-muted-foreground">⚡ Scalp Win (1M):</span>
            <span className="ml-1 font-bold text-amber-600 dark:text-amber-400">
              {engine.perfSummary?.scalp_summary?.win_rate_pct !== undefined ? `${engine.perfSummary.scalp_summary.win_rate_pct}%` : '—'}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">📊 Core Win (5M):</span>
            <span className="ml-1 font-bold text-primary">
              {engine.perfSummary?.intraday_summary?.win_rate_pct !== undefined ? `${engine.perfSummary.intraday_summary.win_rate_pct}%` : '—'}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">Profit Factor:</span>
            <span className="ml-1 font-bold text-foreground">
              {engine.perfSummary?.profit_factor !== undefined ? `${engine.perfSummary.profit_factor}x` : '—'}
            </span>
          </div>
          {engine.auditSummary?.total_pnl_inr !== undefined && (
            <div>
              <span className="text-muted-foreground">Live MTM:</span>
              <span className={`ml-1 font-bold ${engine.auditSummary.total_pnl_inr >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}`}>
                {engine.auditSummary.total_pnl_inr >= 0
                  ? `+₹${Math.round(engine.auditSummary.total_pnl_inr).toLocaleString('en-IN')}`
                  : `-₹${Math.round(Math.abs(engine.auditSummary.total_pnl_inr)).toLocaleString('en-IN')}`}
              </span>
            </div>
          )}
        </div>
        <div className="text-[11px] text-muted-foreground hidden lg:block">
          Feed: <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{engine.activeQuality === 'LIVE' ? 'NSE Live (FYERS)' : 'Degraded'}</span>
        </div>
      </div>

      {/* ── 3 UNIFIED TABS VIA PAGETABS (Opportunities / Create / Track) ── */}
      <PageTabs
        tabs={tabs}
        defaultTab="opportunities"
        syncWithUrl
      />

      {/* ── SIGNAL DEEP DIVE MODAL / DRAWER ── */}
      {engine.inspectSignalId && (
        <SignalDeepDiveModal
          signalId={engine.inspectSignalId}
          onClose={() => engine.setInspectSignalId(null)}
          onPaperExecuted={() => {
            void engine.fetchActive(false);
            void engine.fetchAudit(false);
          }}
        />
      )}
    </div>
  );
}
