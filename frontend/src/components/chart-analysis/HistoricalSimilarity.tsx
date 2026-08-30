'use client';
export function HistoricalSimilarity({ data, timeframe='15m' }: { data: any; timeframe?: string }) {
  const hs = data?.historical_similarity?.[timeframe];
  if (!hs) return null;
  const smallSample = hs.sample_count < 80;
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">Historical Similarity ({timeframe}) — sample-aware</h3>
      <p className="text-sm">Sample count: <b>{hs.sample_count}</b> {smallSample && <span className="text-amber-600">— small sample, not reliable as prediction</span>}</p>
      <p className="text-sm">Up { (hs.historical_direction_distribution.up*100).toFixed(0)}% • Sideways {(hs.historical_direction_distribution.sideways*100).toFixed(0)}% • Down {(hs.historical_direction_distribution.down*100).toFixed(0)}%</p>
      <p className="text-sm">Median move: {hs.median_move_pct>0?'+':''}{hs.median_move_pct}% (p10 {hs.percentiles.p10}% / p50 {hs.percentiles.p50}% / p90 {hs.percentiles.p90}%)</p>
      <p className="text-xs text-muted-foreground mt-2">Based on price structure, trend, momentum, volatility, volume, F&amp;O metrics where available, time of day, expiry distance. Historical pattern match is descriptive — not guaranteed.</p>
      {smallSample && <p className="text-xs text-amber-600 mt-1">Sample size is small — avoid treating as reliable forecast. Confidence remains LOW.</p>}
    </div>
  );
}
