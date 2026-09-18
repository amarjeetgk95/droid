'use client';

import React from 'react';
import {
  BrokerConnectionPanel,
  TelegramIntegration,
  AIProviderManager,
  AIDriftMonitor,
  SystemMetricsPanel,
  CacheManager,
} from '@/components/system-nerve';

export function SystemNerveTab() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-[var(--ds-text)]">System Nerve</h2>
        <p className="text-xs text-[var(--ds-muted)]">
          Operational telemetry, broker session, notifications &amp; diagnostics
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <BrokerConnectionPanel />
        <TelegramIntegration />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AIProviderManager />
        <AIDriftMonitor />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SystemMetricsPanel />
        <CacheManager />
      </div>
    </div>
  );
}
