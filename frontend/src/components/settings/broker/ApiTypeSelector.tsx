'use client';
import React from 'react';
import { Globe, Landmark, Bitcoin } from 'lucide-react';
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

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-sm">
      <div>
        <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
          <Globe className="w-4 h-4 text-primary" />
          Market Universe
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          Choose your market universe. Indian markets operate via FYERS API v3 or Flattrade PiConnect; Crypto operates via Binance.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {[
          { id: 'indian' as ApiType, name: 'Indian Market (NSE/BSE)', desc: 'FYERS API v3 & Flattrade PiConnect (INR)', icon: Landmark },
          { id: 'crypto' as ApiType, name: 'Crypto Market (Binance)', desc: 'Spot & Futures pairs on Binance (USDT-quoted)', icon: Bitcoin },
        ].map((t) => {
          const isSelected = settings.apiType === t.id;
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => handleApiTypeChange(t.id)}
              className={`flex items-center gap-3 text-left p-4 rounded-xl border transition-all cursor-pointer ${isSelected ? 'border-primary bg-primary/10 ring-2 ring-primary/20' : 'border-border bg-card hover:bg-secondary/40'}`}
            >
              <div className={`p-2 rounded-lg ${isSelected ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'}`}>
                <Icon className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-foreground">{t.name}</div>
                <div className="text-[11px] text-muted-foreground">{t.desc}</div>
              </div>
              <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>
                {isSelected ? 'ACTIVE' : 'SELECT'}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
