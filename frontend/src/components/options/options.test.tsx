// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { OptionChainTable, fmtQty } from './OptionChainTable';
import { ExpectedMoveCard, resolveLadder, resolveTarget } from './ExpectedMoveCard';
import { fmtCompactINR } from './PayoffChart';
import { InstitutionalFlowTracker } from './InstitutionalFlowTracker';
import { api } from '@/lib/api';
import type { InstitutionalFlowResponse, OptionChainStrikeRow } from '@/lib/types';

vi.mock('@/lib/api', () => ({
  api: { getInstitutionalFlow: vi.fn() },
}));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe('fmtQty', () => {
  it('uses the drawer k convention and dashes absent values', () => {
    expect(fmtQty(1234567)).toBe('1235k');
    expect(fmtQty(950)).toBe('950');
    expect(fmtQty(0)).toBe('—');
    expect(fmtQty(null)).toBe('—');
  });
});

describe('resolveTarget', () => {
  it('treats small values as point offsets and near-spot values as legacy prices', () => {
    expect(resolveTarget(45, 25000, 80)).toBe(25045);
    expect(resolveTarget(24850, 25000, 80)).toBe(24850);
    expect(resolveTarget(undefined, 25000, 80)).toBe(25080);
  });
});

describe('resolveLadder sign logic', () => {
  const bearish = {
    underlying: 'NIFTY',
    spot_price: 25000,
    direction: 'BEARISH',
    horizon: 'INTRADAY',
    expected_move_points: 100,
    conservative_move_points: 70,
    aggressive_move_points: 145,
    expected_duration_hours: 2.5,
  };

  it('places bearish targets below spot (negative point deltas)', () => {
    const ladder = resolveLadder(bearish, 25000);
    expect(ladder.t1).toBe(24930);
    expect(ladder.t2).toBe(24855);
    expect(ladder.t3).toBe(24900);
  });

  it('resolves t3 through the same offset/absolute helper as T1/T2', () => {
    const offset = resolveLadder({ ...bearish, extended_target_t3: 200 }, 25000);
    expect(offset.t3).toBe(25000 - 200);
    const legacyAbsolute = resolveLadder({ ...bearish, extended_target_t3: 24800 }, 25000);
    expect(legacyAbsolute.t3).toBe(24800);
  });

  it('renders bearish point deltas with a minus sign, never a plus', () => {
    render(<ExpectedMoveCard data={bearish} />);
    expect(screen.getByText(/-70\.0 pts/)).toBeTruthy();
    expect(screen.getByText(/-145\.0 pts/)).toBeTruthy();
    expect(screen.getByText(/-100\.0 pts/)).toBeTruthy();
    expect(screen.queryByText(/\+70\.0 pts/)).toBeNull();
    expect(screen.queryByText(/\+145\.0 pts/)).toBeNull();
  });

  it('renders the unavailable state with the API error text', () => {
    render(<ExpectedMoveCard data={null} error="LIVE_IV_REQUIRED" />);
    expect(screen.getByText(/LIVE_IV_REQUIRED/)).toBeTruthy();
  });
});

describe('fmtCompactINR', () => {
  it('abbreviates crore/lakh and keeps small values exact', () => {
    expect(fmtCompactINR(4.2e9)).toBe('₹420.00 Cr');
    expect(fmtCompactINR(2.5e5)).toBe('₹2.50 L');
    expect(fmtCompactINR(500)).toBe('₹500');
    expect(fmtCompactINR(Number.NaN)).toBe('—');
  });
});

describe('OptionChainTable', () => {
  const rows: OptionChainStrikeRow[] = [
    {
      strike: 25000,
      is_atm: true,
      call: {
        symbol: 'NIFTY25000CE',
        ltp: 120,
        change: 1,
        change_percent: 1,
        volume: 500,
        open_interest: 1234567,
        oi_change: 10,
        bid: 119,
        ask: 121,
        is_itm: false,
        greeks: null,
      },
      put: null,
    },
  ];

  it('formats OI like the drawer, guards null greeks and exposes a caption', () => {
    render(
      <OptionChainTable strikes={rows} viewMode="standard" spotPrice={25000} asOf={new Date().toISOString()} />,
    );
    expect(screen.getByText('1235k')).toBeTruthy();
    expect(screen.getByText(/Option chain, 1 strikes/)).toBeTruthy();
    // Put side is absent entirely: every cell must read unavailable, not zero.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });
});

const zeroFlow: InstitutionalFlowResponse = {
  symbol: 'NIFTY',
  expiry: '2026-09-24',
  spot_price: 0,
  atm_strike: 0,
  pcr_oi: 0,
  pcr_volume: 0,
  max_pain_strike: 0,
  call_wall_strike: 0,
  put_floor_strike: 0,
  institutional_sentiment: 'NEUTRAL',
  institutional_score: 50,
  total_call_oi: 0,
  total_put_oi: 0,
  total_call_volume: 0,
  total_put_volume: 0,
  strike_flows: [],
};

describe('InstitutionalFlowTracker truth-of-wall', () => {
  it('renders no-data labels when walls and max pain come back as 0.0', async () => {    vi.mocked(api.getInstitutionalFlow).mockResolvedValue({
      data: zeroFlow,
      error: null,
      meta: { provider: 'test', timestamp: new Date().toISOString(), status: 'OFFLINE' },
    });
    render(<InstitutionalFlowTracker symbol="NIFTY" expiry="2026-09-24" />);
    expect(await screen.findByText(/No open interest published/)).toBeTruthy();
    expect(screen.queryByText('0 CE')).toBeNull();
    expect(screen.queryByText('0 PE')).toBeNull();
  });

  it('renders real walls as facts when OI is published', async () => {
    vi.mocked(api.getInstitutionalFlow).mockResolvedValue({
      data: {
        ...zeroFlow,
        spot_price: 25000,
        atm_strike: 25000,
        pcr_oi: 1.1,
        max_pain_strike: 24500,
        call_wall_strike: 26000,
        put_floor_strike: 24000,
        total_call_oi: 100,
        total_put_oi: 120,
        strike_flows: [
          {
            strike: 25000,
            is_atm: true,
            call_oi: 10,
            put_oi: 12,
            call_oi_change: 0,
            put_oi_change: 5,
            call_volume: 1,
            put_volume: 1,
            call_ltp: 100,
            put_ltp: 90,
            call_buildup: 'NEUTRAL',
            put_buildup: 'LONG_BUILDUP',
            net_flow: 'BULLISH',
          },
        ],
      },
      error: null,
      meta: { provider: 'test', timestamp: new Date().toISOString(), status: 'LIVE' },
    });
    render(<InstitutionalFlowTracker symbol="NIFTY" expiry="2026-09-24" marketClosed />);
    expect(await screen.findByText('26,000 CE')).toBeTruthy();
    expect(screen.getByText('24,000 PE')).toBeTruthy();
    expect(screen.getByText('24,500')).toBeTruthy();
  });

  it('ignores a late response for the previous symbol', async () => {
    type FlowResult = Awaited<ReturnType<typeof api.getInstitutionalFlow>>;
    const pending: Array<(value: FlowResult) => void> = [];
    vi.mocked(api.getInstitutionalFlow).mockImplementation(
      () => new Promise<FlowResult>((resolve) => { pending.push(resolve); }),
    );

    const flowFor = (symbol: string, callWall: number, putFloor: number): FlowResult => ({
      data: {
        ...zeroFlow,
        symbol,
        spot_price: 25000,
        atm_strike: 25000,
        pcr_oi: 1.1,
        max_pain_strike: 25000,
        call_wall_strike: callWall,
        put_floor_strike: putFloor,
        total_call_oi: 10,
        total_put_oi: 10,
        strike_flows: [],
      },
      error: null,
      meta: { provider: 'test', timestamp: new Date().toISOString(), status: 'LIVE' },
    });

    const { rerender } = render(<InstitutionalFlowTracker symbol="NIFTY" />);
    rerender(<InstitutionalFlowTracker symbol="BANKNIFTY" />);

    await act(async () => {
      pending[1](flowFor('BANKNIFTY', 52000, 50000));
    });
    expect(await screen.findByText('52,000 CE')).toBeTruthy();

    await act(async () => {
      pending[0](flowFor('NIFTY', 24500, 23500));
    });
    expect(screen.queryByText('24,500 CE')).toBeNull();
    expect(screen.getByText('52,000 CE')).toBeTruthy();
  });
});
