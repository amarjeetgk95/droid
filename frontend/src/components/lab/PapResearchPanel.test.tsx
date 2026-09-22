// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { PapResearchPanel } from './PapResearchPanel';
import { papApi, type PapStatus } from '@/lib/api/pap';

vi.mock('@/lib/api/pap', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/pap')>('@/lib/api/pap');
  return {
    ...actual,
    papApi: {
      getStatus: vi.fn(),
    },
  };
});

const BASE_STATUS: PapStatus = {
  phase: 'STAGE_1_BLOCKED_NO_REAL_DATA',
  verdict: 'NOT_RUN',
  criteria_version: 'pap-criteria-v1',
  pre_registered: {
    primary_metric: 'balanced_accuracy_uplift_vs_no_skill',
    min_absolute_uplift: '0.03',
  },
  gates: [
    { name: 'fyers_credentials', passed: false, detail: 'FYERS_ACCESS_TOKEN empty.' },
    { name: 'real_1m_data', passed: false, detail: 'Provenance-admissible: none.' },
    { name: 'experiment_report', passed: false, detail: 'No experiment report yet.' },
  ],
  instruments: [
    {
      instrument: 'NIFTY',
      slug: 'nifty',
      path: 'data/raw/nifty/1m.parquet',
      present: false,
      admissible: false,
      source: null,
      row_count: null,
      checksum_sha256: null,
      reasons: [],
      screen: null,
    },
    {
      instrument: 'BANKNIFTY',
      slug: 'banknifty',
      path: 'data/raw/banknifty/1m.parquet',
      present: false,
      admissible: false,
      source: null,
      row_count: null,
      checksum_sha256: null,
      reasons: [],
      screen: null,
    },
    {
      instrument: 'SENSEX',
      slug: 'sensex',
      path: 'data/raw/sensex/1m.parquet',
      present: true,
      admissible: false,
      source: 'synthetic_fixture',
      row_count: 67500,
      checksum_sha256: 'abc123',
      reasons: ['fixture_source: synthetic_fixture'],
      screen: { signals: ['gapless_sessions'] },
    },
  ],
  token_present: false,
  horizons: ['3m', '5m', '10m'],
  reports: [],
};

describe('PapResearchPanel', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('renders the blocked state honestly when data is missing or synthetic', async () => {
    vi.mocked(papApi.getStatus).mockResolvedValue(BASE_STATUS);
    render(<PapResearchPanel />);

    const verdict = await screen.findByTestId('pap-verdict');
    expect(verdict.textContent).toContain('NOT RUN');
    const blocked = screen.getByTestId('pap-data-blocked');
    expect(blocked.textContent).toMatch(/Experiment blocked.*provenance-verified real 1m data required/i);
    const sensexRow = screen.getByTestId('pap-inst-sensex');
    expect(sensexRow.textContent).toContain('refused');
    expect(sensexRow.textContent).toContain('synthetic_fixture');
  });

  it('renders a PASS verdict with phase STAGE_2_ALLOWED', async () => {
    vi.mocked(papApi.getStatus).mockResolvedValue({
      ...BASE_STATUS,
      phase: 'STAGE_2_ALLOWED',
      verdict: 'PASS',
      gates: [
        { name: 'fyers_credentials', passed: true, detail: 'FYERS access token present.' },
        { name: 'real_1m_data', passed: true, detail: 'All instruments verified.' },
        { name: 'experiment_report', passed: true, detail: 'Experiment verdict: PASS.' },
      ],
      reports: [
        {
          file: 'exp_20260922.json',
          verdict: 'PASS',
          created: '2026-09-22',
          criteria_version: 'pap-criteria-v1',
          experiment_id: 'pap-001',
        },
      ],
    });
    render(<PapResearchPanel />);

    const verdict = await screen.findByTestId('pap-verdict');
    expect(verdict.textContent).toContain('PASS');
    expect(screen.getByTestId('pap-reports')).toBeTruthy();
    expect(screen.queryByTestId('pap-data-blocked')).toBeNull();
  });

  it('shows the no-reports empty state when the runner has not executed', async () => {
    vi.mocked(papApi.getStatus).mockResolvedValue(BASE_STATUS);
    render(<PapResearchPanel />);

    await waitFor(() => expect(screen.getByTestId('pap-no-reports')).toBeTruthy());
    expect(screen.getByTestId('pap-criteria')).toBeTruthy();
  });

  it('renders a backend-unavailable error without fabricating status', async () => {
    vi.mocked(papApi.getStatus).mockRejectedValue(new Error('connection refused'));
    render(<PapResearchPanel />);

    await waitFor(() => expect(screen.getByText(/PAP status unavailable/)).toBeTruthy());
    expect(screen.queryByTestId('pap-verdict')).toBeNull();
  });
});
