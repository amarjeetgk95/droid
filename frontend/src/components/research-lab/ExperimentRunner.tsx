'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { Card, EmptyNote, Stat, fmtNum } from '@/components/ui/desk';
import { Button } from '@/components/ui/button';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { useInstrument } from '@/context/InstrumentContext';
import { ErrorNote, ExportButtons, SectionLabel } from './controls';
import { exportAsJson, exportRowsAsCsv, timestampSlug } from './export';
import {
  asRecord,
  clampInt,
  errorMessage,
  parseExperimentResult,
  type ExperimentResultRow,
  type IndicatorDefinitionRow,
} from './contracts';

function pct(value: number | null): string {
  return value === null ? '—' : `${fmtNum(value, 2)}%`;
}

export const ExperimentRunner: React.FC = () => {
  const { instrument, timeframe } = useInstrument();
  const [indicators, setIndicators] = useState<IndicatorDefinitionRow[]>([]);
  const [registryLoading, setRegistryLoading] = useState(true);
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [horizon, setHorizon] = useState(5);
  const [stride, setStride] = useState(5);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExperimentResultRow | null>(null);
  const [lastRunAt, setLastRunAt] = useState<Date | null>(null);

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

  const handleRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedId || running) return;
    setRunning(true);
    setError(null);
    try {
      const res = await api.runResearchExperiment({
        indicator_id: selectedId,
        instrument,
        timeframe,
        horizon_candles: clampInt(horizon, 1, 50),
        stride: clampInt(stride, 1, 20),
      });
      const parsed = parseExperimentResult(res);
      if (!parsed) {
        setResult(null);
        setError('Experiment response did not contain the expected run + report payload.');
        return;
      }
      setResult(parsed);
      setLastRunAt(new Date());
    } catch (err) {
      setResult(null);
      setError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  };

  const report = result?.report ?? null;

  const handleExportJson = () => {
    if (!result) return;
    exportAsJson(`experiment-${result.run.run_id ?? timestampSlug()}.json`, result);
  };

  const handleExportCsv = () => {
    if (!result || !report) return;
    const rows: Array<Record<string, unknown>> = [
      { metric: 'run_status', value: result.run.status },
      { metric: 'run_id', value: result.run.run_id },
      { metric: 'sample_count', value: result.run.sample_count },
      { metric: 'sample_size', value: report.sample_size },
      { metric: 'accuracy_pct', value: report.accuracy },
      { metric: 'baseline_accuracy_pct', value: report.baseline_accuracy },
      { metric: 'excess_accuracy_pct', value: report.excess_accuracy },
      { metric: 'precision_pct', value: report.precision },
      { metric: 'recall_pct', value: report.recall },
      { metric: 'f1_pct', value: report.f1_score },
      { metric: 'mfe_mean', value: report.mfe_mean },
      { metric: 'mae_mean', value: report.mae_mean },
      { metric: 'win_loss_ratio', value: report.win_loss_ratio },
      { metric: 'ci_low_pct', value: report.confidence_interval_95?.[0] ?? null },
      { metric: 'ci_high_pct', value: report.confidence_interval_95?.[1] ?? null },
      { metric: 'p_value', value: report.p_value },
      { metric: 'significant', value: report.is_statistically_significant },
    ];
    exportRowsAsCsv(`experiment-${result.run.run_id ?? timestampSlug()}.csv`, rows);
  };

  const power = asRecord(result?.run.metrics)?.power;
  const powerRow = asRecord(power);

  return (
    <Card
      title="QUANT VALIDATION GATE"
      meta={`${instrument} · ${timeframe}`}
      action={result ? <ExportButtons onJson={handleExportJson} onCsv={handleExportCsv} /> : null}
    >
      <form onSubmit={handleRun} className="space-y-3 text-xs">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="sm:col-span-1">
            <SectionLabel>Indicator</SectionLabel>
            {registryLoading ? (
              <p className="muted" style={{ margin: 0 }}>Loading registry…</p>
            ) : indicators.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>No registered indicators.</p>
            ) : (
              <select
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                className="input input-sm w-full"
                aria-label="Indicator"
              >
                {indicators.map((ind) => (
                  <option key={ind.indicator_id} value={ind.indicator_id}>
                    {ind.name} ({ind.indicator_id})
                  </option>
                ))}
              </select>
            )}
          </div>
          <div>
            <SectionLabel>Horizon (candles)</SectionLabel>
            <input
              type="number"
              min={1}
              max={50}
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
              className="input input-sm w-full num"
              aria-label="Horizon candles"
            />
          </div>
          <div>
            <SectionLabel>Stride</SectionLabel>
            <input
              type="number"
              min={1}
              max={20}
              value={stride}
              onChange={(e) => setStride(Number(e.target.value))}
              className="input input-sm w-full num"
              aria-label="Stride"
            />
          </div>
        </div>

        {selected ? (
          <p className="muted" style={{ margin: 0 }}>
            {selected.description ?? 'Registry entry'} · lifecycle {selected.lifecycle ?? '—'} · v
            {selected.current_version ?? '—'}
          </p>
        ) : null}

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={running || !selectedId || registryLoading}>
            {running ? 'Running validation gate…' : 'Run validation experiment'}
          </Button>
          {registryError ? <ErrorNote message={`Indicator registry unavailable — ${registryError}`} onRetry={loadRegistry} /> : null}
        </div>

        {error ? <ErrorNote message={error} /> : null}

        {!result && !error && !running ? (
          <EmptyNote>
            No experiment has run yet. The gate backtests the selected indicator over historical
            candles with point-in-time integrity.
          </EmptyNote>
        ) : null}

        {result ? (
          <div className="space-y-3 pt-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`badge ${result.run.status === 'COMPLETED' ? 'b-bull' : result.run.status === 'FAILED' ? 'b-bear' : 'b-neut'}`}>
                {result.run.status}
              </span>
              {result.run.run_id ? <span className="faint mono">{result.run.run_id}</span> : null}
              <span className="spacer" />
              <FreshnessClock
                lastAt={result.run.completed_at ?? lastRunAt}
                fetching={running}
                sourceLabel="POST · experiments/run"
              />
            </div>

            {result.run.error_message ? (
              <ErrorNote message={result.run.error_message} />
            ) : null}

            {report ? (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <Stat label="Accuracy" value={pct(report.accuracy)} />
                  <Stat label="Baseline" value={pct(report.baseline_accuracy)} />
                  <Stat
                    label="Excess"
                    value={pct(report.excess_accuracy)}
                    tone={
                      report.excess_accuracy === null
                        ? undefined
                        : report.excess_accuracy > 0
                          ? 'bull'
                          : report.excess_accuracy < 0
                            ? 'bear'
                            : 'neut'
                    }
                  />
                  <Stat label="Samples" value={report.sample_size ?? '—'} />
                  <Stat label="Precision" value={pct(report.precision)} />
                  <Stat label="Recall" value={pct(report.recall)} />
                  <Stat label="F1" value={pct(report.f1_score)} />
                  <Stat label="Win/Loss" value={report.win_loss_ratio === null ? '—' : fmtNum(report.win_loss_ratio, 2)} />
                  <Stat label="MFE mean" value={report.mfe_mean === null ? '—' : fmtNum(report.mfe_mean, 2)} />
                  <Stat label="MAE mean" value={report.mae_mean === null ? '—' : fmtNum(report.mae_mean, 2)} />
                  <Stat label="p-value" value={report.p_value === null ? '—' : fmtNum(report.p_value, 4)} />
                  <Stat
                    label="Significant"
                    value={
                      report.is_statistically_significant === null
                        ? '—'
                        : report.is_statistically_significant
                          ? `YES (α 0.05)`
                          : 'NO'
                    }
                    tone={report.is_statistically_significant ? 'bull' : 'neut'}
                  />
                </div>

                <p className="muted" style={{ margin: 0 }}>
                  95% CI:{' '}
                  {report.confidence_interval_95
                    ? `${pct(report.confidence_interval_95[0])} – ${pct(report.confidence_interval_95[1])}`
                    : '—'}
                  {powerRow
                    ? ` · power: ${String(powerRow.status ?? '—')} (n=${fmtNum(powerRow.n, 0)} / required ${fmtNum(powerRow.required_n, 0)})`
                    : ''}
                </p>
              </>
            ) : null}
          </div>
        ) : null}
      </form>
    </Card>
  );
};
