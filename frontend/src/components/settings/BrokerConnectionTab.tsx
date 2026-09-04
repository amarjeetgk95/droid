'use client';

import React from 'react';
import { Globe, ExternalLink, Info, Key } from 'lucide-react';
import type { BrokerSettings, AppSettings } from '@/lib/settings';
import { ApiTypeSelector } from './broker/ApiTypeSelector';
import { ProviderGrid } from './broker/ProviderGrid';
import { RenderIntegrationCard } from './broker/RenderIntegrationCard';
import { TelemetryCard } from './broker/TelemetryCard';
import { AdvancedDrawer } from './broker/AdvancedDrawer';
import { SettingSection } from './ui/SettingPrimitives';

interface Props {
  settings: BrokerSettings;
  fullSettings?: AppSettings;
  onChange: (updated: Partial<BrokerSettings>) => void;
  errors?: { path: string; message: string }[];
}

export function BrokerConnectionTab({ settings, fullSettings, onChange }: Props) {
  return (
    <div className="space-y-6">
      {/* 1. Market Universe & Active Broker */}
      <SettingSection
        title="Market Universe &amp; Active Broker"
        description="Select market universe and active execution broker. Credentials are securely held on Render."
        icon={Globe}
      >
        <ApiTypeSelector settings={settings} onChange={onChange} />
        <ProviderGrid settings={settings} onChange={onChange} />
      </SettingSection>

      {/* 2. Backend Integration & OAuth */}
      <RenderIntegrationCard settings={settings} />

      {/* 3. Binance Public Gateway note (if crypto) */}
      {settings.provider === 'binance' && (
        <SettingSection
          title="Binance Spot &amp; Futures Gateway"
          description="Public streaming feeds for crypto spot prices, order book depth, and funding rates."
          icon={Key}
          action={
            <a
              href="https://www.binance.com/en/my/settings/api-management"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 transition-colors"
            >
              <span>Binance Portal</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          }
        >
          <div className="p-5 flex items-start gap-2.5 text-xs text-muted-foreground">
            <Info className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
            <p className="leading-relaxed">
              Binance real-time Spot &amp; Futures tickers, depth streams, and funding rates connect with zero authentication required. Custom API key credentials are optional for private execution endpoints.
            </p>
          </div>
        </SettingSection>
      )}

      {/* 4. Live Telemetry & Health */}
      <TelemetryCard settings={settings} fullSettings={fullSettings} />

      {/* 5. Custom Credentials Override */}
      <AdvancedDrawer settings={settings} onChange={onChange} />
    </div>
  );
}
