'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { chartTokens } from '@/lib/chartTheme';
import { errorMessage } from '@/lib/errors';
import { PAP_UNAVAILABLE_LABEL } from '@/lib/pap';
import { horizonToMinutes } from '@/lib/pap';
import { markerDetail, toChartMarkers, type PapChartMarker } from '@/lib/papChart';
import type { Time } from 'lightweight-charts';

export function PapChartPanel({ instrument, horizon }: { instrument: string; horizon: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [markers, setMarkers] = useState<PapChartMarker[]>([]);
  const [status, setStatus] = useState<string>('loading');
  const [reason, setReason] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<PapChartMarker | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSelected(null);
    try {
      const data = await api.getResearchChart({
        instrument,
        horizon_minutes: horizonToMinutes(horizon),
        limit: 200,
      });
      setMarkers(data.markers);
      setStatus(data.status);
      setReason(data.reason);
      if (data.candles.length === 0) {
        setError(data.reason ?? 'No candles for this slice.');
        return;
      }
      const el = containerRef.current;
      if (!el) return;
      const { createChart, CandlestickSeries, createSeriesMarkers } = await import('lightweight-charts');
      type UTCTimestamp = import('lightweight-charts').UTCTimestamp;
      const tokens = chartTokens();
      el.innerHTML = '';
      const chart = createChart(el, {
        height: 320,
        layout: { background: { color: tokens.surface }, textColor: tokens.text },
        grid: { vertLines: { color: tokens.grid }, horzLines: { color: tokens.grid } },
        crosshair: { vertLine: { color: tokens.crosshair }, horzLine: { color: tokens.crosshair } },
      });
      const series = chart.addSeries(CandlestickSeries, {
        upColor: tokens.up,
        downColor: tokens.down,
        wickUpColor: tokens.up,
        wickDownColor: tokens.down,
        borderVisible: false,
      });
      series.setData(
        data.candles.map((c) => ({
          time: c.time as UTCTimestamp,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        })),
      );
      createSeriesMarkers(
        series,
        toChartMarkers(data.markers, tokens).map((m) => ({ ...m, time: m.time as Time })),
      );
      chart.timeScale().fitContent();
      const byTime = new Map(data.markers.map((m) => [m.time, m]));
      chart.subscribeCrosshairMove((param) => {
        const t = (param?.time ?? null) as number | null;
        if (typeof t === 'number' && byTime.has(t)) setSelected(byTime.get(t) ?? null);
      });
    } catch (err) {
      setError(errorMessage(err, 'Chart unavailable'));
    } finally {
      setLoading(false);
    }
  }, [instrument, horizon]);

  useEffect(() => {
    void load();
  }, [load]);

  const detail = markerDetail(selected);

  return (
    <section className="card" aria-label="PAP prediction chart">
      <div className="card-hd">
        <h3 className="card-title">Price chart + PAP predictions</h3>
        <span className="card-meta">
          {instrument} 1m · {horizon}
        </span>
      </div>
      <div className="card-bd flex flex-col gap-2">
        {loading ? <p className="sg-empty">Loading 1-minute candles…</p> : null}
        {error ? (
          <p className="sg-err" data-testid="pap-chart-unavailable">
            {PAP_UNAVAILABLE_LABEL} — {error}
          </p>
        ) : null}
        {!loading && !error && status === 'INSUFFICIENT_SAMPLE' ? (
          <p className="sg-empty" data-testid="pap-chart-empty">
            {reason ?? 'No predictions join to this window yet.'}
          </p>
        ) : null}
        <div ref={containerRef} data-testid="pap-chart" className="w-full overflow-x-auto" />
        {detail ? (
          <div className="rounded-lg border border-border-subtle p-2.5" data-testid="pap-marker-detail">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">{detail.title}</span>
              <span className={`badge ${detail.correct === true ? 'b-bull' : detail.correct === false ? 'b-bear' : 'b-neut'}`}>
                {detail.correct === null ? 'PENDING' : detail.correct ? 'CORRECT' : 'INCORRECT'}
              </span>
            </div>
            <div className="sg-kvlist mt-1.5">
              {detail.rows.map(([k, v]) => (
                <div className="sg-kv" key={k}>
                  <span className="l">{k}</span>
                  <span className="v">{v}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="sg-note">Click a prediction marker to inspect timestamp, horizon, probabilities and outcome.</p>
        )}
        <p className="sg-note">Markers: {markers.length} ledger prediction(s) joined to this window.</p>
      </div>
    </section>
  );
}
