'use client';

import React, { useCallback, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import type { FeedState } from '@/lib/feedState';

/**
 * Shared ops-panel state primitives for System Nerve.
 *
 * Truth-of-data contract for this module:
 * - a failed refresh never clears the last known payload; it surfaces as
 *   `stale` (data + error) and the banner says exactly that,
 * - no data + error renders DOWN/UNAVAILABLE, never a green default,
 * - every resource carries both the local fetch time and the backend's own
 *   generation timestamp (`meta.timestamp` / `generated_at`) when provided,
 * - polling is delegated to `usePolling`, which pauses while the tab is hidden.
 */

export interface PanelResource<T> {
  data: T | null;
  error: string | null;
  /** Local clock time of the last successful fetch. */
  updatedAt: number | null;
  /** Backend-reported generation timestamp extracted from the payload. */
  generatedAt: string | null;
  fetching: boolean;
  /** A refresh failed but the previous payload is still displayed. */
  stale: boolean;
  refresh: () => void;
}

export function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (typeof error === 'string' && error.trim()) return error;
  return 'Request failed with no error detail.';
}

export function asNumber(value: unknown): number | null {
  const n = typeof value === 'string' && value.trim() !== '' ? Number(value) : value;
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

export function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

export function formatStamp(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined || value === '') return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString([], { hour12: false });
}

export function formatDuration(seconds: number | null | undefined): string | null {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return null;
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function formatPercent(value: number | null, digits = 1): string | null {
  if (value === null || !Number.isFinite(value)) return null;
  return `${value.toFixed(digits)}%`;
}

/**
 * Poll a backend resource, keeping the last successful payload on failure so
 * the UI can render an explicit STALE/ERROR state instead of pretending.
 */
export function usePanelResource<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  extractGeneratedAt?: (value: T) => string | null,
): PanelResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const extractRef = useRef(extractGeneratedAt);
  extractRef.current = extractGeneratedAt;
  const requestSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = requestSeq.current + 1;
    requestSeq.current = seq;
    setFetching(true);
    try {
      const value = await fetcherRef.current();
      if (seq !== requestSeq.current) return;
      setData(value);
      setError(null);
      setUpdatedAt(Date.now());
      setGeneratedAt(extractRef.current ? extractRef.current(value) : null);
    } catch (err) {
      if (seq !== requestSeq.current) return;
      setError(toErrorMessage(err));
    } finally {
      if (seq === requestSeq.current) setFetching(false);
    }
  }, []);

  usePolling(load, intervalMs);

  return {
    data,
    error,
    updatedAt,
    generatedAt,
    fetching,
    stale: error !== null && data !== null,
    refresh: load,
  };
}

export interface TelemetryTileProps {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  title?: string;
}

export const TelemetryTile: React.FC<TelemetryTileProps> = ({ label, value, sub, title }) => (
  <div className="p-2.5 rounded-md bg-surface-subtle border border-border min-w-0" title={title}>
    <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">{label}</div>
    <div className="flex flex-wrap items-center gap-1.5 text-sm font-bold text-ink mt-0.5">
      {value}
    </div>
    {sub ? <div className="text-[10px] text-ink-3 mt-0.5 break-words">{sub}</div> : null}
  </div>
);

export interface PanelStateBannerProps {
  label: string;
  error: string | null;
  hasData: boolean;
  updatedAt: number | null;
  onRetry: () => void;
}

/** Explicit stale/error banner with a retry affordance. Never optimistic. */
export const PanelStateBanner: React.FC<PanelStateBannerProps> = ({
  label,
  error,
  hasData,
  updatedAt,
  onRetry,
}) => {
  if (!error) return null;
  const stamp = formatStamp(updatedAt);
  return (
    <div className={`notice ${hasData ? 'notice--warn' : 'notice--down'}`} role="alert">
      <span className="min-w-0">
        <strong className="font-semibold">{label}:</strong>{' '}
        {hasData
          ? `refresh failed${stamp ? ` at ${stamp}` : ''} — showing last known values. `
          : 'unavailable. '}
        <span className="font-mono text-[11px]">{error}</span>
      </span>
      <button
        type="button"
        className="btn ml-auto"
        onClick={onRetry}
        aria-label={`Retry ${label} request`}
      >
        Retry
      </button>
    </div>
  );
};

export interface PanelFreshnessProps {
  error: string | null;
  hasData: boolean;
  updatedAt: number | null;
  generatedAt: string | null;
  intervalMs: number;
}

/** Per-panel freshness pill: LIVE / STALE / DOWN / SYNCING plus backend time. */
export const PanelFreshness: React.FC<PanelFreshnessProps> = ({
  error,
  hasData,
  updatedAt,
  generatedAt,
  intervalMs,
}) => {
  const state: FeedState | undefined =
    error && !hasData ? 'DOWN' : error && hasData ? 'STALE' : undefined;
  const server = formatStamp(generatedAt);
  return (
    <FreshnessClock
      state={state}
      lastAt={updatedAt}
      sourceLabel={`REST · ${Math.max(1, Math.round(intervalMs / 1000))}s poll`}
      note={server ? `server generated ${server}` : undefined}
    />
  );
};
