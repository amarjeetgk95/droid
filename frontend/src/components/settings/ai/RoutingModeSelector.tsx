'use client';
import React from 'react';
import type { AISettings, AIRoutingMode } from '@/lib/settings';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
}

export function RoutingModeSelector({ settings, onChange }: Props) {
  const routingMode: AIRoutingMode = (settings as unknown as { routingMode: AIRoutingMode }).routingMode || 'Task Optimized';
  const handleRoutingMode = (mode: AIRoutingMode) => onChange({ routingMode: mode } as unknown as Partial<AISettings>);

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-border/50">
      <div>
        <label className="text-xs font-semibold text-foreground block mb-1">Routing Mode</label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
          {(['Manual', 'Task Optimized', 'Best Available', 'Cost Optimized'] as AIRoutingMode[]).map((rm) => {
            const active = routingMode === rm;
            return (
              <button key={rm} type="button" onClick={() => handleRoutingMode(rm)} className={`px-2 py-2 rounded-lg text-[11px] font-medium border cursor-pointer ${active ? 'bg-primary text-primary-foreground border-primary shadow-xs' : 'bg-card border-border hover:bg-secondary/50'}`}>{rm}</button>
            );
          })}
        </div>
        <p className="text-[11px] text-muted-foreground mt-1">Default: <span className="font-semibold">Task Optimized</span></p>
      </div>
      <div>
        <label className="text-xs font-semibold text-foreground block mb-1">Automatic Provider Fallback</label>
        <label className="flex items-center gap-2 cursor-pointer bg-secondary/30 border border-border rounded-lg px-3 py-2">
          <input type="checkbox" checked={!!(settings as unknown as { fallbackEnabled: boolean }).fallbackEnabled} onChange={(e) => onChange({ fallbackEnabled: e.target.checked } as unknown as Partial<AISettings>)} className="accent-primary" />
          <span className="text-xs text-foreground">{(settings as unknown as { fallbackEnabled: boolean }).fallbackEnabled ? 'Enabled — cloud unavailable → Ollama' : 'OFF — do not silently switch providers (default)'}</span>
        </label>
        <p className="text-[11px] text-muted-foreground mt-1">{(settings as unknown as { fallbackEnabled: boolean }).fallbackEnabled ? 'Requires local Ollama model' : 'Never uses paid fallback while FREE ONLY is enabled.'}</p>
      </div>
    </div>
  );
}
