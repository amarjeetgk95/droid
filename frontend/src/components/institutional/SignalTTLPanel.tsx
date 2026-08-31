'use client';

export function SignalTTLPanel({ signal }: { signal: { created_at_utc: number; expires_at_utc: number; ttl_ms: number; fsm_state: string; is_expired?: boolean; error?: string | null } | null }) {
  if (!signal) return null;
  const fmt = (ms: number) => new Date(ms).toISOString().substring(11, 23) + ' UTC';
  const remaining = Math.max(0, signal.expires_at_utc - Date.now());
  const expired = signal.is_expired || Date.now() > signal.expires_at_utc;
  if (expired) {
    return (
      <div className="bg-card border border-red-200 rounded p-4 space-y-1" data-testid="signal-ttl-panel">
        <h4 className="font-bold text-sm text-red-600">SIGNAL EXPIRED</h4>
        <p className="text-xs">Reason: {signal.error || 'TTL exceeded before execution.'}</p>
        <p className="text-xs">Order submitted: NO</p>
        <p className="text-[11px] text-muted-foreground">Created: {fmt(signal.created_at_utc)} • Expires: {fmt(signal.expires_at_utc)}</p>
      </div>
    );
  }
  return (
    <div className="bg-card border rounded p-4 space-y-2" data-testid="signal-ttl-panel">
      <h4 className="font-bold text-xs tracking-widest">SIGNAL</h4>
      <div className="text-xs space-y-1 font-mono">
        <div>Created: {fmt(signal.created_at_utc)}</div>
        <div>TTL: {(signal.ttl_ms / 1000).toFixed(1)} sec ({remaining} ms remaining)</div>
        <div>Expires: {fmt(signal.expires_at_utc)}</div>
        <div className="flex gap-2 mt-2">
          <span className="px-1.5 py-0.5 bg-secondary rounded text-[11px]">FSM: {signal.fsm_state}</span>
          <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded text-[11px]">Freshness: VALID</span>
        </div>
      </div>
    </div>
  );
}
