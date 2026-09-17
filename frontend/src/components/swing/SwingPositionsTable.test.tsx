// @vitest-environment happy-dom
import type { ReactElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SwingPositionDTO } from '@/lib/api/swing';
import { ToastProvider } from '@/components/ui/toast';
import { SwingPositionsTable } from './SwingPositionsTable';

afterEach(() => cleanup());

function renderTable(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

function position(overrides: Partial<SwingPositionDTO> = {}): SwingPositionDTO {
  return {
    position_id: 'p1',
    setup_id: 's1',
    underlying: 'NIFTY',
    option_type: 'CE',
    strike: 24500,
    expiry_date: '2026-09-25',
    contract_symbol: 'NIFTY26SEP24500CE',
    direction: 'LONG_CALL',
    strategy: 'TREND_BREAKOUT_CE',
    horizon: 'POSITIONAL',
    entry_premium: 120,
    current_premium: 120,
    num_lots: 1,
    lot_size: 75,
    initial_stop_premium: 90,
    current_stop_premium: 90,
    spot_stop: 24400,
    stop_method: 'INITIAL',
    target_1: 165,
    target_2: 210,
    spot_at_entry: 24510,
    current_spot: 24510,
    greeks_at_entry: { delta: 0.5, theta_day: -6 },
    iv_at_entry: 0.15,
    days_held: 2,
    dte_remaining: 10,
    highest_premium: 120,
    theta_cost_accumulated: 0,
    unrealized_pnl: 0,
    pnl_pct: 0,
    r_multiple: 0,
    status: 'OPEN',
    ...overrides,
  };
}

describe('SwingPositionsTable truth states', () => {
  it('renders a loading state instead of a false empty portfolio', () => {
    renderTable(<SwingPositionsTable positions={[]} loading />);
    expect(screen.getByText(/Loading swing positions/i)).toBeTruthy();
    expect(screen.queryByText(/No open swing options positions/i)).toBeNull();
  });

  it('renders an explicit unavailable state when the positions fetch failed', () => {
    renderTable(
      <SwingPositionsTable
        positions={[]}
        loadError="backend unreachable"
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText(/Open positions unavailable/i)).toBeTruthy();
    expect(screen.getByText('backend unreachable')).toBeTruthy();
  });

  it('marks marks as STALE and says so when a refresh fails over old data', () => {
    renderTable(
      <SwingPositionsTable
        positions={[position()]}
        stale
        loadError="network down"
        marksAt={Date.now() - 120_000}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText(/Positions refresh failed/i)).toBeTruthy();
    expect(screen.getByText(/STALE/)).toBeTruthy();
  });

  it('labels structured exit reasons and keeps a flat return neutral', () => {
    const closed = position({
      position_id: 'c1',
      status: 'CLOSED',
      exit_reason: 'TARGET_1',
      unrealized_pnl: 0,
      pnl_pct: 0,
      r_multiple: 0,
    });
    renderTable(<SwingPositionsTable positions={[]} closedPositions={[closed]} />);

    fireEvent.click(screen.getByText(/Closed History/));
    expect(screen.getByText('Target 1 Hit (+1.5R)')).toBeTruthy();

    const flat = screen.getByText('₹0');
    expect(flat.className).toContain('text-muted-foreground');
    expect(flat.className).not.toContain('text-up');
  });

  it('requires a positive exit premium before confirming a close', () => {
    renderTable(<SwingPositionsTable positions={[position()]} onExitPosition={vi.fn()} />);

    fireEvent.click(screen.getByText('Close Trade'));
    const input = document.getElementById('swing-exit-premium') as HTMLInputElement;
    expect(input).toBeTruthy();

    fireEvent.change(input, { target: { value: '0' } });
    fireEvent.click(screen.getByText('Confirm Close'));
    expect(screen.getByText(/Enter a positive exit premium/i)).toBeTruthy();
  });
});
