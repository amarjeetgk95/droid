'use client';

import { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, CandlestickSeries, HistogramSeries, LineSeries, UTCTimestamp, ISeriesApi } from 'lightweight-charts';
import { useCandles } from '@/hooks/useMarketData';

export function InteractiveChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [symbol, setSymbol] = useState('NIFTY 50');
  const [timeframe, setTimeframe] = useState('5m');

  const { candles, loading, error } = useCandles(symbol, timeframe);

  // Create chart once container is mounted (after loading finishes).
  // Previously chart was created while loading=true when container was not in DOM,
  // so chartRef stayed null and the data effect never rendered — chart appeared blank.
  useEffect(() => {
    if (loading || error) return;
    if (!chartContainerRef.current) return;
    if (chartRef.current) return; // already created

    const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
    const chart = createChart(chartContainerRef.current, {
      layout: { background: { color: isDark ? '#09090b' : '#ffffff' }, textColor: isDark ? '#a1a1aa' : '#71717a' },
      grid: { vertLines: { color: isDark ? '#27272a' : '#f1f5f9' }, horzLines: { color: isDark ? '#27272a' : '#f1f5f9' } },
      width: chartContainerRef.current.clientWidth,
      height: 400,
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    chartRef.current = chart;

    const ro = new ResizeObserver(() => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    });
    ro.observe(chartContainerRef.current);
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [loading, error]);

  useEffect(() => {
    if (!chartRef.current || !candles.length) return;
    
    const chart = chartRef.current;
    
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });

    const candleData = candles
      .map(c => ({
        time: Math.floor(new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
      .sort((a, b) => (a.time as number) - (b.time as number));
    // De-duplicate timestamps (lightweight-charts requires strictly increasing time)
    const seen = new Set<number>();
    const deduped = candleData.filter(d => {
      const t = d.time as number;
      if (seen.has(t)) return false;
      seen.add(t);
      return true;
    });
    candlestickSeries.setData(deduped);

    // VWAP Line Series (blue)
    const vwapData = candles
      .filter(c => c.vwap !== null && c.vwap !== undefined)
      .map(c => ({
        time: Math.floor(new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
        value: c.vwap as number,
      }));

    let vwapSeries: ISeriesApi<'Line'> | null = null;
    if (vwapData.length > 0) {
      vwapSeries = chart.addSeries(LineSeries, {
        color: '#3b82f6',
        lineWidth: 1,
        title: 'VWAP',
      });
      vwapSeries.setData(vwapData);
    }

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const volumeData = candles.map(c => ({
      time: Math.floor(new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
      value: c.volume,
      color: c.close >= c.open ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)',
    }));
    volumeSeries.setData(volumeData);

    chart.timeScale().fitContent();
    
    return () => {
      chart.removeSeries(candlestickSeries);
      if (vwapSeries) chart.removeSeries(vwapSeries);
      chart.removeSeries(volumeSeries);
    };
  }, [candles]);

  const symbols = ['NIFTY 50', 'BANKNIFTY', 'FINNIFTY', 'SENSEX', 'INDIA VIX'];
  const timeframes = ['1m', '5m', '15m', '1h', '1D'];

  return (
    <div className="flex flex-col h-full gap-4">
      <div className="flex justify-between items-center">
        <div className="flex gap-2">
          {symbols.map(s => (
            <button key={s} onClick={() => setSymbol(s)} className={`px-3 py-1 rounded text-sm font-medium ${symbol === s ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'}`}>{s}</button>
          ))}
        </div>
        <div className="flex gap-2">
          {timeframes.map(t => (
            <button key={t} onClick={() => setTimeframe(t)} className={`px-2 py-1 rounded text-xs font-medium ${timeframe === t ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'}`}>{t}</button>
          ))}
        </div>
      </div>
      
      {/* Chart container is always mounted so createChart can measure width.
          Loading/error overlays are positioned on top. */}
      <div className="relative w-full h-[400px]">
        <div ref={chartContainerRef} className="w-full h-[400px]" />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-card/80 text-muted-foreground animate-pulse text-sm">Loading chart data...</div>
        )}
        {error && !loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-card/80 text-destructive text-sm">{error}</div>
        )}
        {!loading && !error && candles.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center bg-card/80 text-muted-foreground text-sm">No candle data</div>
        )}
      </div>
    </div>
  );
}
