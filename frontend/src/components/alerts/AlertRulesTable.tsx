'use client';

import { AlertRule } from '@/lib/types';
import { Bell, Trash2, Power } from 'lucide-react';

export function AlertRulesTable({
  rules,
  onToggle,
  onDelete,
}: {
  rules: AlertRule[];
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">
            Configured Alert Rules ({rules.length})
          </h3>
        </div>
      </div>

      {rules.length === 0 ? (
        <div className="p-8 text-center bg-secondary/30 rounded-lg border border-border text-muted-foreground text-xs">
          No alert rules configured. Create a rule above to receive automated notifications.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left border-collapse">
            <thead>
              <tr className="border-b border-border text-muted-foreground font-semibold">
                <th className="py-2 px-2">Rule Name</th>
                <th className="py-2 px-2">Symbol</th>
                <th className="py-2 px-2">Metric Type</th>
                <th className="py-2 px-2">Condition</th>
                <th className="py-2 px-2 text-right">Threshold</th>
                <th className="py-2 px-2">Channel</th>
                <th className="py-2 px-2 text-center">Status</th>
                <th className="py-2 px-2 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40 font-mono">
              {rules.map((r) => (
                <tr key={r.id} className="hover:bg-accent/30 transition-colors">
                  <td className="py-2.5 px-2 font-sans font-bold text-foreground">
                    {r.name}
                  </td>
                  <td className="py-2.5 px-2 font-bold text-foreground">
                    {r.symbol}
                  </td>
                  <td className="py-2.5 px-2 font-sans text-muted-foreground text-[11px]">
                    {r.alert_type.replace(/_/g, ' ')}
                  </td>
                  <td className="py-2.5 px-2 font-sans text-muted-foreground text-[11px]">
                    {r.condition.replace(/_/g, ' ')}
                  </td>
                  <td className="py-2.5 px-2 text-right font-bold text-foreground">
                    {r.threshold}
                  </td>
                  <td className="py-2.5 px-2 font-sans">
                    <span className="text-[10px] px-2 py-0.5 rounded font-bold bg-secondary text-foreground border border-border">
                      {r.channel}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 text-center">
                    <button
                      onClick={() => onToggle(r.id)}
                      className={`p-1 rounded transition-colors cursor-pointer ${
                        r.is_active
                          ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                          : 'bg-secondary text-muted-foreground hover:text-foreground'
                      }`}
                      title={r.is_active ? 'Disable Alert' : 'Enable Alert'}
                    >
                      <Power className="w-3.5 h-3.5" />
                    </button>
                  </td>
                  <td className="py-2.5 px-2 text-center">
                    <button
                      onClick={() => onDelete(r.id)}
                      className="p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors cursor-pointer"
                      title="Delete Alert"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
