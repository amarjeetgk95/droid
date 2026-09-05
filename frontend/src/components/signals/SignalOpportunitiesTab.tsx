'use client';

import React from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { SignalCard, type SignalDTO } from './SignalCard';
import { SignalScannerTable } from './SignalScannerTable';
import { SignalErrorBoundary } from './SignalErrorBoundary';
import { CryptoSignalsCard } from '@/components/crypto/CryptoSignalsCard';
import type { CryptoSignal } from '@/lib/types';
import type { FilterInstrument, FilterDesk, FilterAssetClass, OppSource, FilterStrategy, ScanDiagnostics } from './useSignalEngine';
import {
  AlertTriangle,
  Coins,
  Grid,
  Layers,
  List,
  RefreshCw,
  Zap,
} from 'lucide-react';

export interface SignalOpportunitiesTabProps {
  active: SignalDTO[];
  setActive: React.Dispatch<React.SetStateAction<SignalDTO[]>>;
  scannerData: SignalDTO[];
  scanDiagnostics: ScanDiagnostics[];
  scanQuality: string;
  loading: boolean;
  scannerLoading: boolean;
  filterDesk: FilterDesk;
  setFilterDesk: (v: FilterDesk) => void;
  filterInstr: FilterInstrument;
  setFilterInstr: (v: FilterInstrument) => void;
  filterStrat: FilterStrategy;
  setFilterStrat: (v: FilterStrategy) => void;
  assetClass: FilterAssetClass;
  setAssetClass: (v: FilterAssetClass) => void;
  oppSource: OppSource;
  setOppSource: (v: OppSource) => void;
  viewMode: 'grid' | 'table';
  setViewMode: (v: 'grid' | 'table') => void;
  cryptoSignals: CryptoSignal[];
  cryptoLoading: boolean;
  cryptoError: string | null;
  selectMode: boolean;
  setSelectMode: React.Dispatch<React.SetStateAction<boolean>>;
  selectedOppIds: Set<string>;
  setSelectedOppIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  bulkDeletingOpp: boolean;
  setBulkDeletingOpp: (v: boolean) => void;
  cardsNowMs: number;
  activeError: string | null;
  scannerError: string | null;
  onInspectSignal: (id: string) => void;
  onRefreshActive: () => void;
  onRefreshScanner: () => void;
  onRefreshCrypto: () => void;
}

export function SignalOpportunitiesTab({
  active,
  setActive,
  scannerData,
  scanDiagnostics,
  scanQuality,
  loading,
  scannerLoading,
  filterDesk,
  setFilterDesk,
  filterInstr,
  setFilterInstr,
  filterStrat,
  setFilterStrat,
  assetClass,
  setAssetClass,
  oppSource,
  setOppSource,
  viewMode,
  setViewMode,
  cryptoSignals,
  cryptoLoading,
  cryptoError,
  selectMode,
  setSelectMode,
  selectedOppIds,
  setSelectedOppIds,
  bulkDeletingOpp,
  setBulkDeletingOpp,
  cardsNowMs,
  activeError,
  scannerError,
  onInspectSignal,
  onRefreshActive,
  onRefreshScanner,
  onRefreshCrypto,
}: SignalOpportunitiesTabProps) {
  const oppSignals = oppSource === 'live' ? active : scannerData.length > 0 ? scannerData : active;
  const isScannerMode = oppSource === 'scanner';

  return (
    <div className="space-y-4">
      {/* Filter & Command Controls */}
      <Card className="p-3 space-y-2.5">
        {/* Top Row: Desk & Market Selector + Sources & View Switcher */}
        <div className="flex items-center justify-between gap-3 pb-2 border-b flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold text-muted-foreground mr-1">Desk:</span>
            <button
              onClick={() => {
                setFilterDesk('ALL');
                setAssetClass('ALL');
                setFilterStrat('ALL');
              }}
              className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all cursor-pointer ${
                filterDesk === 'ALL' && assetClass === 'ALL'
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-secondary/60 hover:bg-secondary border-transparent'
              }`}
            >
              🌐 All Signals
            </button>
            <button
              onClick={() => {
                setFilterDesk('SCALP');
                setAssetClass('INDEX');
                setFilterStrat('ALL');
              }}
              className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all flex items-center gap-1 cursor-pointer ${
                filterDesk === 'SCALP'
                  ? 'bg-amber-500 text-black border-amber-600 shadow-xs'
                  : 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-600 border-amber-500/30'
              }`}
            >
              <Zap className="w-3.5 h-3.5" /> ⚡ Scalp Desk (1M/3M)
            </button>
            <button
              onClick={() => {
                setFilterDesk('INTRADAY');
                setAssetClass('INDEX');
                setFilterStrat('ALL');
              }}
              className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all flex items-center gap-1 cursor-pointer ${
                filterDesk === 'INTRADAY'
                  ? 'bg-primary text-primary-foreground border-primary shadow-xs'
                  : 'bg-primary/10 hover:bg-primary/20 text-primary border-primary/30'
              }`}
            >
              <Layers className="w-3.5 h-3.5" /> 📊 Core Intraday (5M/15M)
            </button>
            <button
              onClick={() => {
                setAssetClass('CRYPTO');
              }}
              className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all flex items-center gap-1 cursor-pointer ${
                assetClass === 'CRYPTO'
                  ? 'bg-cyan-600 text-white border-cyan-700'
                  : 'bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-600 border-cyan-500/30'
              }`}
            >
              <Coins className="w-3.5 h-3.5" /> 🪙 Binance Crypto
            </button>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Source Pill */}
            <div className="inline-flex bg-muted/50 p-0.5 rounded-lg border text-xs">
              <button
                onClick={() => setOppSource('live')}
                className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                  oppSource === 'live'
                    ? 'bg-background text-foreground shadow-xs font-bold'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Live Setups
              </button>
              <button
                onClick={() => setOppSource('scanner')}
                disabled={assetClass === 'CRYPTO'}
                className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                  oppSource === 'scanner'
                    ? 'bg-background text-foreground shadow-xs font-bold'
                    : 'text-muted-foreground hover:text-foreground disabled:opacity-40'
                }`}
                title={assetClass === 'CRYPTO' ? 'Scanner is index-only' : 'Full universe scanner'}
              >
                Scanner Feed
              </button>
            </div>

            {/* View Mode */}
            <div className="flex items-center border rounded-lg overflow-hidden bg-background">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-1.5 cursor-pointer ${viewMode === 'grid' ? 'bg-secondary text-primary' : 'text-muted-foreground'}`}
                title="Grid Card View"
              >
                <Grid className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setViewMode('table')}
                className={`p-1.5 cursor-pointer ${viewMode === 'table' ? 'bg-secondary text-primary' : 'text-muted-foreground'}`}
                title="Pro Table View"
              >
                <List className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Bottom Row: Instrument Chips & Strategy Pills */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-muted-foreground">Index:</span>
              {(['ALL', 'NIFTY', 'BANKNIFTY', 'SENSEX'] as const).map((instr) => (
                <button
                  key={instr}
                  onClick={() => setFilterInstr(instr)}
                  className={`px-2.5 py-1 text-xs font-bold rounded-lg border transition-all cursor-pointer ${
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
                    className={`px-2 py-0.5 text-[11px] font-mono rounded-md border transition-all cursor-pointer ${
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
          <AlertTriangle className="w-4 h-4 shrink-0" /> {activeError}
          <Button size="sm" variant="outline" className="h-7 text-[11px] ml-auto cursor-pointer" onClick={onRefreshActive}>
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
          {isScannerMode && (
            <Card className="p-3">
              <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
                <div className="text-xs font-semibold flex items-center gap-2">
                  <Layers className="w-3.5 h-3.5 text-primary" /> Scanner Feed
                  <Badge variant="outline" className={`text-[10px] font-mono ${scanQuality === 'LIVE' ? 'text-emerald-600 border-emerald-500/30' : 'text-amber-600 border-amber-500/30'}`}>
                    {scanQuality}
                  </Badge>
                </div>
                <Button size="sm" onClick={onRefreshScanner} disabled={scannerLoading} className="h-7 text-xs gap-1 cursor-pointer">
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
              <div className="flex items-center gap-2 flex-wrap">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-[11px] cursor-pointer"
                  onClick={() => {
                    setSelectMode(!selectMode);
                    setSelectedOppIds(new Set());
                  }}
                >
                  {selectMode ? 'Cancel select' : 'Select multiple'}
                </Button>
                {selectMode && viewMode === 'grid' && (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-[11px] cursor-pointer"
                      onClick={() => setSelectedOppIds(new Set(oppSignals.map((s) => s.signal_id)))}
                    >
                      Select all ({oppSignals.length})
                    </Button>
                    {selectedOppIds.size > 0 && (
                      <Button
                        variant="destructive"
                        size="sm"
                        className="h-7 text-[11px] cursor-pointer"
                        disabled={bulkDeletingOpp}
                        onClick={async () => {
                          setBulkDeletingOpp(true);
                          try {
                            await api.bulkDeleteSignals({ signal_ids: Array.from(selectedOppIds) });
                            setSelectedOppIds(new Set());
                            setSelectMode(false);
                            onRefreshActive();
                          } catch (e: any) {
                            alert(`Bulk delete failed: ${e?.message || 'Unknown error'}`);
                          } finally {
                            setBulkDeletingOpp(false);
                          }
                        }}
                      >
                        {bulkDeletingOpp ? 'Deleting…' : `Delete ${selectedOppIds.size} selected`}
                      </Button>
                    )}
                  </>
                )}
              </div>
              {viewMode === 'grid' ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {oppSignals.map((sig) => (
                    <SignalErrorBoundary key={sig.signal_id} label={sig.underlying || 'Signal'}>
                      <div className="relative">
                        {selectMode && (
                          <input
                            type="checkbox"
                            checked={selectedOppIds.has(sig.signal_id)}
                            onChange={() =>
                              setSelectedOppIds((prev) => {
                                const next = new Set(prev);
                                if (next.has(sig.signal_id)) next.delete(sig.signal_id);
                                else next.add(sig.signal_id);
                                return next;
                              })
                            }
                            onClick={(e) => e.stopPropagation()}
                            className="absolute top-2 right-2 z-10 h-4 w-4 accent-destructive cursor-pointer"
                            title="Select for bulk delete"
                          />
                        )}
                        <SignalCard
                          signal={sig}
                          nowMs={cardsNowMs}
                          onInspect={(id) => {
                            if (!selectMode) onInspectSignal(id);
                          }}
                          onPaperExecuted={() => {
                            onRefreshActive();
                          }}
                          onDeleted={(id) => {
                            setActive((prev) => prev.filter((s) => s.signal_id !== id));
                          }}
                        />
                      </div>
                    </SignalErrorBoundary>
                  ))}
                </div>
              ) : (
                <SignalErrorBoundary label="Scanner table">
                  <SignalScannerTable
                    signals={oppSignals}
                    onInspect={(id) => onInspectSignal(id)}
                    onRefresh={() => (isScannerMode ? onRefreshScanner() : onRefreshActive())}
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
      )}

      {assetClass !== 'INDEX' && (
        <div className="space-y-2">
          {cryptoError && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-2.5 text-[11px] text-amber-700 flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5" /> Crypto feed degraded: {cryptoError}
              <Button size="sm" variant="outline" className="h-6 text-[10px] ml-auto cursor-pointer" onClick={onRefreshCrypto}>
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
    </div>
  );
}
