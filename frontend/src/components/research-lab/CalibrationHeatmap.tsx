'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { Card, DirectionBadge, EmptyNote, Stat, fmtNum, fmtPct01 } from '@/components/ui/desk';
import { Button } from '@/components/ui/button';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { useInstrument } from '@/context/InstrumentContext';
import { ErrorNote, ExportButtons, SectionLabel } from './controls';
import { exportAsJson, exportRowsAsCsv, timestampSlug } from './export';
import {
  asRecord,
  errorMessage,
  parseCalibration,
  parseSettlementSummary,
  type CalibrationSummaryRow,
  type SettlementSummaryRow,
} from './contracts';

function horizonLabel(minutes: number | null): string {
  if (minutes === null) return '—';
  if (minutes < 60) return `${minutes}m`;
  return `${fmtNum(minutes / 60, 1)}h`;
}

export const CalibrationHeatmap: React.FC = () => {
  const { instrument } = useInstrument();
  const [calibration, setCalibration] = useState<CalibrationSummaryRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);
  const [settling, setSettling] = useState(false);
  const [settlement, setSettlement] = useState<SettlementSummaryRow | null>(null);
  const [settleError, setSettleError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getMLCalibration(instrument);
      const data = asRecord(res)?.data;
      const parsed = parseCalibration(data);
      if (!parsed) {
        setCalibration(null);
        setError('Calibration response did not match the settled-rows summary contract.');
        return;
      }
      setCalibration(parsed);
      setLastLoadedAt(new Date());
    } catch (err) {
      setCalibration(null);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [instrument]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSettle = async () => {
    setSettling(true);
    setSettleError(null);
    try {
      const res = await api.runMLSettlement(instrument);
      const data = asRecord(res)?.data;
      const parsed = parseSettlementSummary(data);
      if (!parsed) {
        setSettlement(null);
        setSettleError('Settlement response did not include settled/skipped/errors counts.');
        return;
      }
      setSettlement(parsed);
      await load();
    } catch (err) {
      setSettlement(null);
      setSettleError(errorMessage(err));
    } finally {
      setSettling(false);
    }
  };

  const cells = useMemo(() => calibration?.cells ?? [], [calibration]);
  const skippedEntries = useMemo(
    () => Object.entries(settlement?.skipped ?? {}),
    [settlement],
  );

  const exportRows = useMemo<Array<Record<string, unknown>>>(() => {
    return cells.map((cell) => ({
      symbol: cell.symbol,
      horizon_minutes: cell.horizon_minutes,
      predicted_bias: cell.predicted_bias,
      n: cell.n,
      hits: cell.hits,
      hit_rate: cell.hit_rate,
      avg_confidence: cell.avg_confidence,
    }));
  }, [cells]);

  const handleExportJson = () => {
    exportAsJson(`ml-calibration-${instrument}-${timestampSlug()}.json`, {
      calibration,
      settlement,
    });
  };

  const handleExportCsv = () => {
    exportRowsAsCsv(`ml-calibration-${instrument}-${timestampSlug()}.csv`, exportRows);
  };

  return (
    <Card
      title="MODEL CALIBRATION & SETTLEMENT"
      meta={`${instrument} · settled predictions`}
      action={
        <div className="flex items-center gap-1.5">
          <ExportButtons
            onJson={calibration || settlement ? handleExportJson : undefined}
            onCsv={exportRows.length > 0 ? handleExportCsv : undefined}
          />
          <Button type="button" variant="outline" size="xs" onClick={() => void handleSettle()} disabled={settling || loading}>
            {settling ? 'Settling…' : 'Auto-settle due'}
          </Button>
        </div>
      }
    >
      <div className="space-y-3 text-xs">
        {loading ? <p className="muted" style={{ margin: 0 }}>Loading settled predictions…</p> : null}
        {error ? <ErrorNote message={error} onRetry={() => void load()} /> : null}
        {settleError ? <ErrorNote message={settleError} /> : null}

        {settlement ? (
          <div className="rounded border border-border bg-surface-subtle p-2 space-y-1">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-semibold text-ink">Settlement run</span>
              <span>settled {settlement.settled ?? '—'}</span>
              <span>errors {settlement.errors ?? '—'}</span>
            </div>
            {skippedEntries.length > 0 ? (
              <p className="muted" style={{ margin: 0 }}>
                skipped:{' '}
                {skippedEntries.map(([reason, count]) => `${reason} ${count}`).join(' · ')}
              </p>
            ) : null}
          </div>
        ) : null}

        {calibration ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <Stat label="Settled rows" value={calibration.overall === null ? '—' : calibration.overall.n} />
              <Stat
                label="Overall hit rate"
                value={
                  calibration.overall?.hit_rate === null || calibration.overall?.hit_rate === undefined
                    ? '—'
                    : fmtPct01(calibration.overall.hit_rate)
                }
              />
              <Stat label="Cells" value={cells.length} />
              <Stat label="Target spec" value={calibration.target_spec_version ?? '—'} />
            </div>

            {cells.length === 0 ? (
              <EmptyNote>
                No settled predictions for {instrument} yet. Auto-settle resolves predictions whose
                horizon has elapsed; skipped rows stay unsettled for the next run.
              </EmptyNote>
            ) : (
              <div>
                <SectionLabel>Per-horizon / per-bias hit rates</SectionLabel>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  {cells.map((cell) => {
                    const lowSample = cell.n < 30;
                    return (
                      <div
                        key={`${cell.symbol ?? ''}-${cell.horizon_minutes ?? 'x'}-${cell.predicted_bias}`}
                        className="rounded border border-border bg-surface-subtle p-2 space-y-1"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <DirectionBadge direction={cell.predicted_bias} />
                          <span className="faint num">{horizonLabel(cell.horizon_minutes)}</span>
                        </div>
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="num text-base font-semibold text-ink">
                            {cell.hit_rate === null ? '—' : fmtPct01(cell.hit_rate)}
                          </span>
                          <span className="faint">
                            {cell.hits ?? '—'}/{cell.n} · conf {cell.avg_confidence === null ? '—' : fmtPct01(cell.avg_confidence)}
                          </span>
                        </div>
                        {lowSample ? (
                          <div className="text-[10px] text-warn-ink">
                            n&lt;30 — hit rate is statistical noise
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {calibration.excluded_other_spec_versions ? (
              <p className="muted" style={{ margin: 0 }}>
                {calibration.excluded_other_spec_versions} settled rows excluded — labelled under a
                different target spec version.
              </p>
            ) : null}
          </>
        ) : null}

        <div className="flex items-center justify-end">
          <FreshnessClock lastAt={lastLoadedAt} fetching={loading || settling} sourceLabel="REST · ml/calibration" />
        </div>
      </div>
    </Card>
  );
};
