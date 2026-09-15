'use client';

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
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
import { RefreshCw, BarChart2, CornerDownRight } from 'lucide-react';
import { api } from '@/lib/api';
import { useScalpContext } from './ScalpContext';
import { useSmartInterval } from '@/hooks/useSmartInterval';

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
  symbol?: string;
  timeframe?: '1m' | '3m' | '5m';
  onTimeframeChange?: (tf: '1m' | '3m' | '5m') => void;
  spotPrice?: number | null;
  slDistance?: number | null;
  tpDistance?: number | null;
  activeEntryPrice?: number | null;
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

function vwapHideThreshold(lastClose: number, symbol: string): number {
  const pctBased = Math.abs(lastClose) * 0.0025; // 0.25%
  const sym = (symbol || '').toUpperCase();
  const floor = sym.includes('BANKNIFTY') || sym.includes('SENSEX') ? 100 : 30;
  return Math.max(pctBased, floor);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function aggregateCandles(sorted: any[], factor: number): any[] {
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
  symbol: propSymbol,
  timeframe = '1m',
  onTimeframeChange,
  spotPrice: propSpotPrice,
  slDistance = 8,
  tpDistance = 16,
  activeEntryPrice,
}: ScalperChartProps) {
  const scalpCtx = useScalpContext();
  const symbol = propSymbol || (scalpCtx.underlying === 'NIFTY' ? 'NIFTY 50' : scalpCtx.underlying);
  const spotPrice = propSpotPrice !== undefined ? propSpotPrice : scalpCtx.spotPrice;

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
  const [lastBarTimeSec, setLastBarTimeSec] = useState<number | null>(null);
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
        // line already removed with series reset
      }
    }
    priceLinesRef.current = [];
  }, []);

  const fetchCandles = useCallback(async () => {
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
      const queryTf = timeframe === '3m' ? '1m' : timeframe;
      const res = await api.getCandles(symbol, queryTf, 180);
      if (reqId !== requestIdRef.current || !mountedRef.current) return;
      const rawCandles = (res.data || []) as unknown as CandleData[];

      if (!rawCandles || rawCandles.length === 0) {
        if (isFirstLoad) setError('No candle data available for this session');
        return;
      }

      type Norm = {
        time: number;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
        backendVwap: number | null;
      };
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
        const backendVwap =
          c.vwap != null && Number.isFinite(Number(c.vwap)) && Number(c.vwap) > 0
            ? Number(c.vwap)
            : null;
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

      // VWAP calculation
      const backendCount = deduped.filter((c) => c.backendVwap != null).length;
      const useBackendVwap = backendCount >= Math.ceil(deduped.length * 0.5);
      const volumes = deduped.map((c) => c.volume);
      const uniqueVolumes = new Set(volumes.map((v) => Math.round(v)));
      const unreliableVolume = uniqueVolumes.size <= 2 && !useBackendVwap;

      let cumVol = 0;
      let cumPv = 0;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const vwapData: any[] = deduped.map((c, idx) => {
        const bucketIdx =
          factor > 1 ? Math.min(Math.floor(idx / factor), chartRows.length - 1) : Math.min(idx, chartRows.length - 1);
        if (useBackendVwap && c.backendVwap != null) {
          return { time: chartRows[bucketIdx]?.time ?? c.time, value: Number(c.backendVwap.toFixed(2)) };
        }
        const typical = (c.open + c.high + c.low + c.close) / 4;
        cumVol += c.volume;
        cumPv += typical * c.volume;
        const v = cumVol > 0 ? cumPv / cumVol : c.close;
        return { time: chartRows[bucketIdx]?.time ?? c.time, value: Number(v.toFixed(2)) };
      });

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
          vwapSeriesRef.current.applyOptions({
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            autoscaleInfoProvider: () => null as any,
            visible: !hiddenForScale,
          });
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          vwapSeriesRef.current.setData(vwapRows as any);
        } catch {
          // non-fatal
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
        setLastBarTimeSec(Number(lastBarTime));
        setDataAgeSec(Math.max(0, Math.floor(Date.now() / 1000) - Number(lastBarTime)));
      }
      setLastUpdated(new Date().toLocaleTimeString('en-IN', { hour12: false }));
      setError(null);

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

  // Use smart interval for candle polling (10s)
  const { refresh: refreshCandles } = useSmartInterval(fetchCandles, 10000, {
    fireOnMount: true,
    fireOnVisible: true,
    pauseWhenHidden: true,
  });

  // Immediate refetch on symbol/timeframe switch — the interval holds the
  // callback in a ref and won't refire for the new symbol on its own.
  useEffect(() => {
    void refreshCandles();
  }, [symbol, timeframe, refreshCandles]);

  // Chart setup
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

    const activeCandleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceLineVisible: true,
      priceLineSource: 0,
    });

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
        // ignore
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
        // ignore
      }
      chartRef.current = null;
      candleSeriesRef.current = null;
      vwapSeriesRef.current = null;
      priceLinesRef.current = [];
    };
  }, []);

  useEffect(() => {
    hasFittedRef.current = false;
    hasDataRef.current = false;
    priceLinesRef.current = [];
  }, [symbol, timeframe]);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // SL/TP + entry overlay
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
          })
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
          })
        );
      }
      // Prominent entry price line if active
      if (Number.isFinite(activeEntryPrice) && (activeEntryPrice as number) > 0) {
        priceLinesRef.current.push(
          series.createPriceLine({
            price: Number(activeEntryPrice),
            color: '#f59e0b',
            lineWidth: 2,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: 'Entry Fill',
          })
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
        })
      );
    } catch {
      // overlay error ignored
    }
  }, [spotPrice, slDistance, tpDistance, activeEntryPrice, candleCount, clearPriceLines]);

  const snapToNow = () => {
    if (chartRef.current) {
      try {
        chartRef.current.timeScale().scrollToRealTime();
      } catch {
        chartRef.current.timeScale().fitContent();
      }
    }
  };

  const busy = loading || refreshing;
  const tfLabel = timeframe.toUpperCase();

  const sessionStatus = useMemo(() => {
    if (dataAgeSec == null || candleCount === 0) {
      return { label: 'CONNECTING', tone: 'neutral' as const };
    }
    if (dataAgeSec > 300) {
      const d = lastBarTimeSec ? new Date(lastBarTimeSec * 1000) : null;
      const timeStr = d ? d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false }) : '';
      const dateStr = d ? d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) : '';
      return {
        label: d ? `CLOSED · ${dateStr} ${timeStr}` : 'CLOSED',
        tone: 'closed' as const,
      };
    }
    if (dataAgeSec > 30) {
      return { label: `FEED LAG ${dataAgeSec}s`, tone: 'delayed' as const };
    }
    return { label: 'LIVE STREAM', tone: 'live' as const };
  }, [dataAgeSec, candleCount, lastBarTimeSec]);

  return (
    <div className="flex flex-col h-full bg-[#0a0c10] border border-border/80 rounded-lg overflow-hidden select-none relative">
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

          {vwap.value != null ? (
            <span
              className="text-[10px] text-amber-500/90 font-mono flex items-center gap-1 ml-1"
              title={`Session VWAP ₹${vwap.value.toFixed(2)}`}
            >
              <span className="w-2 h-0.5 bg-amber-500 inline-block" /> VWAP
              {vwap.distance != null ? (
                <span className={vwap.distance >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                  {vwap.distance >= 0 ? '+' : ''}{vwap.distance.toFixed(1)}
                </span>
              ) : null}
            </span>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          {/* Snap to Now */}
          <button
            type="button"
            onClick={snapToNow}
            className="hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-secondary/70 hover:bg-secondary text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            title="Snap chart viewport to latest candle"
          >
            <CornerDownRight className="w-3 h-3" />
            <span>Now</span>
          </button>

          <span
            className={`hidden sm:inline-flex items-center gap-1.5 font-mono text-[10px] px-2 py-0.5 rounded border ${
              sessionStatus.tone === 'live'
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : sessionStatus.tone === 'delayed'
                  ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                  : 'bg-secondary/70 text-muted-foreground border-border/50'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                sessionStatus.tone === 'live'
                  ? 'bg-emerald-400 animate-pulse'
                  : sessionStatus.tone === 'delayed'
                    ? 'bg-amber-400'
                    : 'bg-muted-foreground'
              }`}
            />
            <span>{sessionStatus.label}</span>
          </span>

          {/* Timeframe Selector */}
          <div className="flex items-center bg-secondary/60 rounded p-0.5 border border-border/40" role="tablist">
            {(['1m', '3m', '5m'] as const).map((tf) => (
              <button
                key={tf}
                type="button"
                role="tab"
                aria-selected={timeframe === tf}
                onClick={() => onTimeframeChange?.(tf)}
                className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors cursor-pointer ${
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
            onClick={() => void fetchCandles()}
            disabled={busy}
            className="p-1 hover:bg-secondary rounded text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 cursor-pointer"
            title={`Last updated: ${lastUpdated || 'Never'}`}
          >
            <RefreshCw className={`w-3 h-3 ${busy ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Chart Canvas Area */}
      <div className="relative flex-1 min-h-[260px]">
        {(loading || refreshing) && !error && (
          <div className="absolute top-2 left-2 z-10 font-mono text-[10px] px-1.5 py-0.5 rounded bg-background/80 border border-border/50 text-muted-foreground pointer-events-none">
            {loading ? 'loading candles…' : 'updating…'}
          </div>
        )}

        {/* Market closed informative overlay */}
        {sessionStatus.tone === 'closed' && (
          <div className="absolute top-2 right-2 z-10 bg-background/85 border border-border/60 rounded p-2 text-[10px] font-mono pointer-events-none shadow-md backdrop-blur-xs flex flex-col gap-0.5">
            <span className="font-bold text-muted-foreground">MARKET CLOSED</span>
            <span className="text-foreground">Session MTM: ₹{scalpCtx.sessionMTM.toFixed(1)}</span>
            <span className="text-muted-foreground">Fired trades: {scalpCtx.autoTradesCount}</span>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background/85 z-10 text-xs p-4 text-center">
            <span className="text-rose-400">{error}</span>
            <button
              type="button"
              onClick={() => void fetchCandles()}
              className="px-2 py-1 rounded bg-secondary hover:bg-secondary/80 text-foreground font-mono text-[11px] border border-border/60 cursor-pointer"
            >
              Retry feed
            </button>
          </div>
        )}

        <div ref={chartContainerRef} className="w-full h-full min-h-[260px]" />
      </div>
    </div>
  );
}
