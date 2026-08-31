'use client';

export function ExplainabilityPanel({ ctx }: { ctx: { supporting_evidence?: { signal: string }[]; conflicting_evidence?: { signal: string }[]; scores?: any; technical?: any; levels?: any; ai?: any; risk?: any } | null }) {
  if (!ctx) return null;
  return (
    <div className="bg-card border rounded p-4 space-y-2 text-xs" data-testid="explainability-panel">
      <h4 className="font-bold text-sm">Explainability</h4>
      <div>Supporting: {(ctx.supporting_evidence || []).map(e => e.signal).join(', ') || '—'}</div>
      <div>Conflicts: {(ctx.conflicting_evidence || []).map(e => e.signal).join(', ') || '—'}</div>
      <div>Key levels: {JSON.stringify(ctx.levels || {})}</div>
      <div>Regime: {ctx.technical?.regime || '—'} | Scores: B{ctx.scores?.bullish_score}/Be{ctx.scores?.bearish_score}</div>
      <div>AI: {JSON.stringify(ctx.ai || {})}</div>
      <div>Risk: {JSON.stringify(ctx.risk || {})}</div>
    </div>
  );
}
