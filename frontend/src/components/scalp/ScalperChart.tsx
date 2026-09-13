'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  LineStyle,
  IChartApi,
  ISeriesApi,
  IPriceLine,
  CandlestickSeries,
  LineSeries,
} from 'lightweight-charts';
import { RefreshCw, BarChart2 } from 'lucide-react';
import { api } from '@/lib/api';

interface CandleData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap?: number | null;
}

interface ScalperChartProps {
  symbol: string;
  timeframe?: '1m' | '3m' | '5m';
  onTimeframeChange?: (tf: '1m' | '3m' | '5m') => void;
  spotPrice?: number | null;
  /** Underlying-point bracket distances for SL/TP overlay (e.g. 8 / 16). */
  slDistance?: number | null;
  tpDistance?: number | null;
}

interface VwapState {
  value: number | null;
  distance: number | null;
  distancePct: number | null;
  hiddenForScale: boolean;
  unreliable: boolean;
}

function isFinitePositive(n: unknown): n is number {
  return typeof n === 'number' && Number.isFinite(n) && n > 0;
}

/** Distance beyond which VWAP is hidden to preserve candle scale. */
function vwapHideThreshold(lastClose: number, symbol: string): number {
  const pctBased = Math.abs(lastClose) * 0.0025; // 0.25%
  const sym = (symbol || '').toUpperCase();
  const floor = sym.includes('BANKNIFTY') || sym.includes('SENSEX') ? 100 : 30;
  return Math.max(pctBased, floor);
}

function aggregateCandles(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  sorted: any[],
  factor: number,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): any[] {
  if (factor <= 1) return sorted;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const out: any[] = [];
  for (let i = 0; i < sorted.length; i += factor) {
    const chunk = sorted.slice(i, i + factor);
    if (chunk.length === 0) continue;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const volumes = chunk.map((c: any) => (Number.isFinite(c.volume) ? c.volume : 0));
    out.push({
      time: chunk[0].time,
      open: chunk[0].open,
      high: Math.max(...chunk.map((c: { high: number }) => c.high)),
      low: Math.min(...chunk.map((c: { low: number }) => c.low)),
      close: chunk[chunk.length - 1].close,
      volume: volumes.reduce((a: number, b: number) => a + b, 0),
    });
  }
  return out;
}

export function ScalperChart({
  symbol,
  timeframe = '1m',
  onTimeframeChange,
  spotPrice,
  slDistance,
  tpDistance,
}: ScalperChartProps) {
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const vwapSeriesRef = useRef<ISeriesApi<'Line'> | any>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const requestIdRef = useRef(0);
  const hasDataRef = useRef(false);
  const hasFittedRef = useRef(false);
  const mountedRef = useRef(true);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [candleCount, setCandleCount] = useState(0);
  const [dataAgeSec, setDataAgeSec] = useState<number | null>(null);
  const [vwap, setVwap] = useState<VwapState>({
    value: null,
    distance: null,
    distancePct: null,
    hiddenForScale: false,
    unreliable: false,
  });

  const clearPriceLines = useCallback(() => {
    const series = candleSeriesRef.current;
    if (!series) {
      priceLinesRef.current = [];
      return;
    }
    for (const line of priceLinesRef.current) {
      try {
        series.removePriceLine(line);
      } catch {
        // line already removed with series reset — ignore
      }
    }
    priceLinesRef.current = [];
  }, []);

  const fetchCandles = useCallback(async () => {
    // Don't hammer backend when tab is hidden; the visibilitychange refetch covers it.
    if (typeof document !== 'undefined' && document.hidden) return;
    const reqId = ++requestIdRef.current;
    const isFirstLoad = !hasDataRef.current;
    if (isFirstLoad) setLoading(true);
    else setRefreshing(true);
    if (isFirstLoad) setError(null);

    try {
      if (!symbol || symbol.trim().length === 0) {
        throw new Error('Missing symbol for candle feed');
      }
      // 3m is aggregated client-side from 1m so the label is truthful.
      // 5m uses the native backend feed (180 x 5m bars); only 3m aggregates.
      const queryTf = timeframe === '3m' ? '1m' : timeframe;
      const res = await api.getCandles(symbol, queryTf, 180);
      if (reqId !== requestIdRef.current || !mountedRef.current) return;
      const rawCandles = (res.data || []) as unknown as CandleData[];

      if (!rawCandles || rawCandles.length === 0) {
        if (isFirstLoad) setError('No candle data available for this session');
        return;
      }

      // Validate + normalise OHLC. Drop corrupt prints rather than breaking scale.
      type Norm = { time: number; open: number; high: number; low: number; close: number; volume: number; backendVwap: number | null };
      const normalised: Norm[] = [];
      for (const c of rawCandles) {
        const t = Math.floor(new Date(c.timestamp).getTime() / 1000);
        if (!Number.isFinite(t) || t <= 0) continue;
        const o = Number(c.open);
        const h = Number(c.high);
        const l = Number(c.low);
        const cl = Number(c.close);
        if (![o, h, l, cl].every((v) => Number.isFinite(v) && v > 0)) continue;
        const high = Math.max(o, h, l, cl);
        const low = Math.min(o, h, l, cl);
        const volRaw = Number(c.volume);
        const backendVwap = c.vwap != null && Number.isFinite(Number(c.vwap)) && Number(c.vwap) > 0 ? Number(c.vwap) : null;
        normalised.push({
          time: t,
          open: o,
          high,
          low,
          close: cl,
          volume: Number.isFinite(volRaw) && volRaw >= 0 ? volRaw : 0,
          backendVwap,
        });
      }
      if (normalised.length === 0) {
        if (isFirstLoad) setError('Candle feed returned no valid OHLC rows');
        return;
      }
      normalised.sort((a, b) => a.time - b.time);
      const deduped: Norm[] = [];
      for (const item of normalised) {
        if (deduped.length === 0 || deduped[deduped.length - 1].time !== item.time) deduped.push(item);
      }

      const factor = timeframe === '3m' && queryTf === '1m' ? 3 : 1;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let chartRows: any[] = deduped.map((c) => ({
        time: c.time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
      }));
      if (factor > 1) chartRows = aggregateCandles(chartRows, factor);

      if (candleSeriesRef.current) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        candleSeriesRef.current.setData(chartRows as any);
      }

      // VWAP: prefer backend session VWAP when present, else cumulative typical*volume.
      const backendCount = deduped.filter((c) => c.backendVwap != null).length;
      const useBackendVwap = backendCount >= Math.ceil(deduped.length * 0.5);
      const volumes = deduped.map((c) => c.volume);
      const uniqueVolumes = new Set(volumes.map((v) => Math.round(v)));
      const unreliableVolume = uniqueVolumes.size <= 2 && !useBackendVwap;

      let cumVol = 0;
      let cumPv = 0;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const vwapData: any[] = deduped.map((c, idx) => {
        // Map each 1m bar to its aggregated bucket so VWAP aligns with chartRows.
        const bucketIdx = factor > 1 ? Math.min(Math.floor(idx / factor), chartRows.length - 1) : Math.min(idx, chartRows.length - 1);
        if (useBackendVwap && c.backendVwap != null) {
          return { time: chartRows[bucketIdx]?.time ?? c.time, value: Number(c.backendVwap.toFixed(2)) };
        }
        const typical = (c.open + c.high + c.low + c.close) / 4;
        cumVol += c.volume;
        cumPv += typical * c.volume;
        const v = cumVol > 0 ? cumPv / cumVol : c.close;
        return { time: chartRows[bucketIdx]?.time ?? c.time, value: Number(v.toFixed(2)) };
      });
      // Dedupe VWAP times to match aggregated rows (last wins).
      const vwapByTime = new Map<number, number>();
      for (const p of vwapData) vwapByTime.set(Number(p.time), p.value);
      const vwapRows = [...vwapByTime.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([time, value]) => ({ time, value }));

      const lastClose = chartRows[chartRows.length - 1]?.close;
      const lastVwap = vwapRows.length > 0 ? vwapRows[vwapRows.length - 1].value : null;
      let hiddenForScale = false;
      let distance: number | null = null;
      let distancePct: number | null = null;
      if (isFinitePositive(lastClose) && lastVwap != null && Number.isFinite(lastVwap)) {
        distance = Number((lastVwap - lastClose).toFixed(2));
        distancePct = Number(((distance / lastClose) * 100).toFixed(3));
        hiddenForScale = Math.abs(distance) > vwapHideThreshold(lastClose, symbol);
      }

      if (vwapSeriesRef.current) {
        try {
          // Never let a far-away VWAP squash candle autoscale.
          vwapSeriesRef.current.applyOptions({
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            autoscaleInfoProvider: () => null as any,
            visible: !hiddenForScale,
          });
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          vwapSeriesRef.current.setData(vwapRows as any);
        } catch {
          // Non-fatal: candles are already painted.
        }
      }

      setVwap({
        value: lastVwap ?? null,
        distance,
        distancePct,
        hiddenForScale,
        unreliable: unreliableVolume && !useBackendVwap,
      });

      hasDataRef.current = true;
      setCandleCount(chartRows.length);
      const lastBarTime = chartRows[chartRows.length - 1]?.time;
      if (Number.isFinite(lastBarTime)) {
        setDataAgeSec(Math.max(0, Math.floor(Date.now() / 1000) - Number(lastBarTime)));
      }
      setLastUpdated(new Date().toLocaleTimeString('en-IN', { hour12: false }));
      setError(null);

      // Fit viewport only on first paint / symbol+tf change so polling never yanks zoom.
      if (!hasFittedRef.current && chartRef.current) {
        try {
          chartRef.current.timeScale().fitContent();
        } catch {
          // ignore
        }
        hasFittedRef.current = true;
      }
    } catch (err: unknown) {
      if (reqId !== requestIdRef.current || !mountedRef.current) return;
      if (isFirstLoad) setError((err as Error)?.message || 'Failed to load candle feed');
    } finally {
      if (reqId === requestIdRef.current && mountedRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [symbol, timeframe]);

  // Initialize Chart once
  useEffect(() => {
    mountedRef.current = true;
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;
    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#888888',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
      },
      crosshair: {
        vertLine: { color: 'rgba(255, 255, 255, 0.2)', width: 1, style: 3 },
        horzLine: { color: 'rgba(255, 255, 255, 0.2)', width: 1, style: 3 },
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        scaleMargins: { top: 0.2, bottom: 0.15 },
      },
      handleScroll: true,
      handleScale: true,
    });

    // In lightweight-charts v5: addSeries(CandlestickSeries, options)
    const activeCandleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceLineVisible: true,
      priceLineSource: 0,
    });

    // VWAP overlay — excluded from autoscale so a distant VWAP can't squash candles.
    const activeVwapSeries = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 2,
      title: 'VWAP',
      priceLineVisible: false,
      lastValueVisible: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      autoscaleInfoProvider: () => null as any,
    });

    chartRef.current = chart;
    candleSeriesRef.current = activeCandleSeries;
    vwapSeriesRef.current = activeVwapSeries;

    const applySize = () => {
      const rect = container.getBoundingClientRect();
      const width = Math.max(200, Math.floor(rect.width) || container.clientWidth || 600);
      const height = Math.max(220, Math.floor(rect.height) || container.clientHeight || 320);
      try {
        chart.applyOptions({ width, height });
      } catch {
        // ignore transient resize races
      }
    };
    applySize();
    let raf = 0;
    const resizeObserver = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(applySize);
    });
    resizeObserver.observe(container);

    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      try {
        chart.remove();
      } catch {
        // ignore double-unmount
      }
      chartRef.current = null;
      candleSeriesRef.current = null;
      vwapSeriesRef.current = null;
      priceLinesRef.current = [];
    };
  }, []);

  // Reset fit-on-change when the feed identity changes
  useEffect(() => {
    hasFittedRef.current = false;
    hasDataRef.current = false;
    priceLinesRef.current = [];
  }, [symbol, timeframe]);

  // Fetch data on symbol/timeframe changes + 10s poll + refetch on tab visible
  useEffect(() => {
    fetchCandles();
    const interval = setInterval(fetchCandles, 10000);
    const onVisible = () => {
      if (!document.hidden) fetchCandles();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [fetchCandles]);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // SL/TP + entry overlay. Symmetric zones so both CE and PE scalps can read risk.
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series || !hasDataRef.current) return;
    clearPriceLines();
    const spot = Number(spotPrice);
    const sl = Number(slDistance);
    const tp = Number(tpDistance);
    if (!Number.isFinite(spot) || spot <= 0) return;
    try {
      if (Number.isFinite(sl) && sl > 0) {
        priceLinesRef.current.push(
          series.createPriceLine({
            price: spot - sl,
            color: '#f43f5e',
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: `SL -${sl}`,
          }),
        );
        priceLinesRef.current.push(
          series.createPriceLine({
            price: spot + sl,
            color: 'rgba(244,63,94,0.45)',
            lineWidth: 1,
            lineStyle: LineStyle.Dotted,
            axisLabelVisible: false,
            title: '',
          }),
        );
      }
      if (Number.isFinite(tp) && tp > 0) {
        priceLinesRef.current.push(
          series.createPriceLine({
            price: spot + tp,
            color: '#10b981',
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: `TP +${tp}`,
          }),
        );
        priceLinesRef.current.push(
          series.createPriceLine({
            price: spot - tp,
            color: 'rgba(16,185,129,0.45)',
            lineWidth: 1,
            lineStyle: LineStyle.Dotted,
            axisLabelVisible: false,
            title: '',
          }),
        );
      }
      priceLinesRef.current.push(
        series.createPriceLine({
          price: spot,
          color: '#60a5fa',
          lineWidth: 1,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: 'Spot',
        }),
      );
    } catch {
      // Overlay is advisory; candles remain authoritative.
    }
    return () => {
      // Removal happens on next effect run via clearPriceLines; keep lines mounted.
    };
  }, [spotPrice, slDistance, tpDistance, candleCount, clearPriceLines]);

  const stale = dataAgeSec != null && dataAgeSec > 120;
  const busy = loading || refreshing;
  const tfLabel = timeframe.toUpperCase();

  return (
    <div className="flex flex-col h-full bg-[#0a0c10] border border-border/80 rounded-lg overflow-hidden select-none">
      {/* Chart Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-card/60 border-b border-border/60 text-xs">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          <span className="font-bold tracking-wide flex items-center gap-1.5 text-foreground whitespace-nowrap">
            <BarChart2 className="w-3.5 h-3.5 text-amber-500" />
            {symbol} {tfLabel} Execution Chart
          </span>
          {isFinitePositive(spotPrice) ? (
            <span className="font-mono text-emerald-400 font-semibold bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
              ₹{Number(spotPrice).toFixed(2)}
            </span>
          ) : (
            <span className="font-mono text-muted-foreground bg-secondary/60 px-1.5 py-0.5 rounded border border-border/50">
              no spot
            </span>
          )}
          {vwap.hiddenForScale && vwap.distance != null ? (
            <span
              className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30"
              title={vwap.unreliable ? 'VWAP estimated from thin volume — treat with caution' : `Session VWAP ₹${vwap.value?.toFixed(2)} is off-scale`}
            >
              VWAP {vwap.distance > 0 ? '+' : ''}{vwap.distance.toFixed(1)} ({vwap.distancePct?.toFixed(2)}%) off-scale
            </span>
          ) : vwap.value != null ? (
            <span className="text-[10px] text-amber-500/90 font-mono flex items-center gap-1 ml-1" title={`Session VWAP ₹${vwap.value.toFixed(2)}${vwap.unreliable ? ' (estimated, thin volume)' : ''}`}>
              <span className="w-2 h-0.5 bg-amber-500 inline-block" /> VWAP
              {vwap.distance != null ? (
                <span className={vwap.distance >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                  {vwap.distance >= 0 ? '+' : ''}{vwap.distance.toFixed(1)}
                </span>
              ) : null}
            </span>
          ) : (
            <span className="text-[10px] text-amber-500/90 font-mono flex items-center gap-1 ml-1">
              <span className="w-2 h-0.5 bg-amber-500 inline-block" /> VWAP
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`hidden md:inline font-mono text-[10px] px-1.5 py-0.5 rounded border ${
              stale
                ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                : 'bg-secondary/60 text-muted-foreground border-border/40'
            }`}
            title={lastUpdated ? `Candles refreshed at ${lastUpdated}` : 'Candles not loaded yet'}
          >
            {candleCount > 0 ? `${candleCount} bars` : '—'}
            {dataAgeSec != null ? ` · ${dataAgeSec}s old` : ''}
          </span>
          {/* Timeframe selector */}
          <div className="flex items-center bg-secondary/60 rounded p-0.5 border border-border/40" role="tablist" aria-label="Chart timeframe">
            {(['1m', '3m', '5m'] as const).map((tf) => (
              <button
                key={tf}
                type="button"
                role="tab"
                aria-selected={timeframe === tf}
                onClick={() => onTimeframeChange?.(tf)}
                className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                  timeframe === tf
                    ? 'bg-amber-500 text-black font-bold shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {tf.toUpperCase()}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => fetchCandles()}
            disabled={busy}
            className="p-1 hover:bg-secondary rounded text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            title={`Last updated: ${lastUpdated || 'Never'}`}
          >
            <RefreshCw className={`w-3 h-3 ${busy ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Chart Canvas Area */}
      <div className="relative flex-1 min-h-[280px]">
        {(loading || refreshing) && !error && (
          <div className="absolute top-2 left-2 z-10 font-mono text-[10px] px-1.5 py-0.5 rounded bg-background/80 border border-border/50 text-muted-foreground pointer-events-none">
            {loading ? 'loading candles…' : 'updating…'}
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background/85 z-10 text-xs p-4 text-center">
            <span className="text-rose-400">{error}</span>
            <button
              type="button"
              onClick={() => fetchCandles()}
              className="px-2 py-1 rounded bg-secondary hover:bg-secondary/80 text-foreground font-mono text-[11px] border border-border/60"
            >
              Retry feed
            </button>
          </div>
        )}
        <div ref={chartContainerRef} className="w-full h-full min-h-[280px]" />
      </div>
    </div>
  );
}
