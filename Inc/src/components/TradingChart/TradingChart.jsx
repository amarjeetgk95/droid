import React, { useState, useEffect, useCallback } from 'react';
import TopBar from './TopBar';
import SideTools from './SideTools';
import Legend from './Legend';
import StatusBar from './StatusBar';
import ChartCanvas from './ChartCanvas';
import { useCandleData } from './useCandleData';
import './TradingChart.css';

/**
 * TradingChart
 * Drop-in TradingView-style candlestick chart. No indicators, no chart
 * library — just React + Canvas.
 *
 * Usage:
 *   import TradingChart from './components/TradingChart';
 *   <TradingChart symbol="BTCUSDT" className="h-[600px]" />
 *
 * To wire up real data, swap out `useCandleData` for a hook that fetches
 * from your own API/WebSocket and returns the same shape:
 *   [{ t: number(ms), o: number, h: number, l: number, c: number, v: number }, ...]
 */
export default function TradingChart({
  symbol = 'BTCUSDT',
  exchangeLabel = 'Binance · Crypto',
  defaultTimeframe = 60,
  className = '',
  style,
}) {
  const [tf, setTf] = useState(defaultTimeframe);
  const [chartType, setChartType] = useState('candle');
  const [live, setLive] = useState(true);
  const [view, setView] = useState({ start: 0, count: 120 });
  const [hoverIdx, setHoverIdx] = useState(null);

  const data = useCandleData(tf, live);

  // keep the viewport pinned to the latest bars as new data streams in
  useEffect(() => {
    if (!data.length) return;
    setView((v) => {
      const end = v.start + v.count;
      if (end >= data.length - 2) {
        return { ...v, start: data.length - v.count + 8 };
      }
      return v;
    });
  }, [data.length]);

  const lastPrice = data.length ? data[data.length - 1].c : 0;
  const changePct =
    data.length > 1
      ? ((data[data.length - 1].c - data[Math.max(0, data.length - 25)].c) /
          data[Math.max(0, data.length - 25)].c) *
        100
      : 0;

  const reset = useCallback(() => {
    setView({ count: Math.min(140, data.length), start: Math.max(0, data.length - 140 + 8) });
  }, [data.length]);

  // initial fit once data first loads
  useEffect(() => {
    if (data.length && view.count === 120 && view.start === 0) reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.length]);

  // keyboard shortcuts: +/− zoom, ←/→ pan, R reset
  useEffect(() => {
    const onKey = (ev) => {
      const k = ev.key;
      if (k === '+' || k === '=') {
        setView((v) => ({ ...v, count: Math.max(20, v.count * 0.8) }));
      } else if (k === '-' || k === '_') {
        setView((v) => ({ ...v, count: Math.min(data.length, v.count * 1.25) }));
      } else if (k === 'ArrowLeft') {
        setView((v) => ({ ...v, start: v.start - 3 }));
      } else if (k === 'ArrowRight') {
        setView((v) => ({ ...v, start: v.start + 3 }));
      } else if (k.toLowerCase() === 'r') {
        reset();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [data.length, reset]);

  const onHover = useCallback((i) => setHoverIdx((prev) => (prev === i ? prev : i)), []);

  return (
    <div
      className={`tc-root h-full w-full flex flex-col bg-[#131722] text-[#d1d4dc] ${className}`}
      style={style}
    >
      <TopBar
        symbol={symbol}
        exchangeLabel={exchangeLabel}
        tf={tf}
        setTf={setTf}
        chartType={chartType}
        setChartType={setChartType}
        live={live}
        setLive={setLive}
        lastPrice={lastPrice}
        changePct={changePct}
        onReset={reset}
      />
      <div className="flex-1 flex min-h-0">
        <SideTools />
        <main className="flex-1 relative min-w-0 flex">
          <ChartCanvas
            data={data}
            tf={tf}
            chartType={chartType}
            view={view}
            setView={setView}
            onHover={onHover}
            onReset={reset}
            symbol={symbol}
          />
          <Legend symbol={symbol} data={data} hoverIdx={hoverIdx ?? data.length - 1} tf={tf} />
          <div className="absolute right-[70px] bottom-[34px] flex flex-col gap-1">
            <button
              className="w-7 h-7 rounded bg-[#1e222d] border border-[#2a2e39] text-[#b2b5be] hover:text-white text-sm"
              title="Fit all bars"
              onClick={reset}
            >
              ⤢
            </button>
            <button
              className="w-7 h-7 rounded bg-[#1e222d] border border-[#2a2e39] text-[#b2b5be] hover:text-white text-sm"
              title="Zoom in (+)"
              onClick={() => setView((v) => ({ ...v, count: Math.max(20, v.count * 0.8) }))}
            >
              +
            </button>
            <button
              className="w-7 h-7 rounded bg-[#1e222d] border border-[#2a2e39] text-[#b2b5be] hover:text-white text-sm"
              title="Zoom out (−)"
              onClick={() => setView((v) => ({ ...v, count: Math.min(data.length, v.count * 1.25) }))}
            >
              −
            </button>
          </div>
          <div className="absolute left-3 bottom-[30px] text-[10px] text-[#5d606b] pointer-events-none">
            scroll = zoom · drag = pan · double-click = reset
          </div>
        </main>
      </div>
      <StatusBar data={data} view={view} />
    </div>
  );
}
