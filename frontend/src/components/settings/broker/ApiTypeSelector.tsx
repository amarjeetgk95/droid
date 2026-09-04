'use client';

import React from 'react';
import { Landmark, Bitcoin } from 'lucide-react';
import type { BrokerSettings, ApiType, BrokerProviderId } from '@/lib/settings';

interface Props {
  settings: BrokerSettings;
  onChange: (updates: Partial<BrokerSettings>) => void;
}

export function ApiTypeSelector({ settings, onChange }: Props) {
  const handleApiTypeChange = (next: ApiType) => {
    const defaultProvider: BrokerProviderId = next === 'crypto' ? 'binance' : 'fyers';
    onChange({ apiType: next, provider: defaultProvider });
  };

  const options = [
    {
      id: 'indian' as ApiType,
      name: 'Indian Market (NSE / BSE)',
      desc: 'Equity, Options & Futures via FYERS API v3 or Flattrade PiConnect (INR)',
      icon: Landmark,
    },
    {
      id: 'crypto' as ApiType,
      name: 'Crypto Market (Binance)',
      desc: 'Real-time Spot & Futures order book data (USDT quoted)',
      icon: Bitcoin,
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-5">
      {options.map((t) => {
        const isSelected = settings.apiType === t.id;
        const Icon = t.icon;
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => handleApiTypeChange(t.id)}
            className={`flex items-start gap-3.5 text-left p-4 rounded-lg border transition-all cursor-pointer ${
              isSelected
                ? 'border-foreground/30 bg-secondary/50 shadow-2xs'
                : 'border-border/60 bg-card hover:bg-secondary/30'
            }`}
          >
            <div
              className={`p-2 rounded-md shrink-0 transition-colors ${
                isSelected
                  ? 'bg-foreground text-background'
                  : 'bg-secondary text-muted-foreground'
              }`}
            >
              <Icon className="w-4 h-4" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-foreground">{t.name}</span>
                {isSelected && (
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-foreground/10 text-foreground font-medium">
                    Active
                  </span>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground mt-1 leading-normal">{t.desc}</p>
            </div>
          </button>
        );
      })}
    </div>
  );
}
