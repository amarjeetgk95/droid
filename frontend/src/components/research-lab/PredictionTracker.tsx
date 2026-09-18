'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { Card, DirectionBadge, EmptyNote, fmtClock, fmtINR, fmtNum, fmtPct01, fmtSigned } from '@/components/ui/desk';
import { Button } from '@/components/ui/button';
import { DataTable, type Column } from '@/components/ui/data-table';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { useInstrument } from '@/context/InstrumentContext';
import { ErrorNote, ExportButtons } from './controls';
import { exportAsJson, exportRowsAsCsv, timestampSlug } from './export';
import {
  errorMessage,
  parseOutcome,
  parsePredictions,
  type PredictionOutcomeRow,
  type ResearchPredictionRow,
} from './contracts';

const PREDICTION_LIMIT = 50;

function shortId(id: string): string {
  return id.length > 14 ? `${id.slice(0, 14)}…` : id;
}

export const PredictionTracker: React.FC = () => {
  const { instrument } = useInstrument();
  const [predictions, setPredictions] = useState<ResearchPredictionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);
  const [measuringId, setMeasuringId] = useState<string | null>(null);
  const [measureError, setMeasureError] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<Record<string, PredictionOutcomeRow>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listResearchPredictions({ instrument, limit: PREDICTION_LIMIT });
      const rows = parsePredictions(res);
      if (!rows) {
        setPredictions([]);
        setError('Prediction list response was not an array.');
        return;
      }
      setPredictions(rows);
      setLastLoadedAt(new Date());
    } catch (err) {
      setPredictions([]);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [instrument]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleMeasure = async (predictionId: string) => {
    setMeasuringId(predictionId);
    setMeasureError(null);
    try {
      const res = await api.measureResearchPrediction(predictionId);
      const outcome = parseOutcome(res);
      if (!outcome) {
        setMeasureError(`Measure returned no outcome record for ${predictionId}.`);
        return;
      }
      setOutcomes((prev) => ({ ...prev, [outcome.prediction_id]: outcome }));
    } catch (err) {
      setMeasureError(`${predictionId}: ${errorMessage(err)}`);
    } finally {
      setMeasuringId(null);
    }
  };

  const exportRows = useMemo<Array<Record<string, unknown>>>(() => {
    return predictions.map((p) => {
      const outcome = outcomes[p.prediction_id];
      return {
        prediction_id: p.prediction_id,
        indicator_id: p.indicator_id,
        instrument: p.instrument,
        timeframe: p.timeframe,
        timestamp: p.timestamp,
        direction: p.direction,
        score: p.score,
        confidence: p.confidence,
        forecast_horizon: p.forecast_horizon,
        horizon_candles: p.horizon_candles,
        target_price: p.target_price,
        invalidation_price: p.invalidation_price,
        actual_direction: outcome?.actual_direction ?? null,
        actual_pct_move: outcome?.actual_pct_move ?? null,
        is_correct: outcome?.is_correct ?? null,
        measured_at: outcome?.evaluated_at ?? null,
      };
    });
  }, [predictions, outcomes]);

  const measuredInSession = useMemo(
    () => predictions.filter((p) => outcomes[p.prediction_id]).length,
    [predictions, outcomes],
  );

  const handleExportJson = () => {
    exportAsJson(`research-predictions-${instrument}-${timestampSlug()}.json`, exportRows);
  };

  const handleExportCsv = () => {
    exportRowsAsCsv(`research-predictions-${instrument}-${timestampSlug()}.csv`, exportRows);
  };

  const columns: Column<ResearchPredictionRow>[] = [
    {
      key: 'prediction_id',
      header: 'Prediction',
      sortable: true,
      render: (p) => (
        <span className="mono" title={p.prediction_id}>
          {shortId(p.prediction_id)}
        </span>
      ),
    },
    {
      key: 'indicator_id',
      header: 'Indicator',
      sortable: true,
      sortValue: (p) => p.indicator_id ?? null,
      render: (p) => (
        <div>
          <div>{p.indicator_id ?? '—'}</div>
          <div className="faint text-[10px]">
            {p.timeframe ?? '—'} · {p.forecast_horizon ?? `${p.horizon_candles ?? '—'} candles`}
          </div>
        </div>
      ),
    },
    {
      key: 'direction',
      header: 'Bias',
      render: (p) => <DirectionBadge direction={p.direction} />,
    },
    {
      key: 'score',
      header: 'Score',
      align: 'right',
      sortable: true,
      render: (p) => (p.score === null ? '—' : fmtSigned(p.score, 1)),
    },
    {
      key: 'confidence',
      header: 'Confidence',
      align: 'right',
      sortable: true,
      render: (p) => (p.confidence === null ? '—' : fmtPct01(p.confidence)),
    },
    {
      key: 'target_price',
      header: 'Target',
      align: 'right',
      sortable: true,
      render: (p) => (p.target_price === null ? '—' : fmtINR(p.target_price)),
    },
    {
      key: 'timestamp',
      header: 'Recorded',
      sortable: true,
      className: 'num',
      render: (p) => fmtClock(p.timestamp),
    },
    {
      key: 'outcome',
      header: 'Outcome',
      render: (p) => {
        const outcome = outcomes[p.prediction_id];
        return outcome ? (
          <span className={`badge ${outcome.is_correct ? 'b-bull' : 'b-bear'}`}>
            {outcome.is_correct ? 'CORRECT' : 'WRONG'}
            {outcome.actual_pct_move === null ? '' : ` · ${fmtNum(outcome.actual_pct_move, 2)}%`}
          </span>
        ) : (
          <span className="badge b-neut">UNMEASURED</span>
        );
      },
    },
    {
      key: 'action',
      header: 'Action',
      align: 'right',
      render: (p) =>
        outcomes[p.prediction_id] ? null : (
          <Button
            type="button"
            variant="outline"
            size="xs"
            onClick={() => void handleMeasure(p.prediction_id)}
            disabled={measuringId !== null}
          >
            {measuringId === p.prediction_id ? 'Measuring…' : 'Measure'}
          </Button>
        ),
    },
  ];

  return (
    <Card
      title="PREDICTION OUTCOME TRACKER"
      meta={`${instrument} · ${predictions.length} latest`}
      action={
        <div className="flex items-center gap-1.5">
          <ExportButtons
            onJson={predictions.length > 0 ? handleExportJson : undefined}
            onCsv={predictions.length > 0 ? handleExportCsv : undefined}
          />
          <Button type="button" variant="outline" size="xs" onClick={() => void load()} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </Button>
        </div>
      }
    >
      <div className="space-y-2 text-xs">
        {error ? <ErrorNote message={error} onRetry={() => void load()} /> : null}
        {measureError ? <ErrorNote message={measureError} /> : null}

        {!error && predictions.length === 0 && !loading ? (
          <EmptyNote>
            No predictions recorded for {instrument}. Forecast and indicator recordings will appear
            here as they are persisted.
          </EmptyNote>
        ) : null}

        {predictions.length > 0 ? (
          <DataTable
            data={predictions}
            columns={columns}
            keyExtractor={(p) => p.prediction_id}
            pageSize={25}
            emptyMessage={`No predictions recorded for ${instrument}.`}
          />
        ) : null}

        <div className="flex items-center justify-between gap-2 pt-1">
          <span className="faint">
            {measuredInSession > 0 ? `${measuredInSession} measured in this session` : 'Outcomes measured on demand'}
          </span>
          <FreshnessClock
            lastAt={lastLoadedAt}
            fetching={loading}
            sourceLabel={`REST · limit ${PREDICTION_LIMIT}`}
          />
        </div>
      </div>
    </Card>
  );
};
