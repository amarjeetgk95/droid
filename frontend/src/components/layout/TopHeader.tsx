import { useEffect, useState } from 'react';
import { MarketHealthStatus, MarketStatusResponse } from '@/lib/types';
import { UserProfileMenu } from '../auth/UserProfileMenu';
import { useMarketStream } from '@/hooks/useMarketStream';
import { MarketHealthModal } from '../dashboard/MarketHealthModal';
import { Activity } from 'lucide-react';

export function TopHeader({ health, marketStatus }: { health: MarketHealthStatus | null; marketStatus: MarketStatusResponse | null }) {
  const { streamState } = useMarketStream();
  const [showHealthModal, setShowHealthModal] = useState(false);

  const [time, setTime] = useState<string>(() => {
    return new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' });
  });

  useEffect(() => {
    const interval = setInterval(() => {
      setTime(new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' }));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <>
      <header className="h-16 border-b border-border bg-card flex items-center justify-between px-4">
        <div className="flex items-center gap-4">
          <span className="text-sm font-medium tabular-nums">{time} IST</span>
          {marketStatus && (
            <span className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded font-medium">
              {marketStatus.session.replace('_', ' ')}
            </span>
          )}
          <div className="flex items-center gap-2 text-xs">
            <span className="px-2 py-1 rounded font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30">
              {health?.mode === 'DEMO' ? 'DEMO DATA' : 'LIVE'}
            </span>
            
            {/* Realtime Stream Badge */}
            <div className="flex items-center gap-1 px-2 py-1 rounded bg-secondary text-[11px] font-medium border border-border">
              <span className={`w-2 h-2 rounded-full ${streamState === 'CONNECTED' ? 'bg-success animate-pulse' : 'bg-warning'}`} />
              <span className="text-muted-foreground">{streamState}</span>
            </div>

            <button
              onClick={() => setShowHealthModal(true)}
              className="flex items-center gap-1 px-2 py-1 rounded bg-secondary hover:bg-secondary/80 text-[11px] font-medium text-muted-foreground hover:text-foreground border border-border transition-colors cursor-pointer"
              title="View Ingestion Diagnostics"
            >
              <Activity className="w-3 h-3 text-primary" />
              <span>Telemetry</span>
            </button>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <UserProfileMenu />
        </div>
      </header>

      <MarketHealthModal
        isOpen={showHealthModal}
        onClose={() => setShowHealthModal(false)}
        health={health}
        streamState={streamState}
      />
    </>
  );
}
