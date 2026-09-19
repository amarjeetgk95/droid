// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

const setInstrument = vi.fn();

vi.mock('@/context/InstrumentContext', () => ({
  useInstrument: () => ({ instrument: 'NIFTY', setInstrument }),
}));

vi.mock('@/context/AppStreamContext', () => ({
  useCommandSection: () => ({
    value: {
      cards: [
        { symbol: 'NIFTY 50', ltp: 24185.3, change: 101.2, change_percent: 0.42 },
        { symbol: 'BANKNIFTY', ltp: 52100.5, change: -80.1, change_percent: -0.15 },
      ],
    },
  }),
}));

import { InstrumentPicker } from './InstrumentPicker';

afterEach(() => {
  cleanup();
  setInstrument.mockReset();
});

describe('InstrumentPicker', () => {
  it('renders one tab per instrument with the live quote', () => {
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
});
