'use client';
import { useEffect, useRef, useState } from 'react';

interface Props { data: any; timeframe?: string; }

function tfMinutes(tf: string): number {
  const m: Record<string, number> = { '1m':1, '5m':5, '15m':15, '1h':60, '30m':30, '4h':240, '1D':1440 };
  return m[tf] ?? 15;
}

export function ForecastChart({ data, timeframe = '15m' }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const seriesRef = useRef<any>(null);
  const [showOverlays, setShowOverlays] = useState({ vwap:true, ema:true, walls:true });

  if (!data) return null;
  const activeTf = data.timeframes?.[timeframe] ? timeframe : Object.keys(data.timeframes||{})[0] || '15m';
  const tfData = data.timeframes?.[activeTf];
  const forecast = data.forecasts?.[activeTf];
  const candles: any[] = data.candles?.[activeTf] || [];
  const fno = data.fno;

  useEffect(() => {
    if (!containerRef.current || !candles.length) return;
    let chart: any;
    let candleSeries: any, medianSeries: any, upperSeries: any, lowerSeries: any, vwapSeries: any, ema20Series: any, ema50Series: any;
    const el = containerRef.current;
    // Clear previous
    el.innerHTML = '';
    const create = async () => {
      const lwc: any = await import('lightweight-charts');
      const { createChart, ColorType, CandlestickSeries, LineSeries, AreaSeries } = lwc;
      chart = createChart(el, {
        layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#9ca3af' },
        grid: { vertLines: { color: 'rgba(255,255,255,0.06)' }, horzLines: { color: 'rgba(255,255,255,0.06)' } },
        width: el.clientWidth,
        height: 380,
        rightPriceScale: { borderColor: '#334155' },
        timeScale: { borderColor: '#334155', timeVisible: true, secondsVisible: false },
        crosshair: { mode: 0 },
      });
      chartRef.current = chart;

      // Candlestick (historical solid)
      try {
        candleSeries = chart.addSeries(CandlestickSeries, {
          upColor: '#22c55e', downColor: '#ef4444',
          borderUpColor: '#22c55e', borderDownColor: '#ef4444',
          wickUpColor: '#22c55e', wickDownColor: '#ef4444',
        });
      } catch {
        // fallback v4 API
        candleSeries = (chart as any).addCandlestickSeries({ upColor: '#22c55e', downColor: '#ef4444' });
      }
      seriesRef.current = candleSeries;

      const candleData = candles.map((c:any) => ({
        time: Math.floor(new Date(c.timestamp).getTime()/1000) as any,
        open: c.open, high: c.high, low: c.low, close: c.close
      }));
      candleSeries.setData(candleData);

      // Support / Resistance lines
      if (tfData?.support_resistance) {
        const sr = tfData.support_resistance;
        if (sr.support) {
          candleSeries.createPriceLine({ price: sr.support, color: '#22c55e', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `S ${sr.support}` });
        }
        if (sr.resistance) {
          candleSeries.createPriceLine({ price: sr.resistance, color: '#ef4444', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `R ${sr.resistance}` });
        }
        // F&O walls
        if (showOverlays.walls && fno?.available) {
          if (fno.call_wall) candleSeries.createPriceLine({ price: fno.call_wall, color: '#f97316', lineWidth: 1, lineStyle: 1, axisLabelVisible: true, title: `Call Wall ${fno.call_wall}` });
          if (fno.put_wall) candleSeries.createPriceLine({ price: fno.put_wall, color: '#06b6d4', lineWidth: 1, lineStyle: 1, axisLabelVisible: true, title: `Put Wall ${fno.put_wall}` });
          if (fno.max_pain) candleSeries.createPriceLine({ price: fno.max_pain, color: '#a855f7', lineWidth: 1, lineStyle: 3, axisLabelVisible: true, title: `Max Pain ${fno.max_pain}` });
        }
      }

      // EMA/VWAP overlays (optional)
      if (showOverlays.ema && candles.length) {
        const lastClose = candles[candles.length-1].close;
        const ema20 = tfData?.trend?.ema20 ?? lastClose;
        const ema50 = tfData?.trend?.ema50 ?? lastClose;
        const vwap = tfData?.trend?.vwap ?? tfData?.support_resistance?.vwap ?? null;
        // create line series for EMA if we have values
        const lineOpts = (color:string, style:number)=>({ color, lineWidth: 1, lineStyle: style, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false });
        // Simple flat lines as proxy (proper EMA series would require per-candle values)
        // Instead draw price lines
        if (ema20) candleSeries.createPriceLine({ price: ema20, color: '#eab308', lineWidth:1, lineStyle:0, axisLabelVisible:true, title:'EMA20' });
        if (ema50) candleSeries.createPriceLine({ price: ema50, color: '#3b82f6', lineWidth:1, lineStyle:0, axisLabelVisible:true, title:'EMA50' });
        if (showOverlays.vwap && vwap) candleSeries.createPriceLine({ price: vwap, color: '#f59e0b', lineWidth:1, lineStyle:2, axisLabelVisible:true, title:'VWAP' });
      }

      // Forecast overlay — must begin exactly at latest valid market timestamp + 1 TF
      if (forecast && candleData.length) {
        const lastTime = candleData[candleData.length-1].time as number;
        const horizon = forecast.horizon_minutes ?? tfMinutes(activeTf)*4;
        const tfMin = tfMinutes(activeTf);
        const steps = Math.max(2, Math.round(horizon / tfMin));
        const curPrice = tfData?.current_price ?? candles[candles.length-1].close;
        const low = forecast.expected_range.low;
        const high = forecast.expected_range.high;
        const medianTarget = (low + high)/2;
        // Generate median path with slight curve toward target
        const medianData: any[] = [];
        const upperData: any[] = [];
        const lowerData: any[] = [];
        for (let i=1; i<=steps; i++) {
          const t = (lastTime + i*tfMin*60) as any;
          const prog = i/steps;
          // ease
          const eased = prog*prog*(3 - 2*prog); // smoothstep
          const median = curPrice + (medianTarget - curPrice)*eased;
          // range expands then contracts? linear for now
          const up = curPrice + (high - curPrice)*eased;
          const lo = curPrice + (low - curPrice)*eased;
          medianData.push({ time: t, value: median });
          upperData.push({ time: t, value: up });
          lowerData.push({ time: t, value: lo });
        }
        // Median line — distinct dashed translucent style
        try {
          medianSeries = chart.addSeries(LineSeries, { color: 'rgba(99,102,241,0.95)', lineWidth: 2, lineStyle: 2, priceLineVisible:false, lastValueVisible:true, crosshairMarkerVisible:true, title: 'PREDICTED median' });
        } catch { medianSeries = (chart as any).addLineSeries({ color: 'rgba(99,102,241,0.95)', lineWidth:2, lineStyle:2 }); }
        medianSeries.setData(medianData);
        // Upper/lower range — translucent
        try {
          upperSeries = chart.addSeries(LineSeries, { color: 'rgba(99,102,241,0.35)', lineWidth: 1, lineStyle: 1, priceLineVisible:false, lastValueVisible:false });
          lowerSeries = chart.addSeries(LineSeries, { color: 'rgba(99,102,241,0.35)', lineWidth: 1, lineStyle: 1, priceLineVisible:false, lastValueVisible:false });
        } catch {
          upperSeries = (chart as any).addLineSeries({ color: 'rgba(99,102,241,0.35)', lineWidth:1 });
          lowerSeries = (chart as any).addLineSeries({ color: 'rgba(99,102,241,0.35)', lineWidth:1 });
        }
        upperSeries.setData(upperData);
        lowerSeries.setData(lowerData);
        // Confidence band area — use AreaSeries between lower and median? lightweight-charts can't fill between lines, so we use a translucent area from lower to upper via histogram hack not needed; lines suffice plus opacity.
        // Add markers for forecast start
        try {
          candleSeries.setMarkers([{ time: lastTime, position: 'aboveBar', color: '#6366f1', shape: 'arrowDown', text: 'NOW' }]);
        } catch {}
      }

      chart.timeScale().fitContent();

      const handleResize = () => {
        if (el && chart) chart.applyOptions({ width: el.clientWidth });
      };
      window.addEventListener('resize', handleResize);
      // Store for cleanup
      (chart as any)._handleResize = handleResize;
    };
    create();
    return () => {
      try { if (chart) { window.removeEventListener('resize', (chart as any)._handleResize); chart.remove(); } } catch {}
    };
  }, [JSON.stringify(candles.slice(-1)), activeTf, forecast?.expected_range?.low, forecast?.expected_range?.high, showOverlays.vwap, showOverlays.ema, showOverlays.walls]);

  const freshness = data.freshness;
  const isStale = freshness === 'STALE' || freshness === 'DELAYED';
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="font-semibold">Price Chart & Forecast — {data.symbol} <span className={`text-xs px-2 py-0.5 rounded ml-2 ${freshness==='LIVE'?'bg-green-100 text-green-800': isStale?'bg-amber-100 text-amber-800':'bg-muted'}`}>{freshness || 'LIVE'}</span></h3>
        <div className="flex items-center gap-2 text-xs">
          <label className="flex items-center gap-1 cursor-pointer"><input type="checkbox" checked={showOverlays.vwap} onChange={e=>setShowOverlays(s=>({...s, vwap:e.target.checked}))} /> VWAP</label>
          <label className="flex items-center gap-1 cursor-pointer"><input type="checkbox" checked={showOverlays.ema} onChange={e=>setShowOverlays(s=>({...s, ema:e.target.checked}))} /> EMA</label>
          <label className="flex items-center gap-1 cursor-pointer"><input type="checkbox" checked={showOverlays.walls} onChange={e=>setShowOverlays(s=>({...s, walls:e.target.checked}))} /> Call/Put Walls</label>
        </div>
      </div>

      <div ref={containerRef} className="w-full rounded border border-border overflow-hidden bg-[#0b1220]" />

      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground mt-2">
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 bg-green-500"/> Historical candles — solid / actual</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 border border-dashed border-indigo-500"/> Forecast — distinct dashed / translucent (PREDICTED)</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 bg-indigo-300/60"/> Confidence range — translucent</span>
      </div>

      {forecast && (
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <div className="bg-muted rounded p-2"><div className="text-muted-foreground">Direction (PREDICTED)</div><div>↑ {(forecast.direction.up*100).toFixed(0)}% • → {(forecast.direction.sideways*100).toFixed(0)}% • ↓ {(forecast.direction.down*100).toFixed(0)}%</div></div>
          <div className="bg-muted rounded p-2"><div className="text-muted-foreground">Horizon</div><div>{forecast.horizon_minutes} min • {activeTf}</div></div>
          <div className="bg-muted rounded p-2"><div className="text-muted-foreground">Expected range (PREDICTED)</div><div>{forecast.expected_range.low.toFixed(2)} – {forecast.expected_range.high.toFixed(2)}</div><div className="text-[10px]">Median ± {forecast.expected_move_percent.toFixed(2)}%</div></div>
          <div className="bg-muted rounded p-2"><div className="text-muted-foreground">Confidence</div><div className={`font-semibold ${forecast.confidence==='HIGH'?'text-green-600':forecast.confidence==='MODERATE'?'text-amber-600':'text-muted-foreground'}`}>{forecast.confidence}</div><div className="text-[10px]">Generated {new Date(data.generated_at).toLocaleTimeString()} • Data age {data.data_age_seconds}s</div></div>
        </div>
      )}

      {isStale && <p className="text-xs text-amber-600 mt-2">Forecast status: STALE — data is {data.data_age_seconds}s old, not presented as current.</p>}
      <p className="text-xs text-muted-foreground mt-2">Forecast is probabilistic decision support — not guaranteed. Never presented as actual completed candle.</p>
    </div>
  );
}
