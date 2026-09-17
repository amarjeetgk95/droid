'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { Card, EmptyNote, Stat, fmtINR } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { useInstrument } from '@/context/InstrumentContext';
import { ErrorNote, ExportButtons, SectionLabel, ValueGrid } from './controls';
import { exportAsJson, exportRowsAsCsv, timestampSlug } from './export';
import {
  asNumber,
  asRecord,
  asString,
  errorMessage,
  flattenRecord,
  isAbortError,
} from './contracts';

const POLL_MS = 5_000;

const FEATURE_GROUPS: Array<{ key: string; label: string }> = [
  { key: 'quant', label: 'Quant / technical' },
  { key: 'momentum_dynamics', label: 'Momentum dynamics' },
  { key: 'volume_dynamics', label: 'Volume dynamics' },
  { key: 'ta_suite', label: 'TA suite' },
  { key: 'options', label: 'Options context' },
];

export const FeatureInspector: React.FC = () => {
  const { instrument, timeframe } = useInstrument();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAt, setLastAt] = useState<Date | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setFetching(true);
    try {
      const res = await api.request<unknown>(
        `/api/v1/research/chart/features?instrument=${encodeURIComponent(instrument)}&timeframe=${encodeURIComponent(timeframe)}`,
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      const rec = asRecord(res);
      if (!rec) {
        setError('Feature response was not an object.');
        return;
      }
      const errorText = asString(rec.error);
      if (errorText) {
        setError(errorText);
        return;
      }
      setData(rec);
      setError(null);
      setLastAt(new Date());
    } catch (err) {
      if (isAbortError(err)) return;
      setError(errorMessage(err));
    } finally {
      if (!controller.signal.aborted) setFetching(false);
    }
  }, [instrument, timeframe]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void load();
    }, POLL_MS);
    return () => {
      clearInterval(timer);
      abortRef.current?.abort();
    };
  }, [load]);

  const groups = useMemo(() => {
    if (!data) return [];
    return FEATURE_GROUPS.map((group) => ({
      ...group,
      entries: flattenRecord(asRecord(data[group.key])),
    }));
  }, [data]);

  const asOf = asString(data?.timestamp);
  const currentPrice = asNumber(data?.current_price);
  const regime = asString(data?.regime);
  const session = asString(data?.session);
  const dataQuality = asString(data?.data_quality);
  const hasEntries = groups.some((group) => group.entries.length > 0);

  const handleExportJson = () => {
    if (!data) return;
    exportAsJson(`chart-features-${instrument}-${timeframe}-${timestampSlug()}.json`, data);
  };

  const handleExportCsv = () => {
    if (!data || !hasEntries) return;
    const rows = groups.flatMap((group) =>
      group.entries.map(({ key, value }) => ({
        instrument,
        timeframe,
        group: group.key,
        feature: key,
        value,
      })),
    );
    exportRowsAsCsv(`chart-features-${instrument}-${timeframe}-${timestampSlug()}.csv`, rows);
  };

  return (
    <Card
      title="FEATURE VECTOR INSPECTOR"
      meta={`${instrument} · ${timeframe} · ${POLL_MS / 1000}s poll`}
      action={
        <ExportButtons
          onJson={data ? handleExportJson : undefined}
          onCsv={data && hasEntries ? handleExportCsv : undefined}
          disabled={!data}
        />
      }
    >
      <div className="space-y-3 text-xs">
        {error ? (
          <ErrorNote
            message={
              data
                ? `Feature refresh failed — showing last good vector. ${error}`
                : `Feature layer unavailable — ${error}`
            }
            onRetry={() => void load()}
          />
        ) : null}

        {data ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <Stat label="Spot" value={currentPrice === null ? '—' : fmtINR(currentPrice)} />
              <Stat label="Regime" value={regime ?? '—'} />
              <Stat label="Session" value={session ?? '—'} />
              <Stat label="Data quality" value={dataQuality ?? '—'} />
            </div>

            {hasEntries ? (
              groups.map((group) =>
                group.entries.length > 0 ? (
                  <div key={group.key}>
                    <SectionLabel>{group.label}</SectionLabel>
                    <ValueGrid entries={group.entries} emptyNote="No values." />
                  </div>
                ) : null,
              )
            ) : (
              <EmptyNote>
                The feature layer returned no computable groups for {instrument} {timeframe}.
              </EmptyNote>
            )}
          </>
        ) : !error ? (
          <EmptyNote>Waiting for the first feature vector…</EmptyNote>
        ) : null}

        <div className="flex items-center justify-between gap-2">
          <span className="faint mono">{asOf ? `as of ${asOf}` : 'no timestamp'}</span>
          <FreshnessClock
            lastAt={asOf ?? lastAt}
            fetching={fetching}
            sourceLabel={`REST · ${POLL_MS / 1000}s poll`}
          />
        </div>
      </div>
    </Card>
  );
};
