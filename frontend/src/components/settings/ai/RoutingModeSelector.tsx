'use client';

import React from 'react';
import type { AISettings, AIRoutingMode } from '@/lib/settings';
import { SettingRow, SettingSwitch } from '../ui/SettingPrimitives';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
}

export function RoutingModeSelector({ settings, onChange }: Props) {
  const routingMode: AIRoutingMode =
    (settings as unknown as { routingMode: AIRoutingMode }).routingMode || 'Task Optimized';
  const handleRoutingMode = (mode: AIRoutingMode) =>
    onChange({ routingMode: mode } as unknown as Partial<AISettings>);
  const fallbackEnabled = !!(settings as unknown as { fallbackEnabled: boolean }).fallbackEnabled;

  return (
    <>
      <SettingRow
        label="Routing Strategy"
        description="Dynamic dispatch algorithm to select the best model for options structuring and trade validation."
      >
        <div className="flex items-center gap-1 p-0.5 bg-secondary/80 border border-border/60 rounded-md">
          {(['Manual', 'Task Optimized', 'Best Available', 'Cost Optimized'] as AIRoutingMode[]).map(
            (rm) => {
              const active = routingMode === rm;
              return (
                <button
                  key={rm}
                  type="button"
                  onClick={() => handleRoutingMode(rm)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer ${
                    active
                      ? 'bg-card text-foreground shadow-2xs font-semibold'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {rm}
                </button>
              );
            }
          )}
        </div>
      </SettingRow>

      <SettingRow
        label="Automatic Provider Fallback"
        description="If primary cloud inference is unavailable or rate-limited, fall back to local Ollama."
      >
        <SettingSwitch
          checked={fallbackEnabled}
          onChange={(checked) =>
            onChange({ fallbackEnabled: checked } as unknown as Partial<AISettings>)
          }
          aria-label="Automatic provider fallback"
        />
      </SettingRow>
    </>
  );
}
