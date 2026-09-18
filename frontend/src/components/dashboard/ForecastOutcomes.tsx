'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { useAppStreamRefresh, useCommandSection } from '@/context/AppStreamContext';
import { useMarketSession } from '@/hooks/useMarketSession';
import { Card, DirectionBadge, EmptyNote, fmtClock, fmtNum, fmtSigned } from '@/components/ui/desk';
import { DataTable, type Column } from '@/components/ui/data-table';
import { FreshnessClock } from '@/components/common/FreshnessClock';

type Outcome = {
  outcome_id?: string;
  is_correct?: boolean | null;
  mfe?: number | null;
  mae?: number | null;
} | null;

/** Settleable predicate: excluded only when explicitly false (top-level or component_values). */
function isSettleablePred(p: Record<string, unknown>): boolean {
  if (p.settleable === false) return false;
  const cv = p.component_values;
  if (cv !== null && typeof cv === 'object' && (cv as Record<string, unknown>).settleable === false) {
    return false;
  }
  return true;
}

/** Predictions carry `forecast_horizon` (legacy rows may only have `horizon`). */
function predictionHorizon(p: Record<string, unknown>): string {
  const raw = p.forecast_horizon ?? p.horizon;
  return typeof raw === 'string' ? raw : '';
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function asPredictionRows(v: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(v)) return [];
  return v.filter(
    (row): row is Record<string, unknown> =>
      Boolean(row) && typeof row === 'object' && !Array.isArray(row),
  );
}

/**
 * `forecast.value.by_instrument` keys are the canonical prediction-store
 * spellings the backend composes (`FORECAST_INSTRUMENTS`): "NIFTY 50" /
 * BANKNIFTY / SENSEX. The dashboard token "NIFTY" maps to "NIFTY 50"; an
 * unknown instrument resolves to itself and reads no entry — never another
 * instrument's rows.
 */
const FORECAST_SYMBOL_KEYS: Record<string, string> = {
  NIFTY: 'NIFTY 50',
  'NIFTY 50': 'NIFTY 50',
  BANKNIFTY: 'BANKNIFTY',
  SENSEX: 'SENSEX',
};

function toForecastSymbol(instrument: string): string {
  return FORECAST_SYMBOL_KEYS[instrument.toUpperCase()] ?? instrument;
}

/**
 * Forecast track record — pure consumer of `forecast.value.by_instrument`.
 *
 * Prediction rows for the selected instrument come from the unified command
 * stream; the per-instrument REST fallback poll is gone. Outcome enrichment
 * stays a bounded one-shot batch per fresh row list and Measure stays a
 * user-triggered mutation; Refresh asks the stream for a re-fetch once.
 */
export function ForecastOutcomes({
  instrument,
  horizon = '1h',
}: {
  instrument: string;
  horizon?: string;
}) {
  const { isOpen } = useMarketSession();
  const refresh = useAppStreamRefresh();
  const section = useCommandSection('forecast');

  const sectionValue = asRecord(section?.value);
  const byInstrument = asRecord(sectionValue?.by_instrument);
  const symbol = toForecastSymbol(instrument);
  const entry = byInstrument ? byInstrument[symbol] : undefined;
  const rawPredictions = Array.isArray(entry) ? (entry as unknown[]) : null;

  const predictions = useMemo(() => {
    if (rawPredictions === null) return [];
    return asPredictionRows(rawPredictions)
      .filter((p) => predictionHorizon(p) === horizon)
      .slice(0, 10);
  }, [rawPredictions, horizon]);

  // Keep the last known rows for the same instrument visible while its map
  // entry is an explicit null (the backend caches a failed instrument as null
  // for the TTL); rows are never carried across an instrument change.
  const [lastRows, setLastRows] = useState<{
    symbol: string;
    rows: Array<Record<string, unknown>>;
  }>({ symbol, rows: [] });
  useEffect(() => {
    if (rawPredictions !== null) setLastRows({ symbol, rows: predictions });
  }, [rawPredictions, predictions, symbol]);

  const rows =
    rawPredictions !== null
      ? predictions
      : lastRows.symbol === symbol
        ? lastRows.rows
        : [];

  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({});
  const [measuringId, setMeasuringId] = useState<string | null>(null);
  const [streamRefreshing, setStreamRefreshing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  // P3-4: settleable-only toggle, default on (unsettled/late-session excluded).
  const [settleableOnly, setSettleableOnly] = useState(true);

  // Outcome enrichment: one bounded batch per fresh prediction list, never an
  // interval. Measure stays a user-triggered mutation below.
  useEffect(() => {
    const ids = Array.from(
      new Set(predictions.map((p) => String(p.prediction_id ?? '')).filter((id) => id.length > 0)),
    );
    if (ids.length === 0) return;
    let cancelled = false;
    void (async () => {
      const results = await Promise.allSettled(
        ids.map(async (pid) => {
          const out = (await api.getResearchPredictionOutcome(pid).catch(() => null)) as Outcome;
          return [pid, out] as const;
        }),
      );
      if (cancelled) return;
      const next: Record<string, Outcome> = {};
      for (const result of results) {
        if (result.status === 'fulfilled' && result.value[1]?.outcome_id) {
          next[result.value[0]] = result.value[1];
        }
      }
      if (Object.keys(next).length > 0) {
        setOutcomes((prev) => ({ ...prev, ...next }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [predictions]);

  const error =
    section !== null && rawPredictions === null
      ? 'research predictions section unavailable'
      : null;
  const loading = section === null;
  const refreshing = streamRefreshing;

  const lastAt = useMemo(() => {
    if (!section) return null;
    const parsed = new Date(section.updated_at);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }, [section]);

  const stats = useMemo(() => {
    const visible = settleableOnly ? rows.filter(isSettleablePred) : rows;
    const visibleIds = new Set(visible.map((p) => String(p.prediction_id ?? '')));
    const total = visible.length;
    const measuredEntries = Object.entries(outcomes)
      .filter(([pid]) => visibleIds.has(pid))
      .map(([, o]) => o);
    const measuredCount = measuredEntries.length;
    const correctCount = measuredEntries.filter((o) => o?.is_correct).length;
    const winRate = measuredCount > 0 ? Math.round((correctCount / measuredCount) * 100) : null;
    const mfeVals = measuredEntries
      .map((o) => o?.mfe)
      .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
    const maeVals = measuredEntries
      .map((o) => o?.mae)
      .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
    const avgMfe = mfeVals.length > 0 ? mfeVals.reduce((a, b) => a + b, 0) / mfeVals.length : null;
    const avgMae = maeVals.length > 0 ? maeVals.reduce((a, b) => a + b, 0) / maeVals.length : null;
    return { total, measuredCount, correctCount, winRate, avgMfe, avgMae };
  }, [rows, outcomes, settleableOnly]);

  const handleMeasure = useCallback(async (predictionId: string) => {
    setMeasuringId(predictionId);
    setActionError(null);
    try {
      const out = (await api.measureResearchPrediction(predictionId)) as Outcome;
      if (out) {
        setOutcomes((prev) => ({ ...prev, [predictionId]: out }));
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Outcome measurement failed');
    } finally {
      setMeasuringId(null);
    }
  }, []);

  const handleRefresh = useCallback(async () => {
    setStreamRefreshing(true);
    try {
      await refresh();
    } finally {
      setStreamRefreshing(false);
    }
  }, [refresh]);

  const summary =
    stats.measuredCount > 0
      ? `${stats.correctCount}/${stats.measuredCount} correct · avg MFE ${
          stats.avgMfe !== null ? fmtNum(stats.avgMfe, 1) : '—'
        } · avg MAE ${stats.avgMae !== null ? fmtNum(stats.avgMae, 1) : '—'}`
      : 'No measured outcomes yet';

  const visiblePredictions = settleableOnly ? rows.filter(isSettleablePred) : rows;

  const columns = useMemo<Column<Record<string, unknown>>[]>(
    () => [
      {
        key: 'timestamp',
        header: 'Time',
        sortable: true,
        className: 'num',
        render: (p) => fmtClock(p.timestamp),
      },
      {
        key: 'direction',
        header: 'Dir',
        render: (p) => <DirectionBadge direction={p.direction} />,
      },
      {
        key: 'score',
        header: 'Score',
        align: 'right',
        sortable: true,
        render: (p) => fmtSigned(p.score, 0),
      },
      {
        key: 'result',
        header: 'Result',
        render: (p) => {
          const outcome = outcomes[String(p.prediction_id ?? '')] ?? null;
          const result =
            outcome?.is_correct === true
              ? { label: 'Correct', cls: 'v-bull' }
              : outcome?.is_correct === false
                ? { label: 'Wrong', cls: 'v-bear' }
                : { label: 'Pending', cls: 'faint' };
          return (
            <span className={result.cls} style={{ fontWeight: 600 }}>
              {result.label}
            </span>
          );
        },
      },
      {
        key: 'mfe',
        header: 'Mfe',
        align: 'right',
        sortable: true,
        sortValue: (p) => outcomes[String(p.prediction_id ?? '')]?.mfe ?? null,
        render: (p) => {
          const mfe = outcomes[String(p.prediction_id ?? '')]?.mfe;
          return mfe != null ? fmtNum(mfe, 1) : '—';
        },
      },
      {
        key: 'mae',
        header: 'Mae',
        align: 'right',
        sortable: true,
        sortValue: (p) => outcomes[String(p.prediction_id ?? '')]?.mae ?? null,
        render: (p) => {
          const mae = outcomes[String(p.prediction_id ?? '')]?.mae;
          return mae != null ? fmtNum(mae, 1) : '—';
        },
      },
      {
        key: 'action',
        header: 'Action',
        render: (p) => {
          const pid = String(p.prediction_id ?? '');
          const outcome = pid ? outcomes[pid] : null;
          const busy = measuringId === pid;
          return (
            <button
              type="button"
              className="btn"
              onClick={() => pid && void handleMeasure(pid)}
              disabled={busy || !pid}
            >
              {busy ? 'Measuring…' : outcome ? 'Re-measure' : 'Measure'}
            </button>
          );
        },
      },
    ],
    [outcomes, measuringId, handleMeasure],
  );

  return (
    <Card
      title="Track record"
      meta={`${instrument} · horizon ${horizon}`}
      action={
        <button
          type="button"
          className="btn"
          onClick={() => void handleRefresh()}
          disabled={refreshing}
        >
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      }
    >
      <div
        className="toolbar"
        style={{ margin: '0 0 10px', gap: 10, alignItems: 'center', justifyContent: 'space-between' }}
      >
        <p className="muted num" style={{ margin: 0, fontSize: 12.5 }}>
          {summary}
        </p>
        <label className="muted" style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 12 }}>
          <input
            type="checkbox"
            checked={settleableOnly}
            onChange={(e) => setSettleableOnly(e.target.checked)}
            aria-label="Settleable only"
          />
          Settleable only
        </label>
      </div>
      <p className="faint" style={{ margin: '0 0 10px', fontSize: 11.5 }}>
        Outcomes are measured after the {horizon} horizon elapses; unsettled rows stay pending.
      </p>
      {error ? (
        <div
          style={{
            marginBottom: 10,
            padding: '6px 10px',
            border: '1px solid var(--ds-border)',
            borderRadius: 8,
            fontSize: 12,
          }}
        >
          <span className="v-bear">Predictions unavailable — {error}</span>
          {rows.length > 0 ? <span className="muted"> Showing last known rows.</span> : null}
        </div>
      ) : null}
      {actionError ? (
        <div style={{ marginBottom: 10 }}>
          <span className="v-bear" style={{ fontSize: 12 }}>
            {actionError}
          </span>
        </div>
      ) : null}
      {loading && rows.length === 0 ? (
        <div style={{ display: 'grid', gap: 8 }}>
          <div className="skel" style={{ height: 14, width: '75%' }}>.</div>
          <div className="skel" style={{ height: 14, width: '60%' }}>.</div>
          <div className="skel" style={{ height: 14, width: '68%' }}>.</div>
        </div>
      ) : visiblePredictions.length === 0 ? (
        <EmptyNote>
          {error
            ? 'No prediction rows available.'
            : `No predictions recorded for ${instrument} at horizon ${horizon}.`}
        </EmptyNote>
      ) : (
        <DataTable
          data={visiblePredictions}
          columns={columns}
          keyExtractor={(p, idx) => String(p.prediction_id ?? `${p.timestamp ?? 'pred'}-${idx}`)}
          emptyMessage="No prediction rows available."
        />
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 10 }}>
        <FreshnessClock
          lastAt={lastAt}
          fetching={refreshing}
          marketClosed={!isOpen}
          dataQuality={error ? 'DEGRADED' : null}
          sourceLabel="SSE · command stream"
        />
      </div>
    </Card>
  );
}
