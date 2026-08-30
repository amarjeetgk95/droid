'use client';
export function MultiTimeframePanel({ data }: { data: any }) {
  const mtf = data?.multi_timeframe?.alignment;
  const full = data?.multi_timeframe;
  if (!mtf) return null;
  const unavailable: string[] = data?.unavailable_timeframes || full?.unavailable_timeframes || [];
  const tfOrder = ['1m','5m','15m','1h','4h','1D'];
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">Multi-Timeframe Alignment (6-TF Chart Analysis)</h3>
      <p className="text-xs text-muted-foreground mb-2">Timeframes: 1m • 5m • 15m • 1h • 4h • 1D — Higher TFs = context, Lower TFs = entry timing. Fixed universe: NIFTY/BANKNIFTY/FINNIFTY/SENSEX/BTC/ETH/SOL only.</p>
      <div className="flex gap-2 mb-2 flex-wrap">
        {tfOrder.map((tf) => {
          const bias = (mtf.biases as any)?.[tf];
          if (!bias) {
            const isNA = unavailable.includes(tf);
            return <span key={tf} className={`px-2 py-1 rounded text-xs ${isNA ? 'bg-gray-100 text-gray-500 border border-dashed' : 'bg-muted text-muted-foreground'}`}>{tf} {isNA ? 'Data unavailable' : '—'}</span>;
          }
          return <span key={tf} className={`px-2 py-1 rounded text-xs ${bias==='BULLISH'?'bg-green-100 text-green-800':bias==='BEARISH'?'bg-red-100 text-red-800':'bg-yellow-100 text-yellow-800'}`}>{tf} {bias==='BULLISH'?'🟢':bias==='BEARISH'?'🔴':'🟡'} {bias}</span>;
        })}
      </div>
      <p className="text-sm">Overall Bias: <b>{mtf.overall_bias}</b> • Alignment: {mtf.alignment_count} • {mtf.cross_timeframe_status || (mtf.conflict ? 'Mixed signals' : 'Aligned')} {mtf.mixed_low_confidence && <span className="text-amber-600">• Mixed / Low Confidence</span>}</p>
      <p className="text-xs text-muted-foreground mt-1">{mtf.interpretation}</p>
      {mtf.short_term_reversal_against_htf && <p className="text-xs text-amber-700 mt-1">⚠ Short-term reversal against higher-TF trend — use higher TF for context, lower TF for timing only.</p>}
      {mtf.trend_continuation && <p className="text-xs text-green-700 mt-1">✓ Trend continuation — aligned across TFs.</p>}
      {mtf.possible_regime_change && <p className="text-xs text-amber-700 mt-1">⚠ Possible regime change — mixed HTF/LTF signals.</p>}
      <p className="text-xs mt-1">Dominant: {mtf.dominant_timeframe ?? '—'} • Alignment score {mtf.alignment_score} {unavailable.length>0 && `• Unavailable: ${unavailable.join(', ')} — no substitution`}</p>
      {full?.confidence && <p className="text-xs text-muted-foreground mt-1">MTF Confidence: {full.confidence} ({full.confidence_score}) • {full.signal_quality_note || ''}</p>}
    </div>
  );
}
