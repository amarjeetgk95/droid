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
import { SettingSection } from './ui/SettingPrimitives';

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
    <div className="space-y-4">
      {/* 1. Inference Gateway & Architecture */}
      <SettingSection
        title="Inference Gateway & Routing"
        description="AI execution runtime and model dispatch policy for strategies and signals."
        icon={Brain}
      >
        <ConnectionModeSelector settings={settings} onChange={onChange} />
        <div className="divide-y divide-[var(--ds-border-subtle)] border-t border-[var(--ds-border-subtle)]">
          <RoutingModeSelector settings={settings} onChange={onChange} />
        </div>
      </SettingSection>

      {/* 2. Provider Credentials & Catalog */}
      {connectionMode === 'OpenRouter' && (
        <OpenRouterPanel settings={settings} onChange={onChange} errors={errors} />
      )}
      {connectionMode === 'Direct Provider' && (
        <DirectProviderPanel settings={settings} onChange={onChange} />
      )}
      {connectionMode === 'Local Ollama' && (
        <OllamaPanel settings={settings} onChange={onChange} errors={errors} />
      )}

      {/* 3. Manual Task Routing (Only when Manual routing mode is active) */}
      {(settings as unknown as { routingMode: string }).routingMode === 'Manual' && (
        <TaskRoutingGrid settings={settings} onChange={onChange} />
      )}

      {/* 4. Persona & Sampling Controls */}
      <PersonaControls settings={settings} onChange={onChange} />

      {/* 5. Live Diagnostics Probe */}
      <LiveVerification settings={settings} />
    </div>
  );
}
