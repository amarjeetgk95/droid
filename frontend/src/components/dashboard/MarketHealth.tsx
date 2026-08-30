import { MarketHealthStatus } from '@/lib/types';
import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';

export function MarketHealth({ health, loading }: { health: MarketHealthStatus | null; loading: boolean }) {
  if (loading || !health) {
    return <div className="bg-card rounded-lg border border-border p-4 h-32 animate-pulse" />;
  }

  return (
    <div className="bg-card rounded-lg border border-border p-4">
      <h2 className="text-lg font-bold mb-4">System Health</h2>
      <div className="flex items-center gap-4 p-3 border border-border rounded-lg bg-secondary">
        {health.status === 'HEALTHY' ? <CheckCircle2 className="text-success w-8 h-8" /> :
         health.status === 'DEGRADED' ? <AlertTriangle className="text-warning w-8 h-8" /> :
         <XCircle className="text-destructive w-8 h-8" />}
        <div className="flex-1">
          <p className="font-bold flex items-center gap-2">
            {health.status} <span className="text-xs bg-muted px-2 py-0.5 rounded">{health.mode}</span>
          </p>
          <p className="text-sm text-muted-foreground mt-1">Provider: {health.provider} | Latency: {health.mode === 'DEMO' ? 'N/A' : health.latency_ms ? `${health.latency_ms}ms` : 'N/A'}</p>
        </div>
      </div>
    </div>
  );
}
