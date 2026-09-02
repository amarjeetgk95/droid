'use client';
import React from 'react';
import { Brain } from 'lucide-react';
import type { AISettings, AIConnectionMode } from '@/lib/settings';
import { ConnectionModeSelector } from './ai/ConnectionModeSelector';
import { RoutingModeSelector } from './ai/RoutingModeSelector';
import { TaskRoutingGrid } from './ai/TaskRoutingGrid';
import { OpenRouterPanel } from './ai/OpenRouterPanel';
import { DirectProviderPanel } from './ai/DirectProviderPanel';
import { OllamaPanel } from './ai/OllamaPanel';
import { PersonaControls } from './ai/PersonaControls';
import { LiveVerification } from './ai/LiveVerification';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
  errors?: { path: string; message: string }[];
}

export function AIEngineTab({ settings, onChange, errors = [] }: Props) {
  const connectionMode: AIConnectionMode =
    (settings as unknown as { connectionMode: AIConnectionMode }).connectionMode ||
    (settings.provider === 'openrouter' ? 'OpenRouter' : settings.provider === 'ollama' ? 'Local Ollama' : 'OpenRouter');

  return (
    <div className="space-y-6">
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Brain className="w-4 h-4 text-primary" />
            AI CONFIGURATION
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 font-mono">3 MODES</span>
          </h3>
          <p className="text-xs text-muted-foreground mt-1">Unified quantitative → AI reasoning pipeline. Market data flows through deterministic validators before AI, stale checks, risk, then execution.</p>
        </div>
        <ConnectionModeSelector settings={settings} onChange={onChange} />
        <RoutingModeSelector settings={settings} onChange={onChange} />
      </div>

      <TaskRoutingGrid settings={settings} onChange={onChange} />

      {connectionMode === 'OpenRouter' && <OpenRouterPanel settings={settings} onChange={onChange} errors={errors} />}
      {connectionMode === 'Direct Provider' && <DirectProviderPanel settings={settings} onChange={onChange} />}
      {connectionMode === 'Local Ollama' && <OllamaPanel settings={settings} onChange={onChange} errors={errors} />}

      <PersonaControls settings={settings} onChange={onChange} />
      <LiveVerification settings={settings} />
    </div>
  );
}
