'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  IChartApi,
  ISeriesApi,
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
}

interface ScalperChartProps {
  symbol: string;
  timeframe?: '1m' | '3m' | '5m';
  onTimeframeChange?: (tf: '1m' | '3m' | '5m') => void;
  spotPrice?: number | null;
}

export function ScalperChart({
  symbol,
  timeframe = '1m',
  onTimeframeChange,
  spotPrice,
}: ScalperChartProps) {
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const vwapSeriesRef = useRef<ISeriesApi<'Line'> | any>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');

  const fetchCandles = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      // Map 3m to 1m for backend compatibility if 3m isn't a direct API query enum
      const queryTf = timeframe === '3m' ? '1m' : timeframe;
      const res = await api.getCandles(symbol, queryTf, 120);
      const rawCandles = (res.data || []) as unknown as CandleData[];

      if (!rawCandles || rawCandles.length === 0) {
        setError('No candle data available for this session');
        return;
      }

      // Convert timestamps to unix seconds and sort
      const formatted = rawCandles
        .map((c) => {
          const t = Math.floor(new Date(c.timestamp).getTime() / 1000);
          return {
            time: t as unknown as string,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
            volume: c.volume || 1,
          };
        })
        .filter((c) => !isNaN(Number(c.time)))
        .sort((a, b) => Number(a.time) - Number(b.time));

      // Deduplicate consecutive identical timestamps if any
      const deduped: typeof formatted = [];
      for (const item of formatted) {
        if (deduped.length === 0 || deduped[deduped.length - 1].time !== item.time) {
          deduped.push(item);
        }
      }

      if (candleSeriesRef.current) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        candleSeriesRef.current.setData(deduped as any);
      }

      // Compute Intraday VWAP
      let cumVol = 0;
      let cumVwapVol = 0;
      const vwapData = deduped.map((c) => {
        const typical = (c.open + c.high + c.low + c.close) / 4;
        cumVol += c.volume;
        cumVwapVol += typical * c.volume;
        const vwapVal = cumVol > 0 ? cumVwapVol / cumVol : c.close;
        return {
          time: c.time,
          value: Number(vwapVal.toFixed(2)),
        };
      });

      if (vwapSeriesRef.current) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        vwapSeriesRef.current.setData(vwapData as any);
      }

      setLastUpdated(new Date().toLocaleTimeString('en-IN', { hour12: false }));
    } catch (err: unknown) {
      setError((err as Error)?.message || 'Failed to load candle feed');
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe]);

  // Initialize Chart
  useEffect(() => {
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
        scaleMargins: { top: 0.1, bottom: 0.1 },
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
    });

    // VWAP Overlay Line
    const activeVwapSeries = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 2,
      title: 'VWAP',
      priceLineVisible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = activeCandleSeries;
    vwapSeriesRef.current = activeVwapSeries;

    const resizeObserver = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0) return;
      const { width, height } = entries[0].contentRect;
      chart.applyOptions({ width, height });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      vwapSeriesRef.current = null;
    };
  }, []);

  // Fetch data on symbol/timeframe changes
  useEffect(() => {
    fetchCandles();
    const interval = setInterval(fetchCandles, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, [fetchCandles]);

  return (
    <div className="flex flex-col h-full bg-[#0a0c10] border border-border/80 rounded-lg overflow-hidden select-none">
      {/* Chart Control Bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-card/60 border-b border-border/60 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-bold tracking-wide flex items-center gap-1.5 text-foreground">
            <BarChart2 className="w-3.5 h-3.5 text-amber-500" />
            {symbol} 1M Execution Chart
          </span>
          {spotPrice ? (
            <span className="font-mono text-emerald-400 font-semibold bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
              ₹{spotPrice.toFixed(2)}
            </span>
          ) : null}
          <span className="text-[10px] text-amber-500/90 font-mono flex items-center gap-1 ml-1">
            <span className="w-2 h-0.5 bg-amber-500 inline-block" /> VWAP
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Timeframe selector */}
          <div className="flex items-center bg-secondary/60 rounded p-0.5 border border-border/40">
            {(['1m', '3m', '5m'] as const).map((tf) => (
              <button
                key={tf}
                type="button"
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
            disabled={loading}
            className="p-1 hover:bg-secondary rounded text-muted-foreground hover:text-foreground transition-colors"
            title={`Last updated: ${lastUpdated || 'Never'}`}
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Chart Canvas Area */}
      <div className="relative flex-1 min-h-[280px]">
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10 text-xs text-rose-400 p-4 text-center">
            {error}
          </div>
        )}
        <div ref={chartContainerRef} className="w-full h-full" />
      </div>
    </div>
  );
}
