// @vitest-environment happy-dom
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const { redirectMock } = vi.hoisted(() => ({
  redirectMock: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  redirect: (url: string) => redirectMock(url),
}));

vi.mock('@/components/system-nerve', () => ({
  BrokerConnectionPanel: () => <div data-testid="panel-broker">BrokerConnectionPanel</div>,
  TelegramIntegration: () => <div data-testid="panel-telegram">TelegramIntegration</div>,
  AIProviderManager: () => <div data-testid="panel-ai-provider">AIProviderManager</div>,
  AIDriftMonitor: () => <div data-testid="panel-ai-drift">AIDriftMonitor</div>,
  SystemMetricsPanel: () => <div data-testid="panel-system-metrics">SystemMetricsPanel</div>,
  CacheManager: () => <div data-testid="panel-cache">CacheManager</div>,
}));

import { SystemNerveTab } from './SystemNerveTab';
import SystemPage from '@/app/(app)/system/page';

describe('SystemNerveTab', () => {
  it('renders all 6 operational telemetry panels', () => {
    render(<SystemNerveTab />);

    expect(screen.getByRole('heading', { level: 2, name: 'System Nerve' })).toBeTruthy();
    expect(screen.getByTestId('panel-broker')).toBeTruthy();
    expect(screen.getByTestId('panel-telegram')).toBeTruthy();
    expect(screen.getByTestId('panel-ai-provider')).toBeTruthy();
    expect(screen.getByTestId('panel-ai-drift')).toBeTruthy();
    expect(screen.getByTestId('panel-system-metrics')).toBeTruthy();
    expect(screen.getByTestId('panel-cache')).toBeTruthy();
  });
});

describe('SystemPage redirect', () => {
  it('redirects /system directly to /settings?tab=system', () => {
    SystemPage();
    expect(redirectMock).toHaveBeenCalledWith('/settings?tab=system');
  });
});
