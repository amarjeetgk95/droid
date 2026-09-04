'use client';

import React, { memo, useCallback, useMemo } from 'react';
import { TrendingUp, Landmark, Bitcoin, Check } from 'lucide-react';
import type { BrokerSettings, ApiType, BrokerProviderId } from '@/lib/settings';

type ProviderCard = {
  id: BrokerProviderId;
  name: string;
  badge: string;
  desc: string;
  apiType: ApiType;
  icon: React.ComponentType<{ className?: string }>;
};

const INDIAN_PROVIDERS: ProviderCard[] = [
  {
    id: 'fyers',
    name: 'Fyers API v3',
    badge: 'Low Latency',
    desc: 'Official REST & WebSocket Gateway with tick-level data',
    apiType: 'indian',
    icon: TrendingUp,
  },
  {
    id: 'flattrade',
    name: 'Flattrade PiConnect',
    badge: 'Zero Brokerage',
    desc: 'WallConnect API with real-time websocket feed',
    apiType: 'indian',
    icon: Landmark,
  },
];

const CRYPTO_PROVIDERS: ProviderCard[] = [
  {
    id: 'binance',
    name: 'Binance Gateway',
    badge: 'Public Feed',
    desc: 'Direct Spot & USDT-M Futures market data stream',
    apiType: 'crypto',
    icon: Bitcoin,
  },
];

interface Props {
  settings: BrokerSettings;
  onChange: (updates: Partial<BrokerSettings>) => void;
}

export const ProviderGrid = memo(function ProviderGrid({ settings, onChange }: Props) {
  const visibleProviders = useMemo(
    () => (settings.apiType === 'crypto' ? CRYPTO_PROVIDERS : INDIAN_PROVIDERS),
    [settings.apiType]
  );
  const handleProviderSelect = useCallback(
    (providerId: BrokerProviderId) => onChange({ provider: providerId }),
    [onChange]
  );

  return (
    <div className="p-5 pt-0">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {visibleProviders.map((p) => {
          const isSelected = settings.provider === p.id;
          const Icon = p.icon;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => handleProviderSelect(p.id)}
              className={`flex items-start justify-between text-left p-4 rounded-lg border transition-all cursor-pointer ${
                isSelected
                  ? 'border-primary bg-primary/5 ring-1 ring-primary/20'
                  : 'border-border/60 bg-card hover:bg-secondary/30'
              }`}
            >
              <div className="flex items-start gap-3">
                <div
                  className={`p-2 rounded-md shrink-0 ${
                    isSelected ? 'bg-primary/10 text-primary' : 'bg-secondary text-muted-foreground'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-foreground">{p.name}</span>
                    <span className="text-[10px] px-1.5 py-0.2 rounded font-mono text-muted-foreground bg-secondary">
                      {p.badge}
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-1 leading-normal">{p.desc}</p>
                </div>
              </div>
              {isSelected && (
                <div className="shrink-0 text-primary">
                  <Check className="w-4 h-4" />
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
});
