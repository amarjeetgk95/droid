'use client';

import React, { useState } from 'react';
import { Key, CheckCircle2, AlertCircle, Eye, EyeOff, ExternalLink } from 'lucide-react';
import type { AISettings } from '@/lib/settings';
import { OpenRouterModelSelector } from '../OpenRouterModelSelector';
import { SettingSection, SettingRow } from '../ui/SettingPrimitives';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
  errors?: { path: string; message: string }[];
}

export function OpenRouterPanel({ settings, onChange, errors = [] }: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `ai.${field}`)?.message;
  const [showKey, setShowKey] = useState(false);

  return (
    <SettingSection
      title="OpenRouter Dynamic Gateway"
      description="Connect to thousands of open-source & frontier models via unified API keys."
      icon={Key}
      action={
        <a
          href="https://openrouter.ai/keys"
          target="_blank"
          rel="noreferrer"
          className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 transition-colors"
        >
          <span>Get API Key</span>
          <ExternalLink className="w-3 h-3" />
        </a>
      }
    >
      <SettingRow
        label="OpenRouter API Key"
        description="Stored securely in browser localStorage and synced to your encrypted profile."
        error={getError('openRouterApiKey')}
      >
        <div className="w-full max-w-sm space-y-1.5">
          <div className="relative">
            <input
              type={showKey ? 'text' : 'password'}
              placeholder="sk-or-v1-..."
              value={settings.openRouterApiKey}
              onChange={(e) => onChange({ openRouterApiKey: e.target.value })}
              className="w-full bg-secondary/40 border border-border/70 rounded-md px-3 py-1.5 pr-9 text-xs font-mono text-foreground placeholder:text-muted-foreground/60 transition-colors focus:outline-hidden focus:border-ring focus:ring-1 focus:ring-ring"
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
            >
              {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            </button>
          </div>

          <div className="text-[11px] flex items-center gap-1.5">
            {settings.openRouterApiKey ? (
              <span className="text-emerald-600 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                <span>API key configured</span>
              </span>
            ) : (
              <span className="text-muted-foreground flex items-center gap-1">
                <AlertCircle className="w-3 h-3 text-amber-500" />
                <span>Enter key to unlock model catalog</span>
              </span>
            )}
          </div>
        </div>
      </SettingRow>

      <div className="p-5 border-t border-border/40">
        <OpenRouterModelSelector settings={settings} onChange={onChange} />
      </div>
    </SettingSection>
  );
}
