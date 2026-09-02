'use client';
import React from 'react';
import { Sliders } from 'lucide-react';
import type { AISettings } from '@/lib/settings';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
}

export function PersonaControls({ settings, onChange }: Props) {
  return (
    <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
      <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
        <Sliders className="w-4 h-4 text-primary" />
        Analyst Persona & Generation Controls
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
        <div>
          <label className="font-semibold block mb-1">AI Market Persona</label>
          <select value={settings.persona} onChange={(e) => onChange({ persona: e.target.value as AISettings['persona'] })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs focus:outline-hidden">
            <option value="INSTITUTIONAL">Institutional Derivatives Strategist (FII/DII Focus)</option>
            <option value="MOMENTUM">Breakout Momentum Trader (Trend Following)</option>
            <option value="OPTION_SELLER">Non-Directional Option Seller (Theta / IV Decay)</option>
          </select>
        </div>
        <div>
          <label className="font-semibold block mb-1">Sampling Temperature: {settings.temperature}</label>
          <input type="range" min="0.0" max="0.7" step="0.05" value={settings.temperature} onChange={(e) => onChange({ temperature: parseFloat(e.target.value) })} className="w-full accent-primary mt-2 cursor-pointer" />
          <div className="flex justify-between text-[10px] text-muted-foreground mt-1"><span>0.0 (Deterministic)</span><span>0.7 (Creative)</span></div>
        </div>
        <div>
          <label className="font-semibold block mb-1">Analysis Cache TTL: {settings.cacheTtlSeconds}s</label>
          <input type="range" min="30" max="300" step="15" value={settings.cacheTtlSeconds} onChange={(e) => onChange({ cacheTtlSeconds: parseInt(e.target.value) })} className="w-full accent-primary mt-2 cursor-pointer" />
          <div className="flex justify-between text-[10px] text-muted-foreground mt-1"><span>30s (Ultra Fresh)</span><span>300s (Cost Saving)</span></div>
        </div>
      </div>
    </div>
  );
}
