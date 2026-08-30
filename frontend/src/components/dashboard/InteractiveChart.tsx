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

  useEffect(() => {
    if (!chartContainerRef.current) return;
    const chart = createChart(chartContainerRef.current, {
      layout: { background: { color: '#ffffff' }, textColor: '#71717a' },
      grid: { vertLines: { color: '#f1f5f9' }, horzLines: { color: '#f1f5f9' } },
      width: chartContainerRef.current.clientWidth,
      height: 400,
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    chartRef.current = chart;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

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

    const candleData = candles.map(c => ({
      time: Math.floor(new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candlestickSeries.setData(candleData);

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
      
      {loading ? (
        <div className="h-[400px] flex items-center justify-center text-muted-foreground animate-pulse">Loading chart data...</div>
      ) : error ? (
        <div className="h-[400px] flex items-center justify-center text-destructive">{error}</div>
      ) : (
        <div ref={chartContainerRef} className="w-full h-[400px]" />
      )}
    </div>
  );
}
