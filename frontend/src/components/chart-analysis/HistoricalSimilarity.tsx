'use client';
export function HistoricalSimilarity({ data, timeframe='15m' }: { data: any; timeframe?: string }) {
  const hs = data?.historical_similarity?.[timeframe];
  if (!hs) return null;
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">Historical Similarity ({timeframe})</h3>
      <p className="text-sm">Similar patterns: {hs.sample_count}</p>
      <p className="text-sm">Up { (hs.historical_direction_distribution.up*100).toFixed(0)}% • Sideways {(hs.historical_direction_distribution.sideways*100).toFixed(0)}% • Down {(hs.historical_direction_distribution.down*100).toFixed(0)}%</p>
      <p className="text-sm">Median movement: {hs.median_move_pct>0?'+':''}{hs.median_move_pct}% (p10 {hs.percentiles.p10}% / p90 {hs.percentiles.p90}%)</p>
    </div>
  );
}
