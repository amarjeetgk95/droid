'use client';

import React from 'react';
import type { BrokerSettings, AppSettings } from '@/lib/settings';
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
    <div className="space-y-4">
      {/* 1. Execution Gateway & Session OAuth */}
      <RenderIntegrationCard settings={settings} />

      {/* 2. Live Telemetry & Health */}
      <TelemetryCard settings={settings} fullSettings={fullSettings} />

      {/* 3. Custom Credentials Override */}
      <AdvancedDrawer settings={settings} onChange={onChange} />
    </div>
  );
}
