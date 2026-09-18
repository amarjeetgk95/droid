// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ScannerPanel, type ScannerData } from './ScannerPanel';

afterEach(() => cleanup());

const scannerData: ScannerData = {
  scanned_underlyings: ['NIFTY', 'BANKNIFTY'],
  total_candidates: 3,
  new_signals: [
    {
      id: 'sig-1',
      underlying: 'NIFTY',
      strategy: 'SCALP_BREAKOUT',
      direction: 'BULLISH',
      trigger_price: 25000,
      stop_loss: 24900,
      target_1: 25200,
    },
  ],
  active_signals: [{}, {}],
  timestamp_ms: 1,
};

describe('ScannerPanel', () => {
  it('renders counts, scanned underlyings and candidate rows from fixed props', () => {
    render(
      <ScannerPanel
        scannerData={scannerData}
        scannerLoading={false}
        scannerError={null}
        onScan={vi.fn()}
      />,
    );

    expect(screen.getByText('3')).toBeTruthy();
    expect(screen.getByText('1')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
    expect(screen.getByText('NIFTY, BANKNIFTY')).toBeTruthy();
    expect(screen.getByText('NIFTY')).toBeTruthy();
    expect(screen.getByText('scalp breakout')).toBeTruthy();
    expect(screen.getByText('LONG')).toBeTruthy();
    expect(screen.getByText('₹25,000')).toBeTruthy();
    expect(screen.getByText('₹24,900')).toBeTruthy();
    expect(screen.getByText('₹25,200')).toBeTruthy();
    expect(screen.getByText('NEW CANDIDATE')).toBeTruthy();
  });

  it('fires onScan from the Scan Now button', () => {
    const onScan = vi.fn();
    render(
      <ScannerPanel
        scannerData={null}
        scannerLoading={false}
        scannerError={null}
        onScan={onScan}
      />,
    );

    expect(screen.getByText(/Click "Scan Now"/i)).toBeTruthy();
    expect(screen.queryByText('NEW CANDIDATE')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Scan Now/i }));
    expect(onScan).toHaveBeenCalledTimes(1);
  });

  it('shows the error state and disables the button while loading', () => {
    render(
      <ScannerPanel
        scannerData={null}
        scannerLoading
        scannerError="scanner backend unreachable"
        onScan={vi.fn()}
      />,
    );

    expect(screen.getByText('scanner backend unreachable')).toBeTruthy();
    const scan = screen.getByRole('button', { name: /Scanning/i }) as HTMLButtonElement;
    expect(scan.disabled).toBe(true);
  });

  it('only renders Auto-Detect when a handler is provided', async () => {
    const onAutoDetect = vi.fn(async () => {});
    const { rerender } = render(
      <ScannerPanel
        scannerData={null}
        scannerLoading={false}
        scannerError={null}
        onScan={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: /Auto-Detect/ })).toBeNull();

    rerender(
      <ScannerPanel
        scannerData={null}
        scannerLoading={false}
        scannerError={null}
        onScan={vi.fn()}
        onAutoDetect={onAutoDetect}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Auto-Detect/ }));
    await waitFor(() => expect(onAutoDetect).toHaveBeenCalledTimes(1));
  });
});
