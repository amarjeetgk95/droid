'use client';

import React from 'react';
import { Cloud, Network, Server, Check } from 'lucide-react';
import type { AISettings, AIConnectionMode } from '@/lib/settings';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
}

export function ConnectionModeSelector({ settings, onChange }: Props) {
  const connectionMode: AIConnectionMode =
    (settings as unknown as { connectionMode: AIConnectionMode }).connectionMode ||
    (settings.provider === 'openrouter' ? 'OpenRouter' : settings.provider === 'ollama' ? 'Local Ollama' : 'OpenRouter');

  const handleConnectionMode = (mode: AIConnectionMode) => {
    const legacyMap: Record<AIConnectionMode, AISettings['provider']> = {
      OpenRouter: 'openrouter',
      'Direct Provider': 'openai',
      'Local Ollama': 'ollama',
    } as unknown as Record<AIConnectionMode, AISettings['provider']>;
    onChange({ connectionMode: mode, provider: legacyMap[mode] || 'openrouter' } as unknown as Partial<AISettings>);
  };

  const modes = [
    {
      id: 'OpenRouter' as AIConnectionMode,
      name: 'OpenRouter Gateway',
      icon: Cloud,
      badge: 'Unified',
      desc: 'Unified catalog, automatic model fallbacks, free-only verified models',
    },
    {
      id: 'Direct Provider' as AIConnectionMode,
      name: 'Direct Provider',
      icon: Network,
      badge: 'Native',
      desc: 'Direct API endpoints for OpenAI, Novita, NVIDIA, Gemini, or custom proxy',
    },
    {
      id: 'Local Ollama' as AIConnectionMode,
      name: 'Local Ollama',
      icon: Server,
      badge: 'Private',
      desc: '100% on-device private inference via localhost:11434 with zero cloud dependencies',
    },
  ];

  return (
    <div className="p-5">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {modes.map((m) => {
          const Icon = m.icon;
          const selected = connectionMode === m.id;
          return (
            <button
              key={m.id}
              type="button"
              onClick={() => handleConnectionMode(m.id)}
              className={`flex flex-col text-left p-4 rounded-lg border transition-all cursor-pointer ${
                selected
                  ? 'border-foreground/30 bg-secondary/50 shadow-2xs'
                  : 'border-border/60 bg-card hover:bg-secondary/30'
              }`}
            >
              <div className="flex items-center justify-between w-full">
                <span className="flex items-center gap-2 font-medium text-xs text-foreground">
                  <Icon className="w-3.5 h-3.5 text-muted-foreground" />
                  {m.name}
                </span>
                {selected ? (
                  <Check className="w-3.5 h-3.5 text-foreground shrink-0" />
                ) : (
                  <span className="text-[10px] font-mono text-muted-foreground px-1 py-0.5 rounded bg-secondary">
                    {m.badge}
                  </span>
                )}
              </div>
              <span className="text-[11px] text-muted-foreground mt-2 leading-relaxed">
                {m.desc}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
