'use client';

import { useState } from 'react';
import { Calendar, Download, RefreshCw, AlertCircle, CheckCircle2 } from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/toast';

interface DownloadWizardModalProps {
  onJobStarted?: () => void;
}

export function DownloadWizardModal({ onJobStarted }: DownloadWizardModalProps) {
  const { push } = useToast();
  const [symbol, setSymbol] = useState('SENSEX');
  const [timeframe, setTimeframe] = useState('1m');
  const [forceRefresh, setForceRefresh] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Default to previous 12 months
  const todayStr = new Date().toISOString().split('T')[0];
  const oneYearAgo = new Date();
  oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
  const defaultStartStr = oneYearAgo.toISOString().split('T')[0];

  const [rangeFrom, setRangeFrom] = useState(defaultStartStr);
  const [rangeTo, setRangeTo] = useState(todayStr);

  // Estimate chunks (approx 95 days per chunk)
  const daysDiff = Math.max(1, Math.round((new Date(rangeTo).getTime() - new Date(rangeFrom).getTime()) / (1000 * 3600 * 24)));
  const estimatedChunks = Math.ceil(daysDiff / 95);

  const handlePreset = (months: number) => {
    const d = new Date();
    d.setMonth(d.getMonth() - months);
    setRangeFrom(d.toISOString().split('T')[0]);
    setRangeTo(new Date().toISOString().split('T')[0]);
  };

  const handleStartDownload = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await api.triggerHistoricalDownload({
        symbol,
        timeframe,
        range_from: rangeFrom,
        range_to: rangeTo,
        force_refresh: forceRefresh,
      });
      push('success', 'Download Job Enqueued', `Job ${res.job.job_id} scheduled with ${res.job.total_chunks} chunk(s).`);
      if (onJobStarted) onJobStarted();
    } catch (err: any) {
      push('error', 'Download Failed', err?.message || 'Failed to trigger historical download.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-6 flex items-center justify-between border-b border-border pb-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Historical Ingestion Wizard</h2>
          <p className="text-xs text-muted-foreground">
            Acquire and validate historical candles with automated chunking, geometric OHLC gating, and session gap detection.
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
          <Download className="h-3.5 w-3.5" /> FYERS API v3
        </span>
      </div>

      <form onSubmit={handleStartDownload} className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* Symbol */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
              Instrument Symbol
            </label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
            >
              <option value="SENSEX">SENSEX (BSE)</option>
              <option value="NIFTY">NIFTY 50 (NSE)</option>
              <option value="BANKNIFTY">BANKNIFTY (NSE)</option>
              <option value="FINNIFTY">FINNIFTY (NSE)</option>
            </select>
          </div>

          {/* Timeframe */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
              Candle Resolution
            </label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
            >
              <option value="1m">1 Minute (Primary Base)</option>
              <option value="5m">5 Minutes</option>
              <option value="15m">15 Minutes</option>
              <option value="1D">Daily (1D)</option>
            </select>
          </div>
        </div>

        {/* Presets */}
        <div>
          <span className="mb-2 block text-xs font-medium text-muted-foreground">Date Range Presets</span>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => handlePreset(12)}
              className="rounded-lg border border-border bg-muted px-3 py-1 text-xs font-medium text-foreground hover:bg-accent"
            >
              Previous 1 Year
            </button>
            <button
              type="button"
              onClick={() => handlePreset(6)}
              className="rounded-lg border border-border bg-muted px-3 py-1 text-xs font-medium text-foreground hover:bg-accent"
            >
              Previous 6 Months
            </button>
            <button
              type="button"
              onClick={() => handlePreset(1)}
              className="rounded-lg border border-border bg-muted px-3 py-1 text-xs font-medium text-foreground hover:bg-accent"
            >
              Previous 1 Month
            </button>
          </div>
        </div>

        {/* Date Inputs */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">From Date</label>
            <div className="relative">
              <input
                type="date"
                value={rangeFrom}
                onChange={(e) => setRangeFrom(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
                required
              />
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">To Date</label>
            <div className="relative">
              <input
                type="date"
                value={rangeTo}
                onChange={(e) => setRangeTo(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
                required
              />
            </div>
          </div>
        </div>

        {/* Chunk Strategy Notice */}
        <div className="rounded-lg border border-border bg-muted/40 p-4 text-xs">
          <div className="flex items-center gap-2 font-medium text-foreground">
            <Calendar className="h-4 w-4 text-primary" />
            <span>Chunking Strategy Plan</span>
          </div>
          <p className="mt-1 text-muted-foreground">
            Range spans <span className="font-semibold text-foreground">{daysDiff} days</span>. FYERS limits 1m requests to 100 days; engine will automatically partition this into <span className="font-semibold text-foreground">{estimatedChunks} sequential chunk(s)</span> with exponential backoff and rate protection.
          </p>
        </div>

        {/* Options */}
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="forceRefresh"
            checked={forceRefresh}
            onChange={(e) => setForceRefresh(e.target.checked)}
            className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
          />
          <label htmlFor="forceRefresh" className="text-xs text-foreground">
            Force re-download and overwrite existing range (re-validates and creates new version)
          </label>
        </div>

        <div className="flex justify-end pt-2">
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" /> Scheduling...
              </>
            ) : (
              <>
                <Download className="h-4 w-4" /> Start Ingestion Job
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
