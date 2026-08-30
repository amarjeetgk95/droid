'use client';

import React, { useEffect, useRef, useMemo, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  IChartApi,
  ISeriesApi,
  CandlestickSeries,
  CandlestickData,
  Time,
} from 'lightweight-charts';
import { BarChart3, RefreshCw, AlertCircle, Maximize2 } from 'lucide-react';
import type { NormalizedCandle, CryptoTicker } from '@/lib/types';

type Props = {
  ticker: CryptoTicker | null;
  candles: NormalizedCandle[];
  timeframe: string;
  onTimeframeChange: (tf: string) => void;
  loading?: boolean;
  onRefresh?: () => void;
};

const TF = ['1m', '5m', '15m', '1h', '4h', '1d'] as const;

function toSec(ts: string): number { return Math.floor(new Date(ts).getTime() / 1000); }

function normalize(raw: NormalizedCandle[]): NormalizedCandle[] {
  if (!raw?.length) return [];
  const m = new Map<number, NormalizedCandle>();
  for (const c of raw) {
    const t = toSec(c.timestamp);
    if (!t) continue;
    if (![c.open, c.high, c.low, c.close].every(Number.isFinite)) continue;
    if (c.high < c.low) continue;
    m.set(t, c);
  }
  const arr = [...m.entries()].sort((a, b) => a[0] - b[0]).map(([, v]) => v);
  return arr.length > 400 ? arr.slice(-400) : arr;
}
function decFor(p: number): number {
  if (p >= 1000) return 2;
  if (p >= 1) return 2;
  if (p >= 0.2) return 3;
  if (p >= 0.05) return 4;
  return 5;
}
function fmt(n: number, d: number): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}

export function CryptoCandleChart({ ticker, candles, timeframe, onTimeframeChange, loading, onRefresh }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const roRef = useRef<ResizeObserver | null>(null);

  const [hover, setHover] = useState<NormalizedCandle | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const rows = useMemo(() => normalize(candles), [candles]);
  const last = rows[rows.length - 1] ?? null;
  const shown = hover ?? last;
  const dec = useMemo(() => decFor(last?.close ?? ticker?.price ?? 50000), [last?.close, ticker?.price]);

  // ---- chart factory (industrial minimal) ----
  const build = useCallback(() => {
    const el = wrapRef.current;
    if (!el) return;
    if (chartRef.current) { try { chartRef.current.remove(); } catch {} }
    if (roRef.current) roRef.current.disconnect();
    setErr(null);

    try {
      const chart = createChart(el, {
        width: el.clientWidth || 760,
        height: el.clientHeight || 360,
        autoSize: false,
        layout: {
          background: { type: ColorType.Solid, color: 'transparent' },
          textColor: '#94a3b8',
          fontFamily: 'ui-monospace, SFMono-Regular, monospace',
          fontSize: 11,
        },
        grid: {
          vertLines: { visible: false },
          horzLines: { color: 'rgba(148,163,184,0.08)', visible: true },
        },
        crosshair: {
          vertLine: { width: 1, color: 'rgba(148,163,184,0.28)', style: 1, labelBackgroundColor: '#0f172a' },
          horzLine: { width: 1, color: 'rgba(148,163,184,0.28)', style: 1, labelBackgroundColor: '#0f172a' },
        },
        rightPriceScale: {
          borderColor: 'rgba(148,163,184,0.18)',
          scaleMargins: { top: 0.08, bottom: 0.08 },
          ticksVisible: true,
          entireTextOnly: false,
          visible: true,
        },
        timeScale: {
          borderColor: 'rgba(148,163,184,0.18)',
          timeVisible: true,
          secondsVisible: false,
          rightOffset: 10,
          barSpacing: 10,
          minBarSpacing: 8,
          fixLeftEdge: false,
          fixRightEdge: true,
          tickMarkFormatter: (t: Time) => {
            const d = new Date((t as number) * 1000);
            if (timeframe === '1d') return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
          },
        },
        handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
        handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
      });

      const cs = chart.addSeries(CandlestickSeries, {
        upColor: '#22c55e',
        downColor: '#ef4444',
        borderUpColor: '#16a34a',
        borderDownColor: '#dc2626',
        wickUpColor: '#22c55e',
        wickDownColor: '#ef4444',
        borderVisible: false,
        wickVisible: true,
        priceFormat: { type: 'price', precision: dec, minMove: Math.pow(10, -dec) },
        priceLineVisible: false,
        lastValueVisible: true,
      });

      chart.subscribeCrosshairMove((param) => {
        if (!param?.time) { setHover(null); return; }
        const t = param.time as number;
        const found = rows.find((c) => toSec(c.timestamp) === t);
        setHover(found ?? null);
      });

      chartRef.current = chart;
      seriesRef.current = cs;

      const ro = new ResizeObserver(() => {
        if (!wrapRef.current || !chartRef.current) return;
        const r = wrapRef.current.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) chartRef.current.applyOptions({ width: Math.floor(r.width), height: Math.floor(r.height) });
      });
      ro.observe(el);
      roRef.current = ro;

      requestAnimationFrame(() => {
        const r = el.getBoundingClientRect();
        chart.applyOptions({ width: Math.floor(r.width), height: Math.floor(r.height) });
      });
    } catch (e: any) {
      setErr(e?.message ?? 'Chart init failed');
    }
  }, [dec, timeframe, rows]);

  useEffect(() => {
    build();
    return () => {
      if (roRef.current) roRef.current.disconnect();
      if (chartRef.current) try { chartRef.current.remove(); } catch {}
    };
    // rebuild only on timeframe/precision, not every tick
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeframe, dec]);

  useEffect(() => {
    seriesRef.current?.applyOptions({ priceFormat: { type: 'price', precision: dec, minMove: Math.pow(10, -dec) } as any });
  }, [dec]);

  // ---- data (TradingView: past always visible, scroll preserved) ----
  const fittedKeyRef = useRef('');
  useEffect(() => {
    const cs = seriesRef.current;
    const ch = chartRef.current;
    if (!cs || !ch) return;

    if (rows.length === 0) {
      cs.setData([]);
      fittedKeyRef.current = '';
      return;
    }

    const cData: CandlestickData<Time>[] = rows.map((c) => ({
      time: toSec(c.timestamp) as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    const key = `${cData[0].time}|${cData.length}|${timeframe}`;
    const isSameSeries = fittedKeyRef.current === key;

    cs.setData(cData);
    if (!isSameSeries) {
      ch.timeScale().fitContent();
      // TradingView: show last 60 bars wide, not 100 cramped — prevents mesh
      const total = cData.length;
      if (total > 60) {
        try { ch.timeScale().setVisibleLogicalRange({ from: total - 60, to: total }); } catch {}
      }
      fittedKeyRef.current = key;
    }
  }, [rows, timeframe]);

  // ensure fit after container becomes visible
  useEffect(() => {
    if (fittedKeyRef.current && rows.length) {
      const t = setTimeout(() => chartRef.current?.timeScale().fitContent(), 60);
      return () => clearTimeout(t);
    }
  }, [rows.length]);

  return (
    <div className="bg-card border border-border rounded-xl shadow-sm flex flex-col h-[560px] overflow-hidden">
      <div className="h-[64px] min-h-[64px] flex items-center justify-between px-4 border-b border-border bg-card">
        <div className="flex items-center gap-3 min-w-0">
          <div className="size-8 rounded-lg bg-emerald-600 text-white grid place-items-center shrink-0"><BarChart3 className="size-4" /></div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold font-mono text-[13px] text-foreground">{ticker?.symbol ?? 'BTCUSDT'}</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-secondary border border-border text-muted-foreground">BINANCE</span>
              {last && (
                <span className={`text-[11px] font-mono font-semibold tabular-nums ${last.close >= last.open ? 'text-emerald-500' : 'text-rose-500'}`}>
                  {(last.close - last.open >= 0 ? '+' : '') + fmt(last.close - last.open, dec)} ({(((last.close - last.open) / last.open) * 100).toFixed(2)}%)
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-[11px] font-mono text-muted-foreground mt-1">
              {shown ? (
                <>
                  <span>O <b className="text-foreground">{fmt(shown.open, dec)}</b></span>
                  <span>H <b className="text-foreground">{fmt(shown.high, dec)}</b></span>
                  <span>L <b className="text-foreground">{fmt(shown.low, dec)}</b></span>
                  <span>C <b className={shown.close >= shown.open ? 'text-emerald-500' : 'text-rose-500'}>{fmt(shown.close, dec)}</b></span>
                  <span className="hidden sm:inline">Vol <b className="text-foreground">{shown.volume.toLocaleString()}</b></span>
                  {hover && <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 border border-amber-500/20">HOVER</span>}
                </>
              ) : <span className="text-muted-foreground">—</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <div className="flex bg-secondary rounded-lg p-1 border border-border">
            {TF.map((tf) => (
              <button key={tf} onClick={() => onTimeframeChange(tf)} className={`px-2.5 py-1 text-xs font-mono rounded-md ${timeframe === tf ? 'bg-primary text-primary-foreground font-semibold shadow' : 'text-muted-foreground hover:text-foreground hover:bg-card'}`}>{tf}</button>
            ))}
          </div>
          <button onClick={() => chartRef.current?.timeScale().fitContent()} title="Fit" className="size-8 grid place-items-center bg-secondary border border-border rounded-lg hover:bg-card">
            <Maximize2 className="size-4 text-muted-foreground" />
          </button>
          <button onClick={onRefresh} disabled={!!loading} title="Reload" className="size-8 grid place-items-center bg-secondary border border-border rounded-lg disabled:opacity-50">
            <RefreshCw className={`size-4 text-muted-foreground ${loading ? 'animate-spin text-primary' : ''}`} />
          </button>
        </div>
      </div>

      <div className="relative flex-1 min-h-0 bg-card">
        {loading && rows.length === 0 && (
          <div className="absolute inset-0 z-10 grid place-items-center bg-card/60 text-xs font-mono text-muted-foreground">
            <span className="inline-flex items-center gap-2"><RefreshCw className="size-4 animate-spin text-primary" /> Loading…</span>
          </div>
        )}
        {err && (
          <div className="absolute inset-0 z-20 grid place-items-center bg-card p-6 text-center">
            <AlertCircle className="size-6 text-amber-500 mb-2" />
            <p className="text-xs font-mono text-muted-foreground">{err}</p>
            <button onClick={() => { setErr(null); onRefresh?.(); }} className="mt-3 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs">Retry</button>
          </div>
        )}
        {!loading && !err && rows.length === 0 && <div className="absolute inset-0 grid place-items-center text-xs font-mono text-muted-foreground">No data</div>}
        <div ref={wrapRef} className="absolute inset-0" />
        <div className="absolute bottom-1.5 left-2 text-[10px] font-mono text-muted-foreground bg-card/80 px-2 py-0.5 rounded border border-border">BINANCE • {ticker?.symbol ?? 'BTCUSDT'} • {timeframe} • {rows.length} bars • drag to see past</div>
        {ticker && <div className="absolute bottom-1.5 right-2 text-[10px] font-mono tabular-nums bg-primary text-primary-foreground px-2 py-0.5 rounded">LIVE {fmt(ticker.price, dec)}</div>}
      </div>
    </div>
  );
}
