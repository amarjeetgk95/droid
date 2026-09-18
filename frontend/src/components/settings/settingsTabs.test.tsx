// @vitest-environment happy-dom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react';

// vi.mock is hoisted, so the mock object must be built with vi.hoisted.
const { apiMock } = vi.hoisted(() => {
  const telegramStatus = {
    bot_configured: false,
    bot_username: null,
    webhook_configured: false,
    binding: { linked: false, telegram_chat_id: null, linked_at: null, status: 'NONE' },
    environment: 'test',
    queue_stats: {},
  };

  const baseMocks: Record<string, unknown> = {
    getTelegramStatus: async () => telegramStatus,
    getTelegramPreferences: async () => ({
      events: {},
      instruments: {},
      timeframes: {},
      breakout: false,
      breakdown: false,
    }),
    getTelegramAudit: async () => ({ records: [] }),
    getTelegramStats: async () => ({ notification_queue: {} }),
    getPaperPortfolio: async () => ({ data: null }),
  };

  // Any unmocked api method resolves to an empty object.
  const api = new Proxy(baseMocks, {
    get: (target, prop) => (prop in target ? target[prop as string] : async () => ({})),
  });

  return { apiMock: api };
});

vi.mock('@/lib/api', () => ({ api: apiMock }));

import { DEFAULT_SETTINGS } from '@/lib/settings';
import { PreferencesTab } from './PreferencesTab';
import { AIEngineTab } from './AIEngineTab';
import { BrokerConnectionTab } from './BrokerConnectionTab';
import { QuantitativePricingTab } from './QuantitativePricingTab';
import { PaperTradingRiskTab } from './PaperTradingRiskTab';
import { TelegramTab } from './TelegramTab';
import { MonitoringTab } from './MonitoringTab';
import { MLOperationsTab } from './MLOperationsTab';
import { SettingsSidebar } from './SettingsSidebar';
import { TelegramToggle } from './telegram/TelegramToggle';
import { searchTabs, isSaveableTab, SETTINGS_TABS } from './registry';

const noop = () => {};

// No global setup file registers this, so clean the DOM between renders.
afterEach(() => cleanup());

describe('settings tabs render', () => {
  it('Preferences tab renders its sections', () => {
    render(
      <PreferencesTab
        settings={DEFAULT_SETTINGS.preferences}
        fullSettings={DEFAULT_SETTINGS}
        onChange={noop}
        onImportJson={() => ({ success: true })}
        onResetAll={async () => ({ success: true })}
      />,
    );
    expect(screen.getByText(/Display & Regional Formatting/i)).toBeTruthy();
    expect(screen.getByText(/Configuration Management/i)).toBeTruthy();
  });

  it('AI Engine tab renders the inference gateway', () => {
    render(<AIEngineTab settings={DEFAULT_SETTINGS.ai} onChange={noop} />);
    expect(screen.getByText(/Inference Gateway & Routing/i)).toBeTruthy();
  });

  it('Broker tab renders the FYERS gateway card', () => {
    render(
      <BrokerConnectionTab
        settings={DEFAULT_SETTINGS.broker}
        fullSettings={DEFAULT_SETTINGS}
        onChange={noop}
      />,
    );
    expect(screen.getByText(/Broker Gateway & Execution Session/i)).toBeTruthy();
  });

  it('Quant tab renders pricing kernel and cost breakdown', () => {
    render(
      <QuantitativePricingTab settings={DEFAULT_SETTINGS.quantitative} onChange={noop} />,
    );
    expect(screen.getByText(/Option Pricing & Greeks Kernel/i)).toBeTruthy();
    expect(screen.getByText(/Round-Trip Cost Breakdown/i)).toBeTruthy();
  });

  it('Paper Trading tab renders risk guardrails', () => {
    render(<PaperTradingRiskTab settings={DEFAULT_SETTINGS.paper} onChange={noop} />);
    expect(screen.getByText(/Execution limits & risk guardrails/i)).toBeTruthy();
  });

  it('Telegram tab renders the gateway after loading', async () => {
    render(<TelegramTab />);
    await waitFor(() =>
      expect(screen.getByText(/Telegram notification gateway/i)).toBeTruthy(),
    );
    expect(screen.getByText(/Signal & event subscriptions/i)).toBeTruthy();
    expect(screen.getByText(/Delivery probe simulator/i)).toBeTruthy();
    expect(screen.getByText(/Delivery telemetry & recent audit/i)).toBeTruthy();
  });

  it('Monitoring tab renders system telemetry and circuit breaker', async () => {
    render(<MonitoringTab />);
    await waitFor(() =>
      expect(screen.getByText(/System Telemetry & Health Monitoring/i)).toBeTruthy(),
    );
    expect(screen.getByText(/Forecast Engine Health & Settlement Diagnostics/i)).toBeTruthy();
    expect(screen.getByText(/Circuit Breaker Guard/i)).toBeTruthy();
  });

  it('ML Operations tab renders ensemble metadata and tournaments', async () => {
    render(<MLOperationsTab />);
    await waitFor(() =>
      expect(screen.getByText(/Machine Learning Operations & Calibration/i)).toBeTruthy(),
    );
    expect(screen.getByText(/Gradient Boosted Ensemble Architecture/i)).toBeTruthy();
  });
});

describe('telegram toggle accessibility', () => {
  it('is associated with its label and keyboard-focusable', () => {
    const onChange = vi.fn();
    render(<TelegramToggle checked={false} onChange={onChange} label="NIFTY" />);

    const input = screen.getByLabelText('NIFTY') as HTMLInputElement;
    expect(input.type).toBe('checkbox');

    input.focus();
    expect(document.activeElement).toBe(input);

    fireEvent.click(input);
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe('settings registry', () => {
  it('exposes all nine tabs', () => {
    expect(SETTINGS_TABS).toHaveLength(9);
  });

  it('finds a section by a field-level keyword', () => {
    expect(searchTabs('slippage').map((t) => t.id)).toEqual(['quantitative']);
    expect(searchTabs('fyers').map((t) => t.id)).toEqual(['broker']);
    expect(searchTabs('drawdown').map((t) => t.id)).toEqual(['paper']);
    expect(searchTabs('openrouter').map((t) => t.id)).toEqual(['ai']);
    expect(searchTabs('circuit breaker').map((t) => t.id)).toEqual(['paper', 'monitoring']);
    expect(searchTabs('xgboost').map((t) => t.id)).toEqual(['ml']);
    expect(searchTabs('nerve').map((t) => t.id)).toEqual(['system']);
  });

  it('marks telegram, monitoring, ml and system as not saveable through the settings provider', () => {
    expect(isSaveableTab('telegram')).toBe(false);
    expect(isSaveableTab('monitoring')).toBe(false);
    expect(isSaveableTab('ml')).toBe(false);
    expect(isSaveableTab('system')).toBe(false);
    expect(isSaveableTab('broker')).toBe(true);
  });
});

describe('settings sidebar', () => {
  const renderSidebar = (query: string) =>
    render(
      <SettingsSidebar
        activeTab="preferences"
        onTabChange={noop}
        query={query}
        onQueryChange={noop}
      />,
    );

  it('renders every tab label', () => {
    renderSidebar('');
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(SETTINGS_TABS.length);
    for (const tab of SETTINGS_TABS) {
      expect(tabs.some((t) => t.textContent?.includes(tab.label))).toBe(true);
    }
  });

  it('filters the nav as you type', () => {
    renderSidebar('telegram');
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(1);
    expect(tabs[0].textContent).toContain('Telegram Alerts');
  });

  it('shows an empty state when nothing matches', () => {
    renderSidebar('zzzznomatch');
    expect(screen.queryAllByRole('tab')).toHaveLength(0);
    expect(screen.getByText(/No settings match/i)).toBeTruthy();
  });

  it('highlights the System Nerve tab when activeTab is system', () => {
    render(
      <SettingsSidebar
        activeTab="system"
        onTabChange={noop}
        query=""
        onQueryChange={noop}
      />,
    );
    const systemTab = screen.getByRole('tab', { name: /System Nerve/i });
    expect(systemTab.getAttribute('aria-selected')).toBe('true');
  });
});
