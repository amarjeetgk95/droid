'use client';

import React from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { SignalCard, type SignalDTO } from './SignalCard';
import { SignalScannerTable } from './SignalScannerTable';
import type { FilterInstrument, FilterDesk, OppSource, FilterStrategy, ScanDiagnostics } from './useSignalEngine';
import {
  AlertTriangle,
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
  oppSource: OppSource;
  setOppSource: (v: OppSource) => void;
  viewMode: 'grid' | 'table';
  setViewMode: (v: 'grid' | 'table') => void;
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
  oppSource,
  setOppSource,
  viewMode,
  setViewMode,
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
                setFilterStrat('ALL');
              }}
              className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all cursor-pointer ${
                filterDesk === 'ALL'
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-secondary/60 hover:bg-secondary border-transparent'
              }`}
            >
              🌐 All Desks
            </button>
            <button
              onClick={() => {
                setFilterDesk('SCALP');
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
                className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                  oppSource === 'scanner'
                    ? 'bg-background text-foreground shadow-xs font-bold'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
                title="Full Indian indices universe scanner"
              >
                Scanner Feed
              </button>
            </div>

            {/* View Mode */}
            <div className="inline-flex bg-muted/50 p-0.5 rounded-lg border">
              <Button
                variant={viewMode === 'grid' ? 'default' : 'ghost'}
                size="sm"
                className="h-7 px-2 text-xs cursor-pointer"
                onClick={() => setViewMode('grid')}
              >
                <Grid className="w-3.5 h-3.5" />
              </Button>
              <Button
                variant={viewMode === 'table' ? 'default' : 'ghost'}
                size="sm"
                className="h-7 px-2 text-xs cursor-pointer"
                onClick={() => setViewMode('table')}
              >
                <List className="w-3.5 h-3.5" />
              </Button>
            </div>

            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs cursor-pointer"
              onClick={() => {
                if (oppSource === 'live') onRefreshActive();
                else onRefreshScanner();
              }}
              disabled={loading || scannerLoading}
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading || scannerLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </div>

        {/* Second Row: Instrument + Strategy Filters */}
        <div className="flex items-center justify-between gap-3 flex-wrap text-xs">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-muted-foreground">Instrument:</span>
            {(['ALL', 'NIFTY', 'BANKNIFTY', 'SENSEX', 'FINNIFTY', 'MIDCPNIFTY'] as FilterInstrument[]).map((inst) => (
              <button
                key={inst}
                onClick={() => setFilterInstr(inst)}
                className={`px-2 py-0.5 rounded text-xs transition-all cursor-pointer ${
                  filterInstr === inst
                    ? 'bg-primary text-primary-foreground font-bold shadow-xs'
                    : 'bg-muted/70 hover:bg-muted text-muted-foreground'
                }`}
              >
                {inst}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-muted-foreground">Strategy:</span>
            <select
              value={filterStrat}
              onChange={(e) => setFilterStrat(e.target.value as FilterStrategy)}
              className="bg-background border rounded px-2 py-1 text-xs text-foreground cursor-pointer focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="ALL">All Strategies</option>
              <option value="ORB_5M">ORB (5M)</option>
              <option value="VWAP_PULLBACK">VWAP Pullback</option>
              <option value="EXPIRY_HERO_ZERO">Hero-Zero</option>
              <option value="MOMENTUM_SPIKE">Momentum Spike</option>
              <option value="MULTI_STRIKE_BREAKOUT">Multi-Strike Breakout</option>
              <option value="SQUEEZE_RELEASE">Squeeze Release</option>
              <option value="REVERSAL_EXHAUSTION">Reversal Exhaustion</option>
            </select>

            {oppSignals.length > 0 && !isScannerMode && (
              <Button
                variant={selectMode ? 'secondary' : 'ghost'}
                size="sm"
                className="h-7 text-xs cursor-pointer ml-1"
                onClick={() => {
                  setSelectMode(!selectMode);
                  if (selectMode) setSelectedOppIds(new Set());
                }}
              >
                {selectMode ? 'Cancel Select' : 'Select'}
              </Button>
            )}
          </div>
        </div>

        {/* Bulk Action Bar (When in Select Mode) */}
        {selectMode && (
          <div className="flex items-center justify-between bg-primary/10 border border-primary/20 rounded-lg p-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-medium text-primary">
                {selectedOppIds.size} of {oppSignals.length} selected
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-[11px] cursor-pointer"
                onClick={() => {
                  if (selectedOppIds.size === oppSignals.length) setSelectedOppIds(new Set());
                  else setSelectedOppIds(new Set(oppSignals.map((s) => s.id || s.signal_id)));
                }}
              >
                {selectedOppIds.size === oppSignals.length ? 'Deselect All' : 'Select All'}
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="destructive"
                size="sm"
                className="h-6 text-[11px] cursor-pointer"
                disabled={selectedOppIds.size === 0 || bulkDeletingOpp}
                onClick={async () => {
                  if (selectedOppIds.size === 0) return;
                  try {
                    setBulkDeletingOpp(true);
                    await api.bulkDeleteSignals({ signal_ids: Array.from(selectedOppIds) });
                    setActive((prev) => prev.filter((s) => !selectedOppIds.has(s.id || s.signal_id)));
                    setSelectedOppIds(new Set());
                    setSelectMode(false);
                  } catch (e: any) {
                    console.error('Bulk delete failed:', e);
                  } finally {
                    setBulkDeletingOpp(false);
                  }
                }}
              >
                {bulkDeletingOpp ? 'Deleting...' : `Delete Selected (${selectedOppIds.size})`}
              </Button>
            </div>
          </div>
        )}

        {/* Signal Diagnostics Pill Bar */}
        <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1 border-t flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <span>
              Showing: <strong className="text-foreground">{oppSignals.length}</strong> {isScannerMode ? 'scanner' : 'live'} setups
            </span>
            {isScannerMode && (
              <span className="text-muted-foreground/70">
                Universe: {scanDiagnostics.reduce((acc, d) => acc + (d.scanned ?? d.candidates_found ?? 0), 0)} scanned
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 font-mono">
            {(() => {
              const counts: Record<string, number> = {};
              oppSignals.forEach((s) => {
                const inst = s.instrument || s.underlying || 'UNKNOWN';
                counts[inst] = (counts[inst] || 0) + 1;
              });
              return Object.entries(counts).map(([inst, cnt]) => (
                <span key={inst} className="bg-muted px-1.5 py-0.5 rounded text-[10px]">
                  {inst}: {cnt}
                </span>
              ));
            })()}
          </div>
        </div>
      </Card>

      {activeError && oppSource === 'live' && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive flex items-center gap-2 flex-wrap">
          <AlertTriangle className="w-4 h-4 shrink-0" /> {activeError}
          <Button size="sm" variant="outline" className="h-7 text-[11px] ml-auto cursor-pointer" onClick={onRefreshActive}>
            Retry
          </Button>
        </div>
      )}

      {(loading || scannerLoading) && active.length === 0 && scannerData.length === 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="p-4 space-y-3 animate-pulse">
              <div className="h-4 bg-muted rounded w-32" />
              <div className="h-16 bg-muted rounded" />
            </Card>
          ))}
        </div>
      )}

      {oppSignals.length > 0 ? (
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
                {scannerError && (
                  <span className="text-[11px] text-destructive flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> {scannerError}
                  </span>
                )}
              </div>
              <SignalScannerTable
                signals={oppSignals}
                loading={scannerLoading}
                onInspectSignal={onInspectSignal}
              />
            </Card>
          )}

          {!isScannerMode && viewMode === 'grid' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {oppSignals.map((signal) => {
                const sid = signal.id || signal.signal_id;
                return (
                  <SignalCard
                    key={sid}
                    signal={signal}
                    cardsNowMs={cardsNowMs}
                    onInspect={() => onInspectSignal(sid)}
                    selectMode={selectMode}
                    isSelected={selectedOppIds.has(sid)}
                    onToggleSelect={(id: string) => {
                      setSelectedOppIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(id)) next.delete(id);
                        else next.add(id);
                        return next;
                      });
                    }}
                    onDeleted={(deletedId) => {
                      setActive((prev) => prev.filter((s) => (s.id || s.signal_id) !== deletedId));
                    }}
                  />
                );
              })}
            </div>
          )}

          {!isScannerMode && viewMode === 'table' && (
            <SignalScannerTable
              signals={oppSignals}
              loading={loading}
              onInspectSignal={onInspectSignal}
            />
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
    </div>
  );
}
