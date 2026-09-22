'use client';

import { useState } from 'react';
import { Eye, FileDown, ShieldCheck, Layers, RefreshCw } from 'lucide-react';
import type { HistoricalDataset } from '@/lib/api/historical';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/toast';

interface DatasetCatalogTableProps {
  datasets: HistoricalDataset[];
  onSelectInspect: (symbol: string, timeframe: string) => void;
  onDatasetUpdated?: () => void;
}

export function DatasetCatalogTable({
  datasets,
  onSelectInspect,
  onDatasetUpdated,
}: DatasetCatalogTableProps) {
  const { push } = useToast();
  const [derivingSymbol, setDerivingSymbol] = useState<string | null>(null);

  const handleDerive = async (symbol: string) => {
    setDerivingSymbol(symbol);
    try {
      const res = await api.deriveHistoricalTimeframes({ symbol, source_timeframe: '1m' });
      push(
        'success',
        'Timeframes Derived',
        `Generated ${res.derived_count} derived datasets (5m, 15m, 30m, 1h, 1D) for ${symbol}.`
      );
      if (onDatasetUpdated) onDatasetUpdated();
    } catch (err: any) {
      push('error', 'Derivation Failed', err?.message || 'Failed to derive timeframes.');
    } finally {
      setDerivingSymbol(null);
    }
  };

  if (datasets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card p-12 text-center">
        <ShieldCheck className="h-10 w-10 text-muted-foreground" />
        <h3 className="mt-3 text-sm font-semibold text-foreground">No Historical Datasets Ingested Yet</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Use the Ingestion Wizard to acquire SENSEX 1-minute historical data from FYERS.
        </p>
        <button
          onClick={async () => {
            try {
              await api.syncHistoricalDatasets();
              if (onDatasetUpdated) onDatasetUpdated();
            } catch {}
          }}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted/80"
        >
          <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" /> Rescan Local Parquet Files
        </button>
      </div>
    );
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'READY':
        return (
          <span className="inline-flex items-center rounded-full bg-bull/10 px-2 py-0.5 text-xs font-medium text-bull">
            READY
          </span>
        );
      case 'DEGRADED':
        return (
          <span className="inline-flex items-center rounded-full bg-bear/10 px-2 py-0.5 text-xs font-medium text-bear">
            DEGRADED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {status}
          </span>
        );
    }
  };

  const getQualityBadge = (score: number) => {
    const isGood = score >= 95.0;
    const isWarn = score >= 80.0 && score < 95.0;
    return (
      <span
        className={`font-semibold ${
          isGood ? 'text-bull' : isWarn ? 'text-foreground' : 'text-bear'
        }`}
      >
        {score.toFixed(1)}%
      </span>
    );
  };

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      <div className="border-b border-border px-6 py-4">
        <h3 className="text-sm font-semibold text-foreground">Registered Historical Datasets</h3>
        <p className="text-xs text-muted-foreground">
          Canonical index datasets versioned for research, backtesting, and AI feature calibration.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-border bg-muted/50 text-muted-foreground">
            <tr>
              <th className="px-6 py-3 font-medium">Symbol</th>
              <th className="px-4 py-3 font-medium">Timeframe</th>
              <th className="px-4 py-3 font-medium">Exchange</th>
              <th className="px-4 py-3 font-medium">Candles</th>
              <th className="px-4 py-3 font-medium">Quality</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Last Version</th>
              <th className="px-6 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {datasets.map((d) => (
              <tr key={d.id} className="transition-colors hover:bg-muted/30">
                <td className="px-6 py-3 font-semibold text-foreground">{d.symbol}</td>
                <td className="px-4 py-3 text-muted-foreground">{d.timeframe}</td>
                <td className="px-4 py-3 text-muted-foreground">{d.exchange}</td>
                <td className="px-4 py-3 font-medium text-foreground">
                  {d.total_candles.toLocaleString()}
                </td>
                <td className="px-4 py-3">{getQualityBadge(d.latest_quality_score)}</td>
                <td className="px-4 py-3">{getStatusBadge(d.status)}</td>
                <td className="px-4 py-3 text-muted-foreground">
                  {d.current_version_id?.split('_').pop() || 'None'}
                </td>
                <td className="px-6 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    {/* One-click derive for 1m base datasets */}
                    {d.timeframe.toLowerCase() === '1m' && (
                      <button
                        onClick={() => handleDerive(d.symbol)}
                        disabled={derivingSymbol === d.symbol}
                        title="Derive 5m, 15m, 30m, 1h, 1D datasets automatically"
                        className="inline-flex items-center gap-1 rounded border border-primary/30 bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/20 disabled:opacity-50"
                      >
                        {derivingSymbol === d.symbol ? (
                          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Layers className="h-3.5 w-3.5" />
                        )}
                        Derive 5m–1D
                      </button>
                    )}
                    <button
                      onClick={() => onSelectInspect(d.symbol, d.timeframe)}
                      title="Inspect Candles"
                      className="inline-flex items-center gap-1 rounded border border-border bg-muted px-2 py-1 text-xs text-foreground hover:bg-accent"
                    >
                      <Eye className="h-3.5 w-3.5" /> Inspect
                    </button>
                    <a
                      href={api.getHistoricalExportUrl(d.symbol, d.timeframe, 'v1', 'parquet')}
                      title="Export Parquet"
                      className="inline-flex items-center gap-1 rounded border border-border bg-muted px-2 py-1 text-xs text-foreground hover:bg-accent"
                    >
                      <FileDown className="h-3.5 w-3.5" /> Parquet
                    </a>
                    <a
                      href={api.getHistoricalExportUrl(d.symbol, d.timeframe, 'v1', 'csv')}
                      title="Export CSV"
                      className="inline-flex items-center gap-1 rounded border border-border bg-muted px-2 py-1 text-xs text-foreground hover:bg-accent"
                    >
                      <FileDown className="h-3.5 w-3.5" /> CSV
                    </a>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
