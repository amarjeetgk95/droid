'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { Card, DirectionBadge, EmptyNote, fmtClock, fmtNum, fmtSigned } from '@/components/ui/desk';

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
  if (cv !== null && typeof cv === 'object') {
    try {
      if ((cv as Record<string, unknown>).settleable === false) return false;
    } catch {
      // ignore — treat as settleable
    }
  }
  return true;
}

export function ForecastOutcomes({ instrument, timeframe = '1h' }: { instrument: string; timeframe?: string }) {
  const [predictions, setPredictions] = useState<Array<Record<string, unknown>>>([]);
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [measuringId, setMeasuringId] = useState<string | null>(null);
  // P3-4: settleable-only toggle, default on (unsettled/late-session excluded).
  const [settleableOnly, setSettleableOnly] = useState(true);

  const load = useCallback(
    async (isInitial: boolean) => {
      if (typeof document !== 'undefined' && document.hidden) return;
      if (isInitial) setLoading(true);
      else setRefreshing(true);
      try {
        const preds = (await api.listResearchPredictions({ instrument, limit: 50 })) as Array<
          Record<string, unknown>
        >;
        const list = Array.isArray(preds)
          ? preds.filter((p) => !timeframe || String(p.timeframe ?? '') === timeframe).slice(0, 10)
          : [];
        setPredictions(list);
        const outcomeMap: Record<string, Outcome> = {};
        await Promise.allSettled(
          list.map(async (p) => {
            const pid = p.prediction_id as string | undefined;
            if (!pid) return;
            try {
              const out = (await api.getResearchPredictionOutcome(pid)) as Outcome & {
                outcome_id?: string;
              };
              if (out && (out as { outcome_id?: string }).outcome_id) {
                outcomeMap[pid] = out;
              }
            } catch {
              // Outcome not measured yet — leave pending.
            }
          }),
        );
        if (Object.keys(outcomeMap).length > 0) {
          setOutcomes((prev) => ({ ...prev, ...outcomeMap }));
        }
      } catch {
        setPredictions([]);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [instrument, timeframe],
  );

  useEffect(() => {
    void load(true);
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void load(false);
    }, 60000);
    return () => clearInterval(id);
  }, [load]);

  const stats = useMemo(() => {
    const visible = settleableOnly ? predictions.filter(isSettleablePred) : predictions;
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
  }, [predictions, outcomes, settleableOnly]);

  const handleMeasure = useCallback(async (predictionId: string) => {
    setMeasuringId(predictionId);
    try {
      const out = (await api.measureResearchPrediction(predictionId)) as Outcome;
      if (out) {
        setOutcomes((prev) => ({ ...prev, [predictionId]: out }));
      }
    } catch {
      // Measurement pending — leave as pending, never fake.
    } finally {
      setMeasuringId(null);
    }
  }, []);

  const summary =
    stats.measuredCount > 0
      ? `${stats.correctCount}/${stats.measuredCount} correct · avg MFE ${
          stats.avgMfe !== null ? fmtNum(stats.avgMfe, 1) : '—'
        } · avg MAE ${stats.avgMae !== null ? fmtNum(stats.avgMae, 1) : '—'}`
      : 'No measured outcomes yet';

  return (
    <Card
      title="Track record"
      meta={`${instrument} · ${timeframe}`}
      action={
        <button
          type="button"
          className="btn"
          onClick={() => void load(false)}
          disabled={refreshing || loading}
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
        Reference costs ref-v1, diagnostic.
      </p>
      {loading && predictions.length === 0 ? (
        <div style={{ display: 'grid', gap: 8 }}>
          <div className="skel" style={{ height: 14, width: '75%' }}>.</div>
          <div className="skel" style={{ height: 14, width: '60%' }}>.</div>
          <div className="skel" style={{ height: 14, width: '68%' }}>.</div>
        </div>
      ) : (settleableOnly ? predictions.filter(isSettleablePred) : predictions).length === 0 ? (
        <EmptyNote>No predictions recorded yet.</EmptyNote>
      ) : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Time</th>
                <th>Dir</th>
                <th className="r">Score</th>
                <th>Result</th>
                <th className="r">Mfe</th>
                <th className="r">Mae</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {(settleableOnly ? predictions.filter(isSettleablePred) : predictions).map((p) => {
                const pid = String(p.prediction_id ?? '');
                const outcome = pid ? outcomes[pid] : null;
                const busy = measuringId === pid;
                const result =
                  outcome?.is_correct === true
                    ? { label: 'Correct', cls: 'v-bull' }
                    : outcome?.is_correct === false
                      ? { label: 'Wrong', cls: 'v-bear' }
                      : { label: 'Pending', cls: 'faint' };
                return (
                  <tr key={pid || String(p.timestamp ?? Math.random())}>
                    <td className="num">{fmtClock(p.timestamp)}</td>
                    <td>
                      <DirectionBadge direction={p.direction} />
                    </td>
                    <td className="r num">{fmtSigned(p.score, 0)}</td>
                    <td>
                      <span className={result.cls} style={{ fontWeight: 600 }}>
                        {result.label}
                      </span>
                    </td>
                    <td className="r num">{outcome?.mfe != null ? fmtNum(outcome.mfe, 1) : '—'}</td>
                    <td className="r num">{outcome?.mae != null ? fmtNum(outcome.mae, 1) : '—'}</td>
                    <td>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => pid && void handleMeasure(pid)}
                        disabled={busy || !pid}
                      >
                        {busy ? 'Measuring…' : outcome ? 'Re-measure' : 'Measure'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
