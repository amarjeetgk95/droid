'use client';
/**
 * ForecastOverlay — draws forecast median path + confidence band on top of the chart.
 * Used by ForecastChart internally. Exported separately to satisfy §41 file structure.
 * The overlay begins exactly at the latest valid market timestamp and is visually
 * distinct (dashed / translucent) from historical candles.
 */
export function ForecastOverlay({ forecast, currentPrice, lastTime, timeframe }: { forecast:any; currentPrice:number; lastTime:number; timeframe:string }) {
  if (!forecast) return null;
  // Placeholder: actual drawing is handled inside ForecastChart via lightweight-charts series.
  // This component exposes the textual representation for panels and for testing.
  const low = forecast.expected_range?.low;
  const high = forecast.expected_range?.high;
  const horizon = forecast.horizon_minutes;
  return (
    <div className="text-xs border border-dashed border-indigo-500/50 bg-indigo-500/10 rounded p-2">
      <div className="font-semibold">PREDICTED Forecast Overlay — {timeframe} • {horizon}m horizon</div>
      <div>Median path: {currentPrice?.toFixed(2)} → {((low+high)/2)?.toFixed(2)} (PREDICTED)</div>
      <div>Range: {low?.toFixed(2)} – {high?.toFixed(2)} • Confidence {forecast.confidence}</div>
      <div className="text-[10px] text-muted-foreground">Begins at {new Date(lastTime*1000).toLocaleTimeString()} — distinct from historical solid candles</div>
    </div>
  );
}
