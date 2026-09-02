'use client';
import React from 'react';
import { Key, ExternalLink, Info } from 'lucide-react';
import type { BrokerSettings, AppSettings } from '@/lib/settings';
import { ApiTypeSelector } from './broker/ApiTypeSelector';
import { ProviderGrid } from './broker/ProviderGrid';
import { RenderIntegrationCard } from './broker/RenderIntegrationCard';
import { TelemetryCard } from './broker/TelemetryCard';
import { AdvancedDrawer } from './broker/AdvancedDrawer';

interface Props {
  settings: BrokerSettings;
  fullSettings?: AppSettings;
  onChange: (updated: Partial<BrokerSettings>) => void;
  errors?: { path: string; message: string }[];
}

export function BrokerConnectionTab({ settings, fullSettings, onChange }: Props) {
  return (
    <div className="space-y-6">
      <ApiTypeSelector settings={settings} onChange={onChange} />
      <ProviderGrid settings={settings} onChange={onChange} />
      <RenderIntegrationCard settings={settings} />
      <TelemetryCard settings={settings} fullSettings={fullSettings} />
      {settings.provider === 'binance' && (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Key className="w-4 h-4 text-primary" />
              Binance Spot &amp; Futures Gateway
            </h3>
            <a href="https://www.binance.com/en/my/settings/api-management" target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline flex items-center gap-1 font-medium">
              <span>Binance Portal</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
          <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg text-xs text-amber-300 flex items-start gap-2">
            <Info className="w-4 h-4 shrink-0 mt-0.5" />
            <div><strong>Public Market Data is Free &amp; Active:</strong> Binance real-time Spot &amp; Futures tickers, Order Books, Candlesticks, and Funding Rates stream directly with zero authentication required.</div>
          </div>
        </div>
      )}
      <AdvancedDrawer settings={settings} onChange={onChange} />
    </div>
  );
}
