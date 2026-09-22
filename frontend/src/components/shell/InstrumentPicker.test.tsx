// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

const { marketSection, marketTicks, setInstrument } = vi.hoisted(() => ({
  setInstrument: vi.fn(),
  marketSection: { value: null as unknown },
  marketTicks: {
    latestTicks: {} as Record<string, unknown>,
    ticksFresh: false,
  },
}));

vi.mock('@/context/InstrumentContext', () => ({
  useInstrument: () => ({ instrument: 'NIFTY', setInstrument }),
}));

vi.mock('@/context/AppStreamContext', () => ({
  useCommandSection: () => marketSection,
}));

vi.mock('@/context/MarketTicksContext', () => ({
  useMarketTicks: () => marketTicks,
}));

import { InstrumentPicker } from './InstrumentPicker';

function card(symbol: string, ltp: number, changePercent = 0.42) {
  return {
    symbol,
    display_name: symbol,
    ltp,
    change: 1,
    change_percent: changePercent,
    open: ltp,
    high: ltp,
    low: ltp,
    previous_close: ltp,
    volume: 0,
    open_interest: null,
    sparkline: [],
    status: 'LIVE',
    timestamp: null,
    provider: 'fyers',
  };
}

function tick(symbol: string, ltp: number, receivedAt = Date.now(), close?: number) {
  return { symbol, ltp, received_at: receivedAt, ...(close != null ? { close } : {}) };
}

beforeEach(() => {
  marketSection.value = {
    cards: [card('NIFTY 50', 24185.3), card('BANKNIFTY', 52100.5, -0.15)],
  };
  marketTicks.latestTicks = {};
  marketTicks.ticksFresh = false;
});

afterEach(() => {
  cleanup();
  setInstrument.mockReset();
});

describe('InstrumentPicker', () => {
  it('renders one tab per switchable instrument with the live quote', () => {
    render(<InstrumentPicker />);

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      expect.stringContaining('NIFTY'),
      expect.stringContaining('BANKNIFTY'),
      expect.stringContaining('SENSEX'),
    ]);
    expect(screen.getByText(/24,185/)).toBeTruthy();
    expect(screen.getByText('+0.42%')).toBeTruthy();
    expect(screen.getByText('-0.15%')).toBeTruthy();
  });

  it('selects an instrument on click', () => {
    render(<InstrumentPicker />);
    fireEvent.click(screen.getAllByRole('tab')[1]);
    expect(setInstrument).toHaveBeenCalledWith('BANKNIFTY');
  });

  it('moves selection and focus with the arrow keys', () => {
    render(<InstrumentPicker />);
    const tabs = screen.getAllByRole('tab');

    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' });
    expect(setInstrument).toHaveBeenLastCalledWith('BANKNIFTY');
    expect(document.activeElement).toBe(tabs[1]);

    fireEvent.keyDown(tabs[1], { key: 'End' });
    expect(setInstrument).toHaveBeenLastCalledWith('SENSEX');

    fireEvent.keyDown(tabs[2], { key: 'Home' });
    expect(setInstrument).toHaveBeenLastCalledWith('NIFTY');

    fireEvent.keyDown(tabs[0], { key: 'ArrowLeft' });
    expect(setInstrument).toHaveBeenLastCalledWith('SENSEX');
  });

  it('shows INDIAVIX as a readout, not a tab, and ignores other indices', () => {
    marketSection.value = {
      cards: [
        card('NIFTY 50', 24185.3),
        card('BANKNIFTY', 52100.5),
        card('FINNIFTY', 56642.55, 0.31),
        card('INDIA VIX', 11.21, -2.4),
      ],
    };
    render(<InstrumentPicker />);

    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.getByText('INDIAVIX')).toBeTruthy();
    expect(screen.getByText('11.21')).toBeTruthy();
    expect(screen.getByText('-2.40%')).toBeTruthy();
    expect(screen.queryByText('FINNIFTY')).toBeNull();
  });

  it('reserves the full expanded strip before any quote arrives', () => {
    marketSection.value = { cards: [] };
    render(<InstrumentPicker />);

    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.getByText('INDIAVIX')).toBeTruthy();
    expect(screen.getAllByText('—')).toHaveLength(4);
    expect(screen.queryByText('FINNIFTY')).toBeNull();
  });

  it('derives change % from the tick so quotes are complete before cards load', () => {
    marketSection.value = { cards: [] };
    marketTicks.ticksFresh = true;
    marketTicks.latestTicks = {
      'NIFTY 50': tick('NIFTY 50', 24201.4, Date.now(), 24100),
    };
    render(<InstrumentPicker />);

    expect(screen.getByText('24,201.40')).toBeTruthy();
    expect(screen.getByText('+0.42%')).toBeTruthy();
  });

  it('never lets a VIX tick overwrite the NIFTY quote', () => {
    marketTicks.ticksFresh = true;
    marketTicks.latestTicks = {
      'INDIA VIX': tick('INDIA VIX', 11.21),
      'NIFTY 50': tick('NIFTY 50', 24201.4),
    };
    render(<InstrumentPicker />);

    const niftyTab = screen.getAllByRole('tab')[0];
    expect(niftyTab.textContent).toContain('24,201.40');
    expect(niftyTab.textContent).not.toContain('11.21');
    expect(screen.getByText('11.21')).toBeTruthy();
  });

  it('ignores stale ticks and unknown symbols', () => {
    marketTicks.ticksFresh = true;
    marketTicks.latestTicks = {
      'INDIA VIX': tick('INDIA VIX', 11.21, Date.now() - 30_000),
      USDINR: tick('USDINR', 83.2),
    };
    render(<InstrumentPicker />);

    expect(screen.queryByText('11.21')).toBeNull();
    expect(screen.queryByText('83.20')).toBeNull();
    expect(screen.getByText(/24,185/)).toBeTruthy();
  });
});
