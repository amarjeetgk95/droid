'use client';
export function MultiTimeframePanel({ data }: { data: any }) {
  const mtf = data?.multi_timeframe?.alignment;
  if (!mtf) return null;
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">Alignment</h3>
      <div className="flex gap-2 mb-2">
        {Object.entries(mtf.biases).map(([tf, bias]: any) => (
          <span key={tf} className={`px-2 py-1 rounded text-xs ${bias==='BULLISH'?'bg-green-100 text-green-800':bias==='BEARISH'?'bg-red-100 text-red-800':'bg-yellow-100 text-yellow-800'}`}>{tf} {bias==='BULLISH'?'🟢':bias==='BEARISH'?'🔴':'🟡'}</span>
        ))}
      </div>
      <p className="text-sm">Overall Bias: <b>{mtf.overall_bias}</b> • Alignment: {mtf.alignment_count} • {mtf.conflict ? 'Conflict detected' : 'Aligned'}</p>
      <p className="text-xs text-muted-foreground mt-1">{mtf.interpretation}</p>
      <p className="text-xs mt-1">Dominant: {mtf.dominant_timeframe ?? '—'} • Score {mtf.alignment_score}</p>
    </div>
  );
}
