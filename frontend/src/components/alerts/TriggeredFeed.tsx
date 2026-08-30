'use client';

import { AlertTriggerLog } from '@/lib/types';
import { History, BellRing } from 'lucide-react';

export function TriggeredFeed({
  history,
}: {
  history: AlertTriggerLog[];
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">
            Triggered Notifications Audit Feed ({history.length})
          </h3>
        </div>
        <span className="text-xs text-muted-foreground font-mono">Live Dispatch Stream</span>
      </div>

      {history.length === 0 ? (
        <div className="p-8 text-center bg-secondary/30 rounded-lg border border-border text-muted-foreground text-xs">
          No alert trigger events logged in this session.
        </div>
      ) : (
        <div className="space-y-2 font-mono">
          {history.map((h) => (
            <div
              key={h.id}
              className="bg-secondary/30 p-2.5 rounded-lg border border-border flex items-center justify-between gap-3 text-xs"
            >
              <div className="flex items-start gap-2.5">
                <BellRing className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <span className="font-sans font-bold text-foreground text-xs">{h.alert_name}</span>
                  <p className="text-muted-foreground text-[11px] font-sans leading-relaxed">{h.message}</p>
                </div>
              </div>

              <div className="shrink-0 text-right space-y-0.5">
                <span className="text-[10px] text-muted-foreground block">
                  {new Date(h.timestamp).toLocaleTimeString('en-IN')}
                </span>
                <span className="text-[9px] px-1.5 py-0.5 rounded font-bold bg-primary/20 text-primary border border-primary/30 font-sans">
                  {h.channel_dispatched}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
