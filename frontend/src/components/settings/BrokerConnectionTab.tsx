'use client';

import React from 'react';
import { Globe } from 'lucide-react';
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
    <div className="space-y-4">
      {/* 1. Market Universe & Active Broker */}
      <SettingSection
        title="Market universe & active broker"
        description="Market universe and execution broker. Credentials are held on Render."
        icon={Globe}
      >
        <ApiTypeSelector settings={settings} onChange={onChange} />
        <ProviderGrid settings={settings} onChange={onChange} />
      </SettingSection>

      {/* 2. Backend Integration & OAuth */}
      <RenderIntegrationCard settings={settings} />

      {/* 3. Live Telemetry & Health */}
      <TelemetryCard settings={settings} fullSettings={fullSettings} />

      {/* 5. Custom Credentials Override */}
      <AdvancedDrawer settings={settings} onChange={onChange} />
    </div>
  );
}
