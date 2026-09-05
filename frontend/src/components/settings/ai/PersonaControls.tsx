'use client';

import React from 'react';
import { Sliders } from 'lucide-react';
import type { AISettings } from '@/lib/settings';
import { SettingSection, SettingRow, SettingSelect } from '../ui/SettingPrimitives';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
}

export function PersonaControls({ settings, onChange }: Props) {
  return (
    <SettingSection
      title="Analyst persona & reasoning"
      description="Analytical perspective, sampling temperature, and cache duration."
      icon={Sliders}
    >
      <SettingRow
        label="Analytical Market Persona"
        description="Defines the prompt tone, risk appetite, and strategic focus of generated trade ideas."
      >
        <SettingSelect
          value={settings.persona}
          onChange={(e) => onChange({ persona: e.target.value as AISettings['persona'] })}
        >
          <option value="INSTITUTIONAL">Institutional Derivatives Strategist (FII/DII Focus)</option>
          <option value="MOMENTUM">Breakout Momentum Trader (Trend Following)</option>
          <option value="OPTION_SELLER">Non-Directional Option Seller (Theta / IV Decay)</option>
        </SettingSelect>
      </SettingRow>

      <SettingRow
        label={`Sampling Temperature (${settings.temperature})`}
        description="Controls model randomness: 0.0 is deterministic and quantitative; 0.7 is exploratory."
      >
        <div className="w-full max-w-xs space-y-1">
          <input
            type="range"
            min="0.0"
            max="0.7"
            step="0.05"
            value={settings.temperature}
            onChange={(e) => onChange({ temperature: parseFloat(e.target.value) })}
            className="w-full accent-primary cursor-pointer"
          />
          <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
            <span>0.0 (Deterministic)</span>
            <span>0.7 (Creative)</span>
          </div>
        </div>
      </SettingRow>

      <SettingRow
        label={`Analysis Cache TTL (${settings.cacheTtlSeconds}s)`}
        description="Duration AI market insights remain cached before re-querying the inference engine."
      >
        <div className="w-full max-w-xs space-y-1">
          <input
            type="range"
            min="30"
            max="300"
            step="15"
            value={settings.cacheTtlSeconds}
            onChange={(e) => onChange({ cacheTtlSeconds: parseInt(e.target.value) })}
            className="w-full accent-primary cursor-pointer"
          />
          <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
            <span>30s (Ultra Fresh)</span>
            <span>300s (Cost Saving)</span>
          </div>
        </div>
      </SettingRow>
    </SettingSection>
  );
}
