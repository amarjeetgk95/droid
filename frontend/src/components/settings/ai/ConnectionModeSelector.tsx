'use client';
import React from 'react';
import { Brain, Cloud, Network, Server } from 'lucide-react';
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

  return (
    <div>
      <label className="text-xs font-semibold text-foreground block mb-2">Connection Mode</label>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { id: 'OpenRouter' as AIConnectionMode, name: 'OpenRouter', icon: Cloud, badge: 'Gateway', desc: 'Unified gateway · dynamic catalog · free-only enforced' },
          { id: 'Direct Provider' as AIConnectionMode, name: 'Direct Provider', icon: Network, badge: '5 Adapters', desc: 'OpenAI · Novita · NVIDIA · Gemini · Custom' },
          { id: 'Local Ollama' as AIConnectionMode, name: 'Local Ollama', icon: Server, badge: '100% Private', desc: 'http://localhost:11434 · no cloud key' },
        ].map((m) => {
          const Icon = m.icon;
          const selected = connectionMode === m.id;
          return (
            <button
              key={m.id}
              type="button"
              onClick={() => handleConnectionMode(m.id)}
              className={`flex flex-col text-left p-3.5 rounded-xl border transition-all cursor-pointer ${selected ? 'border-primary bg-primary/10 ring-2 ring-primary/20' : 'border-border bg-card hover:bg-secondary/40'}`}
            >
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 font-semibold text-xs text-foreground"><Icon className="w-3.5 h-3.5" /> {m.name}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${selected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>{m.badge}</span>
              </div>
              <span className="text-[11px] text-muted-foreground mt-2">{m.desc}</span>
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-muted-foreground mt-2">
        Selected: <span className="font-mono font-semibold text-foreground">{connectionMode}</span> — quantitative engine is provider-independent.
      </p>
    </div>
  );
}
