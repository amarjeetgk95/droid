'use client';
import React from 'react';
import { Radio, TrendingUp, Landmark, Bitcoin } from 'lucide-react';
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
  { id: 'fyers', name: 'Fyers API v3', badge: 'Low Latency', desc: 'Official REST & WebSocket Gateway', apiType: 'indian', icon: TrendingUp, portalUrl: '' },
  { id: 'flattrade', name: 'Flattrade PiConnect', badge: 'Zero Brokerage', desc: 'WallConnect API & Realtime Feed', apiType: 'indian', icon: Landmark, portalUrl: '' },
];
const CRYPTO_PROVIDERS: ProviderCard[] = [
  { id: 'binance', name: 'Binance API', badge: 'Crypto & Spot', desc: 'Public Spot & Futures Gateway', apiType: 'crypto', icon: Bitcoin, portalUrl: '' },
];

interface Props {
  settings: BrokerSettings;
  onChange: (updates: Partial<BrokerSettings>) => void;
}

export function ProviderGrid({ settings, onChange }: Props) {
  const visibleProviders = settings.apiType === 'crypto' ? CRYPTO_PROVIDERS : INDIAN_PROVIDERS;
  const handleProviderSelect = (providerId: BrokerProviderId) => onChange({ provider: providerId });

  return (
    <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
      <div>
        <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
          <Radio className="w-4 h-4 text-primary" />
          {settings.apiType === 'crypto' ? 'Crypto Gateway' : 'Active Indian Broker'}
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          {settings.apiType === 'crypto'
            ? 'Binance provides real-time spot and futures market data.'
            : 'Select your active broker. All API credentials and secret keys are securely stored on your Render backend.'}
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {visibleProviders.map((p) => {
          const isSelected = settings.provider === p.id;
          const Icon = p.icon;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => handleProviderSelect(p.id)}
              className={`flex flex-col text-left p-4 rounded-xl border transition-all cursor-pointer ${isSelected ? 'border-primary bg-primary/10 ring-2 ring-primary/20' : 'border-border bg-card hover:bg-secondary/40'}`}
            >
              <div className="flex items-center justify-between w-full">
                <span className="font-semibold text-sm text-foreground flex items-center gap-2">
                  <Icon className="w-4 h-4 text-primary" />
                  {p.name}
                </span>
                <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${isSelected ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'}`}>
                  {isSelected ? 'ACTIVE' : p.badge}
                </span>
              </div>
              <span className="text-xs text-muted-foreground mt-2">{p.desc}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
