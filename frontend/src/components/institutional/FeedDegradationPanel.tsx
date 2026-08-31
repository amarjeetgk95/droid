'use client';

export function FeedDegradationPanel({ instrument, health }: { instrument: string; health: { health: string; reason?: string | null; anomaly?: string | null } }) {
  if (health.health !== 'FEED_DEGRADED') return null;
  return (
    <div className="bg-amber-50 border border-amber-300 rounded p-4 space-y-1" data-testid="feed-degradation-panel">
      <h4 className="font-bold text-sm">{instrument}</h4>
      <p className="text-sm text-amber-800">⚠ FEED DEGRADED</p>
      <p className="text-xs text-muted-foreground">Sequence integrity failure detected.</p>
      <p className="text-xs">Reason: {health.reason || health.anomaly || 'unknown'}</p>
      <ul className="text-xs list-disc pl-4">
        <li>New breakout signals: DISABLED</li>
        <li>AI confirmation: DISABLED</li>
        <li>Execution: DISABLED</li>
      </ul>
      <p className="text-xs font-medium">Status: Waiting for clean resynchronization</p>
    </div>
  );
}
