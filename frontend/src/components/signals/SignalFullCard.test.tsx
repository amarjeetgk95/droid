// @vitest-environment happy-dom
import { afterEach, describe, it, expect, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { SignalFullCard } from './SignalFullCard';
import { toActiveRow, type ActiveRow } from '@/lib/signalsNormalize';

afterEach(() => cleanup());

/** Build a realistic signal row through the real normalize path. */
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
      mtf: 65,
      fno: 90,
      regime: 55,
      ai_status: 'AVAILABLE',
      ai: 62,
      ml_status: 'UNAVAILABLE',
    },
    option_contract: {
      display_symbol: 'NSE:NIFTY25818CE',
      strike: 24800,
      option_type: 'CE',
      expiry: '25 SEP',
      lot_size: 75,
    },
    timeframe: '5m',
    data_quality: 'LIVE',
    ...overrides,
  });
  if (!row) throw new Error('fixture failed to normalize');
  return row;
}

describe('SignalFullCard', () => {
  it('renders the header, hero, contract row and plan levels for a populated row', () => {
    render(<SignalFullCard row={buildRow()} />);

    expect(screen.getByText('NIFTY')).toBeDefined();
    expect(screen.getAllByText('NIFTY25818CE').length).toBeGreaterThan(0);
    expect(screen.getByText('LONG · BREAKOUT')).toBeDefined();
    expect(screen.getByText('24,750.00')).toBeDefined(); // spot
    expect(screen.getAllByText('24800.00').length).toBeGreaterThan(0); // trigger + strike
    expect(screen.getByText('24700.00')).toBeDefined(); // stop
    expect(screen.getByText('24900.00')).toBeDefined(); // T1
    expect(screen.getAllByText('TRIGGERED').length).toBeGreaterThan(0); // status pill + lifecycle
  });

  it('renders strictly the 5 chronological lifecycle stages', () => {
    render(<SignalFullCard row={buildRow({ status: 'TRIGGERED' })} />);

    expect(screen.getAllByText('Detected').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Armed').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Triggered').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Executed').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Closed').length).toBeGreaterThan(0);
  });

  it('renders No data instead of fabricated levels when the row is sparse', () => {
    render(
      <SignalFullCard
        row={buildRow({
          trigger_price: null,
          stop_loss: null,
          target_1: null,
          target_2: null,
          spot_price: null,
          option_contract: null,
        })}
      />,
    );

    expect(screen.getAllByText('No data').length).toBeGreaterThan(0);
  });

  it('renders the validation gates + fused quant score from real confluence data', () => {
    render(<SignalFullCard row={buildRow()} />);

    expect(screen.getByText(/TECH 78✓/)).toBeDefined();
    expect(screen.getByText(/MTF 65✓/)).toBeDefined();
    expect(screen.getByText('Q72')).toBeDefined();
    // Unavailable ML advisor renders hollow, not passing.
    expect(screen.getByText('ML ○')).toBeDefined();
  });

  it('renders No data when the validation stack is absent', () => {
    render(
      <SignalFullCard
        row={buildRow({
          confidence01: null,
          confluence_breakdown: null,
        })}
      />,
    );

    expect(screen.getByText(/validation stack unavailable/)).toBeDefined();
  });

  it('disables Execute when the market is closed', () => {
    const onExecute = vi.fn();
    render(<SignalFullCard row={buildRow()} marketClosed onExecute={onExecute} />);

    const execute = screen.getByRole('button', { name: /Execute Paper Order/ });
    expect((execute as HTMLButtonElement).disabled).toBe(true);
  });

  it('hides the execute strip when no callback is wired', () => {
    render(<SignalFullCard row={buildRow()} />);

    expect(screen.queryByRole('button', { name: /Execute Paper Order/ })).toBeNull();
  });
});