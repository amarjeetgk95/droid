'use client';
export function AIAnalysisPanel({ data }: { data: any }) {
  const mtf = data?.multi_timeframe;
  if (!mtf) return null;
  const bias = mtf.alignment?.overall_bias ?? 'NEUTRAL';
  const conf = mtf.confidence ?? 'LOW';
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">AI Analysis</h3>
      <p className="text-sm text-muted-foreground">
        {bias === 'BULLISH' && `Short-term structure is bullish while the ${mtf.alignment.dominant_timeframe} timeframe ${mtf.alignment.interpretation.toLowerCase()} This suggests a potential intraday continuation scenario rather than a confirmed higher-timeframe reversal.`}
        {bias === 'BEARISH' && `Bearish alignment detected across ${mtf.alignment.alignment_count} timeframes. Higher-timeframe context is ${mtf.alignment.interpretation.toLowerCase()}`}
        {bias === 'NEUTRAL' && `Market is in a neutral/mixed state. Timeframe alignment score is ${mtf.alignment.alignment_score}. Consider waiting for clearer confluence before directional positioning.`}
        {" "}Confidence: {conf}. This is a decision-support assessment, not guaranteed prediction.
      </p>
      <p className="text-xs text-muted-foreground mt-2">AI cannot execute trades. Probabilities are statistical estimates — e.g., Bullish probability {((data.forecasts?.['15m']?.direction.up ?? 0.5)*100).toFixed(0)}% (15m).</p>
    </div>
  );
}
