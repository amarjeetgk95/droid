// @vitest-environment happy-dom
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

const { apiMock } = vi.hoisted(() => {
  const api = {
    request: vi.fn(),
    getBrokerTokenStatus: vi.fn(),
    runTokenDiagnostics: vi.fn(),
    refreshBrokerToken: vi.fn(),
    getTelegramStatus: vi.fn(),
    sendTelegramTestMessage: vi.fn(),
    revokeTelegramLink: vi.fn(),
    rollbackAlgoAiModel: vi.fn(),
    testAi: vi.fn(),
    getCacheStats: vi.fn(),
    clearCache: vi.fn(),
    getCircuitBreakerStatus: vi.fn(),
    getMarketHealth: vi.fn(),
  };
  return { apiMock: api };
});

vi.mock('@/lib/api', () => ({ api: apiMock }));

import { asNumber, toErrorMessage } from './PanelState';
import { SystemMetricsPanel } from './SystemMetricsPanel';
import { BrokerConnectionPanel } from './BrokerConnectionPanel';
import { TelegramIntegration } from './TelegramIntegration';
import { AIProviderManager } from './AIProviderManager';
import { AIDriftMonitor } from './AIDriftMonitor';
import { CacheManager } from './CacheManager';

afterEach(() => cleanup());
beforeEach(() => {
  vi.clearAllMocks();
});

describe('SystemMetricsPanel', () => {
  it('renders real subsystem/database/breaker telemetry and marks CPU/RAM unavailable', async () => {
    apiMock.request.mockImplementation(async (url: string) => {
      if (url === '/health/subsystems') {
        return {
          status: 'ok',
          timestamp: '2026-09-17T08:00:00+00:00',
          elements: {
            central_feed: true,
            signal_worker: true,
            morning_briefing: false,
            forecast_scheduler: true,
            flow_scheduler: true,
            chain_status: 'FRESH',
            chain_strikes: 120,
            chain_age_ms: 4000,
            chain_mark_status: 'LIVE',
            tick_sanity_rejections: 0,
          },
        };
      }
      if (url === '/api/v1/health/database') {
        return { status: 'ok', connected: true, database: 'droid', counts: { executed_signals: 7 } };
      }
      throw new Error(`unexpected url ${url}`);
    });
    apiMock.getCircuitBreakerStatus.mockResolvedValue({
      data: { state: 'CLOSED', failure_count: 0, failure_threshold: 5, tripped_count: 1 },
      error: null,
      meta: { timestamp: '2026-09-17T08:00:00+00:00' },
    });
    apiMock.getMarketHealth.mockResolvedValue({
      status: 'HEALTHY',
      provider: 'fyers',
      mode: 'LIVE',
      last_update: '2026-09-17T08:00:00+00:00',
      data_age_seconds: 2,
      latency_ms: null,
      active_instruments: 4,
      reconnect_count: 0,
      subscriptions: 8,
      buffer_depth: 0,
      dropped_events: 0,
      circuit_breaker_state: 'CLOSED',
      last_heartbeat: null,
      message: '',
    });

    render(<SystemMetricsPanel />);

    expect(await screen.findByText('HEALTHY')).toBeTruthy();
    expect(screen.getByText('CONNECTED')).toBeTruthy();
    expect(screen.getByText('CLOSED')).toBeTruthy();
    expect(screen.getByText('3/4 running')).toBeTruthy();
    expect(screen.getByText(/Backend CPU Load/).parentElement?.textContent).toContain(
      'No value is invented',
    );
    expect(screen.getByText(/RAM Utilization/).parentElement?.textContent).toContain(
      'No value is invented',
    );
  });

  it('renders an explicit unavailable state when every telemetry leg fails', async () => {
    apiMock.request.mockRejectedValue(new Error('backend offline'));
    apiMock.getCircuitBreakerStatus.mockRejectedValue(new Error('backend offline'));
    apiMock.getMarketHealth.mockRejectedValue(new Error('backend offline'));

    render(<SystemMetricsPanel />);

    expect(
      await screen.findByRole('button', { name: /Retry System telemetry request/i }),
    ).toBeTruthy();
    expect(screen.queryByText('HEALTHY')).toBeNull();
  });
});

describe('BrokerConnectionPanel', () => {
  const tokenStatus = {
    provider: 'fyers',
    state: 'AUTH_EXPIRED',
    is_token_valid: false,
    connection_started_at: null,
    uptime_seconds: null,
    last_message_at: null,
    last_heartbeat_at: null,
    data_lag_seconds: 42,
    reconnect_count: 3,
    subscription_count: 8,
    last_error: 'access token expired',
  };

  beforeEach(() => {
    apiMock.getBrokerTokenStatus.mockResolvedValue({
      data: tokenStatus,
      error: null,
      meta: { timestamp: '2026-09-17T08:00:00+00:00' },
    });
  });

  it('renders real token fields and never claims AUTHENTICATED for an expired token', async () => {
    render(<BrokerConnectionPanel />);

    expect(await screen.findByText('AUTH_EXPIRED')).toBeTruthy();
    expect(screen.getByText('EXPIRED')).toBeTruthy();
    expect(screen.getByText('access token expired')).toBeTruthy();
    expect(screen.queryByText('AUTHENTICATED')).toBeNull();
    expect(screen.queryByText('Just now')).toBeNull();
  });

  it('surfaces a failed diagnostics probe instead of a fabricated pass', async () => {
    apiMock.runTokenDiagnostics.mockRejectedValue(new Error('broker probe offline'));

    render(<BrokerConnectionPanel />);
    fireEvent.click(await screen.findByRole('button', { name: /Run broker token diagnostics/i }));

    expect(await screen.findByText(/broker probe offline/)).toBeTruthy();
    expect(screen.getByText('Diagnostics result')).toBeTruthy();
    expect(screen.queryByText(/Diagnostics Passed/)).toBeNull();
    expect(screen.queryByText(/permissions verified/)).toBeNull();
  });

  it('requires confirmation before re-authenticating and shows the real outcome', async () => {
    apiMock.refreshBrokerToken.mockResolvedValue({
      data: { refreshed: false, provider: 'fyers', has_token: false, auth_method: 'oauth_callback_required' },
      error: null,
      meta: { timestamp: '2026-09-17T08:00:00+00:00' },
    });

    render(<BrokerConnectionPanel />);
    fireEvent.click(await screen.findByRole('button', { name: /Re-authenticate broker token/i }));

    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(apiMock.refreshBrokerToken).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Re-authenticate' }));
    expect(await screen.findByText(/No new token was issued/)).toBeTruthy();
    expect(apiMock.refreshBrokerToken).toHaveBeenCalledTimes(1);
  });
});

describe('TelegramIntegration', () => {
  it('renders the raw backend payload without fabricated bot defaults', async () => {
    apiMock.getTelegramStatus.mockResolvedValue({
      bot_configured: true,
      bot_username: null,
      webhook_configured: false,
      binding: { linked: false, telegram_chat_id: null, linked_at: null, status: 'NOT_LINKED' },
      environment: 'production',
      queue_stats: { total: 5, queued: 1, dead_letter: 0, statuses: { SENT: 4 } },
    });

    render(<TelegramIntegration />);

    expect(await screen.findByText('NOT CONFIGURED')).toBeTruthy();
    expect(screen.queryByText('@DroidQuantBot')).toBeNull();
    expect(screen.queryByText('984102941')).toBeNull();
    expect(screen.getByText('production')).toBeTruthy();
    expect(screen.getByText('SENT 4')).toBeTruthy();
  });

  it('sends the test ping with no arguments and reports the enqueue result', async () => {
    apiMock.getTelegramStatus.mockResolvedValue({
      bot_configured: true,
      bot_username: 'droid_real_bot',
      webhook_configured: true,
      binding: {
        linked: true,
        telegram_chat_id: '123456789',
        linked_at: 1758000000,
        status: 'ACTIVE',
      },
      environment: 'production',
      queue_stats: {},
    });
    apiMock.sendTelegramTestMessage.mockResolvedValue({
      status: 'enqueued',
      notification_id: 'ntf-1',
    });
    apiMock.revokeTelegramLink.mockResolvedValue({ status: 'revoked' });

    render(<TelegramIntegration />);
    expect(await screen.findByText('droid_real_bot')).toBeTruthy();
    expect(screen.getByText('123456789')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Send Telegram test alert/i }));
    expect(await screen.findByText(/Test alert enqueued \(ID ntf-1\)/)).toBeTruthy();
    expect(apiMock.sendTelegramTestMessage).toHaveBeenCalledWith();

    fireEvent.click(screen.getByRole('button', { name: /Revoke Telegram account link/i }));
    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(apiMock.revokeTelegramLink).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Revoke link' }));
    expect(await screen.findByText(/Telegram unlinked/)).toBeTruthy();
  });
});

describe('AIProviderManager', () => {
  it('renders registered models from the registry without invented latency', async () => {
    apiMock.request.mockResolvedValue({
      data: [
        {
          key: 'google:gemini-3.8:2026-01',
          provider: 'google',
          model_id: 'gemini-3.8',
          model_version: '2026-01',
          prompt_version: 'v4',
          status: 'CURRENT',
          is_last_known_good: true,
          canary_pct: '0',
        },
        {
          key: 'anthropic:claude-4:2026-02',
          provider: 'anthropic',
          model_id: 'claude-4',
          model_version: '2026-02',
          prompt_version: 'v2',
          status: 'CANARY',
          is_last_known_good: false,
          canary_pct: '15',
        },
      ],
      error: null,
      meta: { timestamp: '2026-09-17T08:00:00+00:00' },
    });

    render(<AIProviderManager />);

    expect(await screen.findByText('gemini-3.8')).toBeTruthy();
    expect(screen.getByText('claude-4')).toBeTruthy();
    expect(screen.queryByText(/220ms/)).toBeNull();
    expect(screen.queryByText(/Latency: ~/)).toBeNull();
    expect(screen.getByText(/canary 15%/)).toBeTruthy();
  });

  it('reports the measured latency from the test endpoint', async () => {
    apiMock.request.mockResolvedValue({ data: [], error: null, meta: {} });
    apiMock.testAi.mockResolvedValue({
      data: {
        success: true,
        provider: 'openrouter',
        model: 'deepseek/deepseek-chat',
        latency_ms: 123,
        schema_valid: true,
      },
      error: null,
      meta: { timestamp: '2026-09-17T08:00:00+00:00' },
    });

    render(<AIProviderManager />);
    fireEvent.click(await screen.findByRole('button', { name: /Test AI provider inference/i }));

    expect(await screen.findByText(/123 ms/)).toBeTruthy();
    expect(screen.getByText(/deepseek\/deepseek-chat/)).toBeTruthy();
    expect(screen.queryByText(/240ms/)).toBeNull();
  });

  it('confirms rollback and shows the real restored model', async () => {
    apiMock.request.mockResolvedValue({
      data: [
        {
          key: 'google:gemini-3.8:2026-01',
          provider: 'google',
          model_id: 'gemini-3.8',
          model_version: '2026-01',
          prompt_version: 'v4',
          status: 'CANARY',
          is_last_known_good: false,
          canary_pct: '15',
        },
      ],
      error: null,
      meta: { timestamp: '2026-09-17T08:00:00+00:00' },
    });
    apiMock.rollbackAlgoAiModel.mockResolvedValue({
      data: { rolled_back: 'google:gemini-3.8:2026-01', restored: 'google:gemini-3.7:2025-12' },
      error: null,
      meta: { timestamp: '2026-09-17T08:00:00+00:00' },
    });

    render(<AIProviderManager />);

    fireEvent.click(await screen.findByRole('button', { name: 'Rollback gemini-3.8 to last known good' }));
    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(apiMock.rollbackAlgoAiModel).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Roll back model' }));
    expect(await screen.findByText(/restored: google:gemini-3.7:2025-12/)).toBeTruthy();
    expect(apiMock.rollbackAlgoAiModel).toHaveBeenCalledWith('google:gemini-3.8:2026-01');
  });
});

describe('AIDriftMonitor', () => {
  it('maps real drift_state / bias_shift_* fields', async () => {
    apiMock.request.mockResolvedValue({
      data: {
        drift_state: 'DRIFT_WARNING',
        confidence_shift: 0.2,
        recent_conf_mean: 0.6,
        baseline_conf_mean: 0.4,
        bias_shift_LONG: 0.3,
        schema_failure_rate: 0.06,
        drift_flags: ['CONFIDENCE_SHIFT', 'BIAS_SHIFT_LONG'],
      },
      error: null,
      meta: { timestamp: '2026-09-17T08:00:00+00:00' },
    });

    render(<AIDriftMonitor />);

    expect(await screen.findByText('DRIFT_WARNING')).toBeTruthy();
    expect(screen.getByText('20.0%')).toBeTruthy();
    expect(screen.getByText('30.0% shift')).toBeTruthy();
    expect(screen.getByText('2 FLAGGED')).toBeTruthy();
    expect(screen.queryByText(/NO_SIGNIFICANT_DRIFT/)).toBeNull();
  });

  it('renders INSUFFICIENT_DATA as an absence of evidence, not a healthy verdict', async () => {
    apiMock.request.mockResolvedValue({
      data: { drift_state: 'NORMAL', reason: 'INSUFFICIENT_DATA' },
      error: null,
      meta: { timestamp: '2026-09-17T08:00:00+00:00' },
    });

    render(<AIDriftMonitor />);

    expect(await screen.findByText('INSUFFICIENT DATA')).toBeTruthy();
    expect(screen.getByText(/not a healthy result/)).toBeTruthy();
  });
});

describe('CacheManager', () => {
  beforeEach(() => {
    apiMock.getCacheStats.mockResolvedValue({
      data: {
        backend: 'in_memory_lru',
        items_count: 120,
        max_capacity: 50000,
        hit_count: 900,
        miss_count: 100,
        total_requests: 1000,
        hit_ratio_percent: 90,
        eviction_count: 3,
        expired_count: 5,
      },
      error: null,
      meta: { timestamp: '2026-09-17T08:00:00+00:00' },
    });
  });

  it('renders real cache fields and no fabricated memory figure', async () => {
    render(<CacheManager />);

    expect(await screen.findByText('120 / 50000')).toBeTruthy();
    expect(screen.getByText('90.0%')).toBeTruthy();
    expect(screen.queryByText(/24\.5\s*MB/)).toBeNull();
    expect(screen.queryByText('18,420')).toBeNull();
  });

  it('confirms the purge and reports the real post-clear outcome', async () => {
    apiMock.clearCache.mockResolvedValue({
      data: { cleared: true },
      error: null,
      meta: { timestamp: '2026-09-17T08:00:00+00:00' },
    });

    render(<CacheManager />);
    fireEvent.click(await screen.findByRole('button', { name: /Purge in-memory cache/i }));

    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(apiMock.clearCache).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Purge cache' }));
    expect(await screen.findByText(/Cache flushed/)).toBeTruthy();
    expect(apiMock.clearCache).toHaveBeenCalledTimes(1);
    expect(apiMock.getCacheStats.mock.calls.length).toBeGreaterThan(1);
  });
});

describe('system-nerve source guards', () => {
  const dir = path.resolve(process.cwd(), 'src/components/system-nerve');
  const files = readdirSync(dir).filter(
    (file) => (file.endsWith('.tsx') || file.endsWith('.ts')) && !file.endsWith('.test.tsx'),
  );

  it('contains no private polling intervals (hidden-tab pause is owned by usePolling)', () => {
    for (const file of files) {
      const source = readFileSync(path.join(dir, file), 'utf8');
      expect(source.includes('setInterval('), `${file} must not own an interval`).toBe(false);
    }
  });

  it('removed the duplicated SettingsEditor and its no-op confirmation copy', () => {
    expect(existsSync(path.join(dir, 'SettingsEditor.tsx'))).toBe(false);
    for (const file of files) {
      const source = readFileSync(path.join(dir, file), 'utf8');
      expect(source.includes('Settings applied across all frontend clients')).toBe(false);
    }
  });

  it('contains no fabricated telemetry constants or fake authenticated claims', () => {
    const banned = [
      'getSystemMetrics',
      'cpu_pct',
      'memory_pct',
      'db_latency_ms',
      'active_websockets',
      'circuit_breakers_ok',
      'memory_mb',
      'cache_hits',
      'drift_score',
      'ks_test_p_value',
      'feature_shifts',
      '@DroidQuantBot',
      '984102941',
      'AUTHENTICATED',
      'Diagnostics Passed',
      'permissions verified',
      'Just now',
      '240ms',
    ];
    for (const file of files) {
      const source = readFileSync(path.join(dir, file), 'utf8');
      for (const token of banned) {
        expect(source.includes(token), `${file} must not contain "${token}"`).toBe(false);
      }
    }
  });
});

describe('PanelState helpers', () => {
  it('asNumber rejects empty and whitespace-only strings, never coercing them to 0', () => {
    expect(asNumber('12.5')).toBe(12.5);
    expect(asNumber(0)).toBe(0);
    expect(asNumber('')).toBeNull();
    expect(asNumber('   ')).toBeNull();
    expect(asNumber('abc')).toBeNull();
    expect(asNumber(true)).toBeNull();
  });

  it('toErrorMessage keeps the module fallback for blank errors', () => {
    expect(toErrorMessage(new Error('boom'))).toBe('boom');
    expect(toErrorMessage('direct')).toBe('direct');
    expect(toErrorMessage(new Error('   '))).toBe('Request failed with no error detail.');
    expect(toErrorMessage(undefined)).toBe('Request failed with no error detail.');
  });
});
