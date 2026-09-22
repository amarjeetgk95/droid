'use client';

import { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, RefreshCw, Filter } from 'lucide-react';
import { api } from '@/lib/api';
import type { CandleRecord } from '@/lib/api/historical';

interface CandleInspectorTableProps {
  initialSymbol?: string;
  initialTimeframe?: string;
}

export function CandleInspectorTable({
  initialSymbol = 'SENSEX',
  initialTimeframe = '1m',
}: CandleInspectorTableProps) {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [timeframe, setTimeframe] = useState(initialTimeframe);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [candles, setCandles] = useState<CandleRecord[]>([]);
  const [totalPages, setTotalPages] = useState(1);
  const [totalRecords, setTotalRecords] = useState(0);
  const [loading, setLoading] = useState(false);
  const [sortDesc, setSortDesc] = useState(true);

  const fetchCandles = async () => {
    setLoading(true);
    try {
      const res = await api.getHistoricalCandles({
        symbol,
        timeframe,
        page,
        page_size: pageSize,
        sort_desc: sortDesc,
      });
      setCandles(res.candles || []);
      setTotalPages(res.total_pages || 1);
      setTotalRecords(res.total_records || 0);
    } catch (err) {
      setCandles([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCandles();
  }, [symbol, timeframe, page, pageSize, sortDesc]);

  const formatIST = (utcStr: string) => {
    try {
      const d = new Date(utcStr);
      return d.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
    } catch {
      return utcStr;
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card shadow-sm">
      {/* Header and Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Candle Inspector</h3>
          <p className="text-xs text-muted-foreground">
            Server-side paginated inspection of normalized historical candles stored in local Parquet.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Symbol Select */}
          <select
            value={symbol}
            onChange={(e) => {
              setSymbol(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:border-primary focus:outline-none"
          >
            <option value="SENSEX">SENSEX</option>
            <option value="NIFTY">NIFTY</option>
            <option value="BANKNIFTY">BANKNIFTY</option>
          </select>

          {/* Timeframe Select */}
          <select
            value={timeframe}
            onChange={(e) => {
              setTimeframe(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:border-primary focus:outline-none"
          >
            <option value="1m">1m</option>
            <option value="5m">5m</option>
            <option value="15m">15m</option>
            <option value="1D">1D</option>
          </select>

          {/* Sort Order */}
          <button
            onClick={() => setSortDesc(!sortDesc)}
            className="rounded-lg border border-border bg-muted px-2.5 py-1 text-xs text-foreground hover:bg-accent"
          >
            {sortDesc ? 'Newest First' : 'Oldest First'}
          </button>

          <button
            onClick={fetchCandles}
            disabled={loading}
            className="rounded-lg border border-border bg-muted p-1.5 text-foreground hover:bg-accent disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead className="border-b border-border bg-muted/50 font-sans text-muted-foreground">
            <tr>
              <th className="px-6 py-3 font-medium">Timestamp (IST)</th>
              <th className="px-4 py-3 font-medium">Open</th>
              <th className="px-4 py-3 font-medium">High</th>
              <th className="px-4 py-3 font-medium">Low</th>
              <th className="px-4 py-3 font-medium">Close</th>
              <th className="px-6 py-3 font-medium text-right">Volume</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {candles.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center font-sans text-muted-foreground">
                  {loading ? 'Scanning Parquet...' : 'No candles found for this dataset resolution.'}
                </td>
              </tr>
            ) : (
              candles.map((c, i) => {
                const isBull = c.close >= c.open;
                return (
                  <tr key={i} className="transition-colors hover:bg-muted/20">
                    <td className="px-6 py-2.5 text-muted-foreground">{formatIST(c.timestamp)}</td>
                    <td className="px-4 py-2.5 text-foreground">{c.open.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-bull">{c.high.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-bear">{c.low.toFixed(2)}</td>
                    <td className={`px-4 py-2.5 font-semibold ${isBull ? 'text-bull' : 'text-bear'}`}>
                      {c.close.toFixed(2)}
                    </td>
                    <td className="px-6 py-2.5 text-right text-muted-foreground">
                      {c.volume.toLocaleString()}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="flex items-center justify-between border-t border-border px-6 py-3 text-xs text-muted-foreground">
        <div>
          Showing {candles.length > 0 ? (page - 1) * pageSize + 1 : 0} to{' '}
          {Math.min(page * pageSize, totalRecords)} of {totalRecords.toLocaleString()} candles
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1 || loading}
            className="inline-flex items-center gap-1 rounded-lg border border-border bg-muted px-2.5 py-1 text-foreground hover:bg-accent disabled:opacity-40"
          >
            <ChevronLeft className="h-3.5 w-3.5" /> Previous
          </button>
          <span className="font-mono">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages || loading}
            className="inline-flex items-center gap-1 rounded-lg border border-border bg-muted px-2.5 py-1 text-foreground hover:bg-accent disabled:opacity-40"
          >
            Next <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
