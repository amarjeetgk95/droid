// @vitest-environment happy-dom
import { afterEach, describe, it, expect, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { SignalChecklistCard } from './SignalChecklistCard';
import { toActiveRow, type ActiveRow } from '@/lib/signalsNormalize';

afterEach(() => cleanup());

function buildRow(overrides: Record<string, unknown> = {}): ActiveRow {
  const row = toActiveRow({
    signal_id: 'sig_0001',
    underlying: 'NIFTY',
    strategy: 'BREAKOUT',
    direction: 'BULLISH',
    status: 'TRIGGERED',
    trigger_price: 24800,
    stop_loss: 24700,
    target_1: 24900,
    target_2: 25000,
    spot_price: 24750,
    confidence01: 0.72,
    confluence_breakdown: {
      technical: 78,
      fno: 90,
      ai_status: 'AVAILABLE',
      ai: 62,
      ml_status: 'UNAVAILABLE',
    },
    option_contract: { display_symbol: 'NSE:NIFTY25818CE' },
    ...overrides,
  });
  if (!row) throw new Error('fixture failed to normalize');
  return row;
}

function noop() {}

describe('SignalChecklistCard', () => {
  it('renders the tile header, levels, lifecycle and actions', () => {
    render(
      <SignalChecklistCard
        row={buildRow()}
        now={Date.now()}
        marketClosed={false}
        busy={false}
        onOpen={noop}
        onExecute={noop}
        onDelete={noop}
      />,
    );

    expect(screen.getByText('NIFTY')).toBeDefined();
    expect(screen.getByText('NIFTY25818CE')).toBeDefined();
    expect(screen.getByText('24800.00')).toBeDefined();
    expect(screen.getByText('24700.00')).toBeDefined();
    expect(screen.getByText('Triggered')).toBeDefined();
    expect(screen.getByRole('button', { name: /^Execute/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /^Dossier/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /^Delete/ })).toBeDefined();
  });

  it('shows the outcome pill and hides Execute for a concluded signal', () => {
    render(
      <SignalChecklistCard
        row={buildRow({ status: 'TARGET_2_HIT' })}
        now={Date.now()}
        marketClosed={false}
        busy={false}
        onOpen={noop}
        onExecute={noop}
        onDelete={noop}
      />,
    );

    expect(screen.getByText('WIN')).toBeDefined();
    expect(screen.queryByRole('button', { name: /^Execute/ })).toBeNull();
    expect(screen.getByRole('button', { name: /^Delete/ })).toBeDefined();
  });

  it('renders the confluence gates and fused quant score', () => {
    render(
      <SignalChecklistCard
        row={buildRow()}
        now={Date.now()}
        marketClosed={false}
        busy={false}
        onOpen={noop}
        onExecute={noop}
        onDelete={noop}
      />,
    );

    expect(screen.getByText(/TECH 78✓/)).toBeDefined();
    expect(screen.getByText('Q72')).toBeDefined();
  });

  it('flags incomplete levels instead of hiding the signal', () => {
    render(
      <SignalChecklistCard
        row={buildRow({ trigger_price: null, stop_loss: null })}
        now={Date.now()}
        marketClosed={false}
        busy={false}
        onOpen={noop}
        onExecute={noop}
        onDelete={noop}
      />,
    );

    expect(screen.getByText(/Missing trigger, stop_loss/)).toBeDefined();
  });

  it('disables Execute while the market is closed', () => {
    render(
      <SignalChecklistCard
        row={buildRow()}
        now={Date.now()}
        marketClosed
        busy={false}
        onOpen={noop}
        onExecute={noop}
        onDelete={noop}
      />,
    );

    const execute = screen.getByRole('button', { name: /^Execute/ });
    expect((execute as HTMLButtonElement).disabled).toBe(true);
  });

  it('opens the dossier when the tile is clicked', () => {
    const onOpen = vi.fn();
    render(
      <SignalChecklistCard
        row={buildRow()}
        now={Date.now()}
        marketClosed={false}
        busy={false}
        onOpen={onOpen}
        onExecute={noop}
        onDelete={noop}
      />,
    );

    const tile = screen.getByTitle(/Open signal dossier/);
    fireEvent.click(tile);
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});