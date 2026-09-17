'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { Card, DirectionBadge, EmptyNote, Meter, Stat, fmtINR, fmtNum, fmtPct01, fmtSigned } from '@/components/ui/desk';
import { Button } from '@/components/ui/button';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { useInstrument } from '@/context/InstrumentContext';
import { ErrorNote, ExportButtons, SectionLabel, ValueGrid } from './controls';
import { exportAsJson, exportRowsAsCsv, timestampSlug } from './export';
import {
  errorMessage,
  flattenRecord,
  parseIndicatorOutput,
  type IndicatorDefinitionRow,
  type IndicatorOutputRow,
} from './contracts';

export const IndicatorWorkbench: React.FC = () => {
  const { instrument, timeframe } = useInstrument();
  const [indicators, setIndicators] = useState<IndicatorDefinitionRow[]>([]);
  const [registryLoading, setRegistryLoading] = useState(true);
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [calculating, setCalculating] = useState(false);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [output, setOutput] = useState<IndicatorOutputRow | null>(null);

  const loadRegistry = useCallback(async () => {
    setRegistryLoading(true);
    setRegistryError(null);
    try {
      const res = await api.getResearchIndicators();
      const rows = Array.isArray(res) ? (res as IndicatorDefinitionRow[]) : [];
      setIndicators(rows);
      setSelectedId((prev) =>
        rows.some((r) => r.indicator_id === prev) ? prev : (rows[0]?.indicator_id ?? ''),
      );
    } catch (err) {
      setIndicators([]);
      setRegistryError(errorMessage(err));
    } finally {
      setRegistryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRegistry();
  }, [loadRegistry]);

  const selected = useMemo(
    () => indicators.find((i) => i.indicator_id === selectedId) ?? null,
    [indicators, selectedId],
  );

  const handleCalculate = async () => {
    if (!selectedId || calculating) return;
    setCalculating(true);
    setCalcError(null);
    try {
      const res = await api.calculateResearchIndicator(selectedId, { instrument, timeframe });
      const parsed = parseIndicatorOutput(res);
      if (!parsed) {
        setOutput(null);
        setCalcError('Indicator response did not contain a valid output contract.');
        return;
      }
      setOutput(parsed);
    } catch (err) {
      setOutput(null);
      setCalcError(errorMessage(err));
    } finally {
      setCalculating(false);
    }
  };

  const componentEntries = useMemo(
    () => flattenRecord(output?.component_values ?? null),
    [output],
  );

  const hasRaw = output?.raw_value !== null && output?.raw_value !== undefined;

  const handleExportJson = () => {
    if (!output) return;
    exportAsJson(`indicator-${output.indicator_id}-${timestampSlug()}.json`, output);
  };

  const handleExportCsv = () => {
    if (!output || componentEntries.length === 0) return;
    exportRowsAsCsv(
      `indicator-${output.indicator_id}-${timestampSlug()}.csv`,
      componentEntries.map(({ key, value }) => ({
        indicator_id: output.indicator_id,
        version: output.version,
        component: key,
        value,
      })),
    );
  };

  return (
    <Card
      title="INDICATOR QUANT WORKBENCH"
      meta={`${instrument} · ${timeframe}`}
      action={
        <div className="flex items-center gap-1.5">
          <ExportButtons
            onJson={output ? handleExportJson : undefined}
            onCsv={output && componentEntries.length > 0 ? handleExportCsv : undefined}
            disabled={!output}
          />
          <Button
            type="button"
            onClick={handleCalculate}
            disabled={calculating || !selectedId}
            size="xs"
          >
            {calculating ? 'Computing…' : 'Calculate'}
          </Button>
        </div>
      }
    >
      <div className="space-y-3 text-xs">
        {registryLoading ? (
          <p className="muted" style={{ margin: 0 }}>Loading indicator registry…</p>
        ) : registryError ? (
          <ErrorNote message={`Indicator registry unavailable — ${registryError}`} onRetry={loadRegistry} />
        ) : indicators.length === 0 ? (
          <EmptyNote>No indicators are registered on this backend build.</EmptyNote>
        ) : (
          <>
            <div>
              <SectionLabel>Indicator</SectionLabel>
              <select
                value={selectedId}
                onChange={(e) => {
                  setSelectedId(e.target.value);
                  setOutput(null);
                  setCalcError(null);
                }}
                className="input input-sm w-full"
                aria-label="Indicator"
              >
                {indicators.map((ind) => (
                  <option key={ind.indicator_id} value={ind.indicator_id}>
                    {ind.name} ({ind.category ?? 'TECHNICAL'} · v{ind.current_version ?? '—'})
                  </option>
                ))}
              </select>
            </div>

            {selected?.description ? (
              <p className="muted" style={{ margin: 0 }}>{selected.description}</p>
            ) : null}

            {calcError ? <ErrorNote message={calcError} onRetry={handleCalculate} /> : null}

            {!output && !calcError ? (
              <EmptyNote>
                No calculation yet. Run Calculate to compute the registry indicator on live
                {' '}
                {instrument} {timeframe} candles.
              </EmptyNote>
            ) : null}

            {output ? (
              <div className="space-y-3 pt-1">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <Stat
                    label="Direction"
                    value={<DirectionBadge direction={output.direction} />}
                  />
                  <Stat
                    label="Score (±100)"
                    value={output.score === null ? '—' : fmtSigned(output.score, 2)}
                    tone={output.score === null ? undefined : output.score > 0 ? 'bull' : output.score < 0 ? 'bear' : 'neut'}
                  />
                  <Stat
                    label="Confidence"
                    value={output.confidence === null ? '—' : fmtPct01(output.confidence)}
                  />
                  <Stat label="Data quality" value={output.data_quality ?? '—'} />
                  <Stat label="Target" value={output.target_price === null ? '—' : fmtINR(output.target_price)} />
                  <Stat
                    label="Invalidation"
                    value={output.invalidation_price === null ? '—' : fmtINR(output.invalidation_price)}
                  />
                  <Stat label="Horizon" value={output.horizon ?? '—'} sub={output.horizon_candles === null ? undefined : `${output.horizon_candles} candles`} />
                  <Stat label="Version" value={`v${output.version}`} />
                </div>

                {output.confidence !== null ? (
                  <Meter value={output.confidence} label="Indicator confidence" />
                ) : null}

                <div>
                  <SectionLabel>Component values</SectionLabel>
                  <ValueGrid
                    entries={componentEntries}
                    emptyNote="The indicator returned no component breakdown for this instrument/timeframe."
                  />
                </div>

                {hasRaw || output.normalized_value !== null ? (
                  <p className="muted" style={{ margin: 0 }}>
                    raw {hasRaw ? JSON.stringify(output.raw_value) : '—'} · normalized{' '}
                    {output.normalized_value === null ? '—' : fmtNum(output.normalized_value, 4)}
                  </p>
                ) : null}

                <div className="flex items-center justify-between gap-2">
                  <span className="faint mono">
                    {output.indicator_id} · as of {output.timestamp || '—'}
                  </span>
                  <FreshnessClock
                    lastAt={output.timestamp || null}
                    fetching={calculating}
                    sourceLabel="POST · indicators/calculate"
                  />
                </div>
              </div>
            ) : null}
          </>
        )}
      </div>
    </Card>
  );
};
