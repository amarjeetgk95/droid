// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

const { apiMock, polls } = vi.hoisted(() => {
  const apiMock: Record<string, ReturnType<typeof vi.fn>> = {
    getPaperPositions: vi.fn(async () => ({ data: [] })),
    getAlgoPositions: vi.fn(async () => ({ data: [] })),
    closePaperPosition: vi.fn(async () => ({ data: { closed: true } })),
    exitAlgoPosition: vi.fn(async () => ({ data: { closed: true } })),
    getPaperPortfolio: vi.fn(async () => ({ data: null })),
    closeAllPaperPositions: vi.fn(async () => ({ data: [] })),
    getAlgoOrders: vi.fn(async () => ({ data: [] })),
    cancelAlgoOrder: vi.fn(async () => ({ data: { cancelled: true } })),
    getAlgoKillSwitch: vi.fn(async () => ({ data: { is_killed: false, kill_level: 'NONE' } })),
    triggerAlgoKillSwitch: vi.fn(async () => ({ data: { is_killed: true, kill_level: 'FULL_EXECUTION_STOP' } })),
    exitAllAlgoPositions: vi.fn(async () => ({ data: { closed_count: 2 } })),
    getAlgoAccount: vi.fn(async () => ({ data: { account_id: 'a1', mode: 'PAPER' } })),
    getAlgoConsent: vi.fn(async () => ({
      data: {
        disclosure: { version: 'v1.0-2026-08-31', content: 'x', requires_acknowledgement: true, pre_checked: false },
        consents: [],
        current_ok: true,
      },
    })),
    acknowledgeAlgoConsent: vi.fn(async () => ({ data: { acknowledged: true, version: 'v1.0-2026-08-31' } })),
    setAlgoMode: vi.fn(async () => ({ data: { mode: 'PAPER', status: 'OK' } })),
    getQuote: vi.fn(async () => ({
      data: { symbol: 'NIFTY 24350 CE', ltp: 135, status: 'LIVE', timestamp: new Date().toISOString() },
    })),
    createAlgoBasket: vi.fn(async () => ({ data: { accepted: 1, status: 'ACCEPTED' } })),
    getAlgoExposure: vi.fn(async () => ({ data: {} })),
    previewAlgoSizing: vi.fn(async () => ({ data: {} })),
    getAlgoCapital: vi.fn(async () => ({ data: { config: {} } })),
    updateAlgoCapital: vi.fn(async () => ({ data: { updated: true } })),
    runAlgoReconciliation: vi.fn(async () => ({ data: {} })),
  };
  const polls: Array<() => unknown> = [];
  return { apiMock, polls };
});

vi.mock('@/lib/api', () => ({ api: apiMock }));
vi.mock('@/hooks/usePolling', () => ({
  usePolling: (cb: () => unknown) => {
    polls.push(cb);
  },
}));

import { PositionsTable } from './PositionsTable';
import { PaperPortfolioCard } from './PaperPortfolioCard';
import { OrderBook } from './OrderBook';
import { BasketOrderBuilder } from './BasketOrderBuilder';
import { KillSwitchButton } from './KillSwitchButton';
import { ExecutionModeSwitcher } from './ExecutionModeSwitcher';
import { ExposureGauge } from './ExposureGauge';
import { SizingPreview } from './SizingPreview';
import { CapitalLimitsEditor } from './CapitalLimitsEditor';
import { ReconciliationPanel } from './ReconciliationPanel';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  polls.length = 0;
});

async function flushPolls() {
  const callbacks = [...polls];
  polls.length = 0;
  await act(async () => {
    await Promise.all(callbacks.map((cb) => Promise.resolve(cb())));
  });
}

const paperPosition = {
  position_id: 'P1',
  symbol: 'NIFTY 24350 CE',
  underlying: 'NIFTY',
  instrument_type: 'OPT',
  side: 'BUY' as const,
  product: 'INTRADAY' as const,
  quantity: 75,
  average_price: 124.5,
  ltp: 142,
  unrealized_pnl: 1312.5,
  realized_pnl: 0,
  used_margin: 1000,
  is_open: true,
};

const portfolio = {
  virtual_capital: 500000,
  available_margin: 400000,
  used_margin: 100000,
  margin_utilization_pct: 20,
  total_realized_pnl: 1000,
  total_unrealized_pnl: -500,
  total_portfolio_pnl: 500,
  open_positions_count: 2,
};

describe('PositionsTable safety', () => {
  it('clears rows when the backend returns an empty book instead of keeping stale rows', async () => {
    apiMock.getPaperPositions.mockResolvedValue({ data: [paperPosition] });
    render(<PositionsTable />);
    await flushPolls();
    expect(screen.getByText('NIFTY 24350 CE')).toBeTruthy();

    apiMock.getPaperPositions.mockResolvedValue({ data: [] });
    await flushPolls();
    expect(screen.queryByText('NIFTY 24350 CE')).toBeNull();
    expect(screen.getByText('No active open positions.')).toBeTruthy();
  });

  it('requires confirmation before exit and never removes the row when the backend reports closed:false', async () => {
    apiMock.getPaperPositions.mockResolvedValue({ data: [paperPosition] });
    apiMock.closePaperPosition.mockResolvedValue({ data: { closed: false, is_open: true } });
    render(<PositionsTable />);
    await flushPolls();

    fireEvent.click(screen.getByRole('button', { name: 'Exit' }));
    expect(apiMock.closePaperPosition).not.toHaveBeenCalled();
    expect(screen.getByText(/Close this/)).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'CONFIRM EXIT' }));
    });

    expect(apiMock.closePaperPosition).toHaveBeenCalledWith('P1');
    expect(screen.getAllByText(/did not confirm the close/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('NIFTY 24350 CE').length).toBeGreaterThan(0);
  });

  it('keeps the row when the exit request throws', async () => {
    apiMock.getPaperPositions.mockResolvedValue({ data: [paperPosition] });
    apiMock.closePaperPosition.mockRejectedValue(new Error('broker offline'));
    render(<PositionsTable />);
    await flushPolls();

    fireEvent.click(screen.getByRole('button', { name: 'Exit' }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'CONFIRM EXIT' }));
    });

    expect(screen.getAllByText(/broker offline/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('NIFTY 24350 CE').length).toBeGreaterThan(0);
  });
});

describe('PaperPortfolioCard truth states', () => {
  it('shows unavailable instead of hardcoded capital when the portfolio fails', async () => {
    apiMock.getPaperPortfolio.mockRejectedValue(new Error('paper service down'));
    render(<PaperPortfolioCard />);
    await flushPolls();

    expect(screen.getByText(/Paper portfolio unavailable/)).toBeTruthy();
    expect(screen.queryByText(/10,00,000/)).toBeNull();
    expect(screen.queryByText(/14,250/)).toBeNull();
  });

  it('requires confirmation for square-off and surfaces a partial result', async () => {
    apiMock.getPaperPortfolio.mockResolvedValue({ data: portfolio });
    apiMock.closeAllPaperPositions.mockResolvedValue({ data: [] });
    render(<PaperPortfolioCard />);
    await flushPolls();

    fireEvent.click(screen.getByRole('button', { name: 'Square Off All' }));
    expect(apiMock.closeAllPaperPositions).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'SQUARE OFF ALL' }));
    });

    expect(apiMock.closeAllPaperPositions).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Square-off incomplete: 0 of 2/)).toBeTruthy();
  });

  it('reports a failure when the square-off payload is invalid', async () => {
    apiMock.getPaperPortfolio.mockResolvedValue({ data: portfolio });
    apiMock.closeAllPaperPositions.mockResolvedValue({ data: { closed: false } });
    render(<PaperPortfolioCard />);
    await flushPolls();

    fireEvent.click(screen.getByRole('button', { name: 'Square Off All' }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'SQUARE OFF ALL' }));
    });

    expect(screen.getAllByText(/did not return a square-off result/).length).toBeGreaterThan(0);
  });
});

describe('OrderBook truth states', () => {
  it('clears rows on an empty backend response and only offers cancel for cancellable statuses', async () => {
    apiMock.getAlgoOrders.mockResolvedValue({
      data: [
        {
          client_order_id: 'ORD-1',
          symbol: 'NIFTY 24350 CE',
          side: 'BUY',
          quantity: 75,
          status: 'FILLED',
          filled_quantity: 75,
          price: 100,
        },
        {
          client_order_id: 'ORD-2',
          symbol: 'NIFTY 24450 CE',
          side: 'SELL',
          quantity: 75,
          status: 'PENDING',
          filled_quantity: 0,
          price: 82,
        },
      ],
    });
    render(<OrderBook />);
    await flushPolls();

    expect(screen.getAllByRole('button', { name: 'Cancel' })).toHaveLength(1);

    apiMock.getAlgoOrders.mockResolvedValue({ data: [] });
    await flushPolls();
    expect(screen.queryByText('ORD-2')).toBeNull();
    expect(screen.getByText('No orders in the book.')).toBeTruthy();
  });

  it('keeps the order live and reports failure when the broker does not confirm cancellation', async () => {
    apiMock.getAlgoOrders.mockResolvedValue({
      data: [
        {
          client_order_id: 'ORD-2',
          symbol: 'NIFTY 24450 CE',
          side: 'SELL',
          quantity: 75,
          status: 'PENDING',
          filled_quantity: 0,
          price: 82,
        },
      ],
    });
    apiMock.cancelAlgoOrder.mockResolvedValue({ data: { cancelled: false } });
    render(<OrderBook />);
    await flushPolls();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(apiMock.cancelAlgoOrder).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'CONFIRM CANCEL' }));
    });

    expect(screen.getAllByText(/did not confirm cancellation/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('ORD-2').length).toBeGreaterThan(0);
    expect(screen.queryByText('CANCELLED')).toBeNull();
  });
});

describe('BasketOrderBuilder quote gating', () => {
  async function addLeg(symbol: string, quantity: number) {
    fireEvent.click(screen.getByRole('button', { name: '+ Add Leg' }));
    fireEvent.change(screen.getByLabelText('Leg 1 symbol'), { target: { value: symbol } });
    fireEvent.change(screen.getByLabelText('Leg 1 quantity'), { target: { value: String(quantity) } });
    await flushPolls();
  }

  it('blocks review when a live quote is unavailable', async () => {
    apiMock.getQuote.mockRejectedValue(new Error('feed down'));
    render(<BasketOrderBuilder />);
    await addLeg('NIFTY 24350 CE', 75);

    fireEvent.click(screen.getByRole('button', { name: /REVIEW MULTI-LEG BASKET/ }));
    expect(screen.getByText(/Basket blocked/)).toBeTruthy();
    expect(apiMock.createAlgoBasket).not.toHaveBeenCalled();
  });

  it('blocks review when the quote is stale', async () => {
    apiMock.getQuote.mockResolvedValue({
      data: {
        symbol: 'NIFTY 24350 CE',
        ltp: 135,
        status: 'LIVE',
        timestamp: new Date(Date.now() - 120_000).toISOString(),
      },
    });
    render(<BasketOrderBuilder />);
    await addLeg('NIFTY 24350 CE', 75);

    fireEvent.click(screen.getByRole('button', { name: /REVIEW MULTI-LEG BASKET/ }));
    expect(screen.getByText(/quote stale/)).toBeTruthy();
    expect(apiMock.createAlgoBasket).not.toHaveBeenCalled();
  });

  it('shows the exact quote-derived payload and only sends after confirmation', async () => {
    apiMock.getQuote.mockResolvedValue({
      data: {
        symbol: 'NIFTY 24350 CE',
        ltp: 135,
        status: 'LIVE',
        timestamp: new Date().toISOString(),
      },
    });
    render(<BasketOrderBuilder />);
    await addLeg('NIFTY 24350 CE', 75);

    fireEvent.click(screen.getByRole('button', { name: /REVIEW MULTI-LEG BASKET/ }));
    expect(apiMock.createAlgoBasket).not.toHaveBeenCalled();
    expect(screen.getByText(/"price": 135/)).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'CONFIRM & SEND BASKET' }));
    });

    expect(apiMock.createAlgoBasket).toHaveBeenCalledWith({
      orders: [{ symbol: 'NIFTY 24350 CE', side: 'BUY', quantity: 75, price: 135, order_type: 'LIMIT' }],
      execution_mode: 'ATOMIC',
      leg_risk_policy: 'HOLD_AND_ALERT',
    });
    expect(screen.getByText(/Basket dispatched/)).toBeTruthy();
  });

  it('reports engine rejection instead of a fabricated success', async () => {
    render(<BasketOrderBuilder />);
    await addLeg('NIFTY 24350 CE', 75);
    apiMock.createAlgoBasket.mockResolvedValue({ data: { status: 'REJECTED', reason: 'margin short' } });

    fireEvent.click(screen.getByRole('button', { name: /REVIEW MULTI-LEG BASKET/ }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'CONFIRM & SEND BASKET' }));
    });

    expect(screen.getAllByText(/Basket rejected by the engine/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Basket dispatched/)).toBeNull();
  });
});

describe('KillSwitchButton safety', () => {
  it('renders persistent halt state from the backend and disables the trigger', async () => {
    apiMock.getAlgoKillSwitch.mockResolvedValue({
      data: { is_killed: true, kill_level: 'FULL_EXECUTION_STOP', killed_at: '2026-09-17T10:00:00Z' },
    });
    render(<KillSwitchButton />);
    await flushPolls();

    const trigger = screen.getByRole('button', { name: /EXECUTION ENGINES HALTED/ }) as HTMLButtonElement;
    expect(trigger.disabled).toBe(true);
    expect(screen.getByText(/Kill switch ENGAGED/)).toBeTruthy();
  });

  it('reports an unconfirmed kill as a failure without claiming the engine halted', async () => {
    apiMock.getAlgoKillSwitch.mockResolvedValue({ data: { is_killed: false, kill_level: 'NONE' } });
    apiMock.triggerAlgoKillSwitch.mockResolvedValue({ data: { is_killed: false } });
    render(<KillSwitchButton />);
    await flushPolls();

    fireEvent.click(screen.getByRole('button', { name: /EMERGENCY COCKPIT KILL SWITCH/ }));
    fireEvent.change(document.getElementById('confirm-typed-input') as HTMLInputElement, {
      target: { value: 'KILL' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'EXECUTE EMERGENCY HALT' }));
    });

    expect(screen.getAllByText(/was not confirmed by the backend/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/EXECUTION ENGINES HALTED/)).toBeNull();
  });

  it('distinguishes a confirmed kill from a failed exit-all', async () => {
    apiMock.getAlgoKillSwitch.mockResolvedValue({ data: { is_killed: false, kill_level: 'NONE' } });
    apiMock.triggerAlgoKillSwitch.mockResolvedValue({
      data: { is_killed: true, kill_level: 'FULL_EXECUTION_STOP' },
    });
    apiMock.exitAllAlgoPositions.mockRejectedValue(new Error('exit gateway timeout'));
    render(<KillSwitchButton />);
    await flushPolls();

    fireEvent.click(screen.getByRole('button', { name: /EMERGENCY COCKPIT KILL SWITCH/ }));
    fireEvent.change(document.getElementById('confirm-typed-input') as HTMLInputElement, {
      target: { value: 'KILL' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'EXECUTE EMERGENCY HALT' }));
    });

    expect(screen.getByText(/Engines halted, but exiting open algo positions failed/)).toBeTruthy();
    const trigger = screen.getByRole('button', { name: /EXECUTION ENGINES HALTED/ }) as HTMLButtonElement;
    expect(trigger.disabled).toBe(true);
  });
});

describe('ExecutionModeSwitcher consent and unknown state', () => {
  it('shows UNKNOWN and blocks switching when the mode cannot be read', async () => {
    apiMock.getAlgoAccount.mockRejectedValue(new Error('backend unreachable'));
    render(<ExecutionModeSwitcher />);
    await flushPolls();

    expect(screen.getByText('MODE UNKNOWN')).toBeTruthy();
    for (const name of ['OFF', 'PAPER DESK', 'LIVE BROKER']) {
      expect((screen.getByRole('button', { name }) as HTMLButtonElement).disabled).toBe(true);
    }
  });

  it('uses the disclosure version from the API for the explicit LIVE acknowledgment', async () => {
    apiMock.getAlgoAccount.mockResolvedValue({ data: { account_id: 'a1', mode: 'PAPER' } });
    apiMock.getAlgoConsent.mockResolvedValue({
      data: {
        disclosure: { version: 'v1.0-2026-08-31', content: 'x', requires_acknowledgement: true, pre_checked: false },
        consents: [],
        current_ok: false,
      },
    });
    apiMock.setAlgoMode.mockResolvedValue({ data: { mode: 'LIVE', status: 'OK' } });
    render(<ExecutionModeSwitcher />);
    await flushPolls();

    fireEvent.click(screen.getByRole('button', { name: 'LIVE BROKER' }));
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(document.getElementById('confirm-typed-input') as HTMLInputElement, {
      target: { value: 'LIVE' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'ACKNOWLEDGE & ACTIVATE LIVE' }));
    });

    expect(apiMock.acknowledgeAlgoConsent).toHaveBeenCalledWith('v1.0-2026-08-31', true);
    expect(apiMock.setAlgoMode).toHaveBeenCalledWith('LIVE');
  });

  it('blocks LIVE activation when the disclosure version cannot be read', async () => {
    apiMock.getAlgoAccount.mockResolvedValue({ data: { account_id: 'a1', mode: 'PAPER' } });
    apiMock.getAlgoConsent.mockRejectedValue(new Error('consent service down'));
    render(<ExecutionModeSwitcher />);
    await flushPolls();

    fireEvent.click(screen.getByRole('button', { name: 'LIVE BROKER' }));
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(document.getElementById('confirm-typed-input') as HTMLInputElement, {
      target: { value: 'LIVE' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'ACKNOWLEDGE & ACTIVATE LIVE' }));
    });

    expect(screen.getByText(/Risk-disclosure version unavailable/)).toBeTruthy();
    expect(apiMock.setAlgoMode).not.toHaveBeenCalled();
  });
});

describe('ExposureGauge truth states', () => {
  it('binds real margin_utilization_pct and never falls back to placeholder values', async () => {
    apiMock.getAlgoExposure.mockResolvedValue({
      data: {
        gross_exposure_pct: 50,
        net_exposure_pct: -10,
        margin_utilization_pct: 55,
        portfolio_delta: 12.3,
      },
    });
    render(<ExposureGauge />);
    await flushPolls();

    expect(screen.getByText(/50\.0%/)).toBeTruthy();
    expect(screen.getByText(/55\.0%/)).toBeTruthy();
    expect(screen.queryByText(/34\.0%/)).toBeNull();
    expect(screen.queryByText(/28\.0%/)).toBeNull();
  });

  it('renders unavailable when the backend omits metrics', async () => {
    apiMock.getAlgoExposure.mockResolvedValue({ data: {} });
    render(<ExposureGauge />);
    await flushPolls();

    expect(screen.getAllByText(/unavailable/).length).toBeGreaterThanOrEqual(3);
  });
});

describe('SizingPreview no fabricated lots', () => {
  it('shows unavailable instead of client-side fallback lots on error', async () => {
    apiMock.previewAlgoSizing.mockRejectedValue(new Error('sizing engine down'));
    render(<SizingPreview />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Compute Volatility-Adjusted Size/ }));
    });

    expect(screen.getByText(/Sizing unavailable: sizing engine down/)).toBeTruthy();
    expect(screen.queryByText(/2 Lots/)).toBeNull();
    expect(screen.queryByText(/4,000/)).toBeNull();
  });

  it('renders engine-reported sizing', async () => {
    apiMock.previewAlgoSizing.mockResolvedValue({ data: { lots: 3, max_loss: 4500 } });
    render(<SizingPreview />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Compute Volatility-Adjusted Size/ }));
    });

    expect(screen.getByText('3 Lots')).toBeTruthy();
    expect(screen.getByText('₹4,500')).toBeTruthy();
  });
});

describe('CapitalLimitsEditor', () => {
  const capitalResponse = {
    data: {
      limit: '1000000',
      deployed: '0',
      available: '1000000',
      utilization_pct: '0',
      config: {
        investment_limit: 500000,
        max_capital_per_trade: 100000,
        max_daily_loss: 20000,
        max_loss_per_trade: 8000,
        max_open_positions: 3,
        max_trades_per_day: 10,
      },
    },
  };

  it('reads fields from config and requires confirmation with a visible result', async () => {
    apiMock.getAlgoCapital.mockResolvedValue(capitalResponse);
    apiMock.updateAlgoCapital.mockResolvedValue({ data: { updated: true } });
    render(<CapitalLimitsEditor />);
    await flushPolls();

    const investment = screen.getByLabelText('INVESTMENT CEILING (₹)') as HTMLInputElement;
    expect(investment.value).toBe('500000');

    fireEvent.change(investment, { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: /Apply & Confirm Capital Limits/ }));
    expect(apiMock.updateAlgoCapital).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'CONFIRM & APPLY LIMITS' }));
    });

    expect(apiMock.updateAlgoCapital).toHaveBeenCalledWith(
      expect.objectContaining({ investment_limit: 600000, confirm: true }),
    );
    expect(screen.getByText(/Risk mandate updated/)).toBeTruthy();
  });

  it('surfaces a rejected update instead of showing success', async () => {
    apiMock.getAlgoCapital.mockResolvedValue(capitalResponse);
    apiMock.updateAlgoCapital.mockResolvedValue({
      data: { updated: false, reason: 'exceeds mandate' },
    });
    render(<CapitalLimitsEditor />);
    await flushPolls();

    fireEvent.change(screen.getByLabelText('MAX DAILY LOSS (₹)'), { target: { value: '50000' } });
    fireEvent.click(screen.getByRole('button', { name: /Apply & Confirm Capital Limits/ }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'CONFIRM & APPLY LIMITS' }));
    });

    expect(screen.getAllByText(/refused the update: exceeds mandate/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Risk mandate updated/)).toBeNull();
  });
});

describe('ReconciliationPanel truth states', () => {
  it('does not claim SYNCHRONIZED before a reconciliation run', async () => {
    render(<ReconciliationPanel />);
    await flushPolls();

    expect(screen.queryByText('SYNCHRONIZED')).toBeNull();
    expect(screen.getByText(/results are UNKNOWN until an audit completes/)).toBeTruthy();
  });

  it('renders real discrepancy counts and engine state after a run', async () => {
    apiMock.runAlgoReconciliation.mockResolvedValue({
      data: { discrepancies: 2, engine_state: 'MISMATCH', matched_orders: 3, matched_positions: 1 },
    });
    render(<ReconciliationPanel />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Run Audit Now' }));
    });

    expect(screen.getByText('MISMATCH')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
    expect(screen.getByText('3')).toBeTruthy();
  });

  it('reports a failed reconciliation run', async () => {
    apiMock.runAlgoReconciliation.mockRejectedValue(new Error('broker gateway down'));
    render(<ReconciliationPanel />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Run Audit Now' }));
    });

    expect(screen.getByText(/Reconciliation failed: broker gateway down/)).toBeTruthy();
  });
});
