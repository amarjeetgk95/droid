'use client';

import React from 'react';
import Link from 'next/link';
import { Activity } from 'lucide-react';
import {
  BrokerConnectionPanel,
  TelegramIntegration,
  AIProviderManager,
  AIDriftMonitor,
  SystemMetricsPanel,
  CacheManager,
} from '@/components/system-nerve';

export default function SystemNervePage() {
  return (
    <div className="ds-page">
      <header className="page-hero">
        <div className="toolbar">
          <div>
            <div className="flex items-center gap-2.5">
              <Activity className="w-4 h-4 text-[var(--ds-ink-3)]" aria-hidden="true" />
              <h1>System Nerve</h1>
            </div>
            <p>
              Operational truth only: broker session, notification dispatch, AI governance, drift
              and cache telemetry
            </p>
          </div>
          <span className="spacer" />
          <Link href="/settings" className="btn">
            Open Settings
          </Link>
        </div>
      </header>

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
