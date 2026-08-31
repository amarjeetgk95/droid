'use client';

import React, { useState, useEffect, useCallback } from 'react';
import TopBar from '@/components/TradingChart/TopBar';
import SideTools from '@/components/TradingChart/SideTools';
import Legend from '@/components/TradingChart/Legend';
import StatusBar from '@/components/TradingChart/StatusBar';
import ChartCanvas from '@/components/TradingChart/ChartCanvas';
import { useRealCandleDataWithSymbol } from '@/components/TradingChart/useRealCandleData';
import '@/components/TradingChart/TradingChart.css';

// Map frontend timeframe string to Inc TF number
const TF_LABEL_TO_VALUE = {
  '1m': 1,
  '5m': 5,
  '15m': 15,
  '1h': 60,
  '1D': 1440,
};

const VALUE_TO_LABEL = {
  1: '1m',
  5: '5m',
  15: '15m',
  60: '1h',
  240: '4h',
  1440: '1D',
};

const INDIAN_SYMBOLS = ['NIFTY 50', 'BANKNIFTY', 'FINNIFTY', 'SENSEX', 'INDIA VIX'];
const EXCHANGE_LABEL_MAP = {
  'NIFTY 50': 'NSE · Index',
  'BANKNIFTY': 'NSE · Bank',
  'FINNIFTY': 'NSE · Financial',
  'SENSEX': 'BSE · Index',
  'INDIA VIX': 'NSE · Volatility',
};

export default function DashboardTradingChart({ defaultSymbol = 'NIFTY 50', className = '', style = undefined }) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [tf, setTf] = useState(5); // 5m default like dashboard
  const [chartType, setChartType] = useState('candle');
  const [live, setLive] = useState(true);
  const [view, setView] = useState({ start: 0, count: 120 });
  const [hoverIdx, setHoverIdx] = useState(null);

  const { data, loading, error } = useRealCandleDataWithSymbol(symbol, tf, live);

  // Keep viewport pinned to latest bars as new data streams
  useEffect(() => {
    if (!data.length) return;
    setView((v) => {
      const end = v.start + v.count;
      if (end >= data.length - 2) {
        return { ...v, start: Math.max(0, data.length - v.count + 8) };
      }
      return v;
    });
  }, [data.length]);

  const lastPrice = data.length ? data[data.length - 1].c : 0;
  const changePct =
    data.length > 1
      ? ((data[data.length - 1].c - data[Math.max(0, data.length - 25)].c) / data[Math.max(0, data.length - 25)].c) * 100
      : 0;

  const reset = useCallback(() => {
    setView({ count: Math.min(140, data.length || 120), start: Math.max(0, (data.length || 120) - 140 + 8) });
  }, [data.length]);

  useEffect(() => {
    if (data.length && view.count === 120 && view.start === 0) reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.length]);

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (ev) => {
      const k = ev.key;
      if (k === '+' || k === '=') {
        setView((v) => ({ ...v, count: Math.max(20, v.count * 0.8) }));
      } else if (k === '-' || k === '_') {
        setView((v) => ({ ...v, count: Math.min(data.length || 140, v.count * 1.25) }));
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

  const exchangeLabel = EXCHANGE_LABEL_MAP[symbol] || 'NSE · Index';

  // Wrap setTf to handle both number and string from TopBar
  const handleSetTf = (val) => {
    if (typeof val === 'number') setTf(val);
    else if (TF_LABEL_TO_VALUE[val]) setTf(TF_LABEL_TO_VALUE[val]);
    else setTf(val);
  };

  return (
    <div
      className={`tc-root h-full w-full flex flex-col bg-white text-[#131722] rounded-lg overflow-hidden border border-[#e0e3eb] shadow-sm ${className}`}
      style={style}
    >
      <TopBar
        symbol={symbol}
        exchangeLabel={exchangeLabel}
        tf={tf}
        setTf={handleSetTf}
        chartType={chartType}
        setChartType={setChartType}
        live={live}
        setLive={setLive}
        lastPrice={lastPrice}
        changePct={changePct}
        onReset={reset}
      />
      {/* Symbol selector for Indian market — TradingView-style */}
      <div className="flex items-center gap-1 px-2 py-1.5 bg-white border-b border-[#e0e3eb] overflow-x-auto">
        {INDIAN_SYMBOLS.map((s) => (
          <button
            key={s}
            onClick={() => setSymbol(s)}
            className={`px-3 py-1 rounded text-xs font-medium whitespace-nowrap border ${symbol === s ? 'bg-[#2962ff] text-white border-[#2962ff]' : 'bg-white text-[#6a6d78] border-[#e0e3eb] hover:bg-[#f0f3fa] hover:text-[#131722]'}`}
          >
            {s}
          </button>
        ))}
        <span className="ml-auto text-[10px] text-[#6a6d78] hidden sm:block">
          {loading ? 'Loading…' : error ? `Error: ${error}` : `${data.length} bars · ${VALUE_TO_LABEL[tf] || tf + 'm'}`}
        </span>
      </div>
      <div className="flex-1 flex min-h-0 bg-white">
        <SideTools />
        <main className="flex-1 relative min-w-0 flex bg-white">
          {loading ? (
            <div className="flex-1 flex items-center justify-center bg-white text-[#6a6d78] text-sm">Loading chart data…</div>
          ) : error ? (
            <div className="flex-1 flex items-center justify-center bg-white text-[#ef5350] text-sm p-4 text-center">{error}</div>
          ) : data.length === 0 ? (
            <div className="flex-1 flex items-center justify-center bg-white text-[#6a6d78] text-sm">No candle data</div>
          ) : (
            <>
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
                  className="w-7 h-7 rounded bg-white border border-[#e0e3eb] text-[#6a6d78] hover:text-[#131722] hover:bg-[#f0f3fa] shadow-sm text-sm"
                  title="Fit all bars"
                  onClick={reset}
                >
                  ⤢
                </button>
                <button
                  className="w-7 h-7 rounded bg-white border border-[#e0e3eb] text-[#6a6d78] hover:text-[#131722] hover:bg-[#f0f3fa] shadow-sm text-sm"
                  title="Zoom in (+)"
                  onClick={() => setView((v) => ({ ...v, count: Math.max(20, v.count * 0.8) }))}
                >
                  +
                </button>
                <button
                  className="w-7 h-7 rounded bg-white border border-[#e0e3eb] text-[#6a6d78] hover:text-[#131722] hover:bg-[#f0f3fa] shadow-sm text-sm"
                  title="Zoom out (−)"
                  onClick={() => setView((v) => ({ ...v, count: Math.min(data.length, v.count * 1.25) }))}
                >
                  −
                </button>
              </div>
              <div className="absolute left-3 bottom-[30px] text-[10px] text-[#9598a1] pointer-events-none">
                scroll = zoom · drag = pan · double-click = reset
              </div>
            </>
          )}
        </main>
      </div>
      <StatusBar data={data} view={view} />
    </div>
  );
}
