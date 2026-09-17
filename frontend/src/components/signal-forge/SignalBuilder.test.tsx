// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const { getSignalEnginesMock, generateSignalMock } = vi.hoisted(() => ({
  getSignalEnginesMock: vi.fn(),
  generateSignalMock: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: {
    getSignalEngines: getSignalEnginesMock,
    generateSignal: generateSignalMock,
    autoDetectSignal: vi.fn(),
  },
}));

import { SignalBuilder } from './SignalBuilder';

const ENGINES = {
  approved_universe: ['NIFTY'],
  broker: 'FYERS API v3',
  strategies: [{ id: 'BREAKOUT', label: 'Institutional Breakout' }],
};

const SUCCESS = {
  success: true,
  signal: { signal_id: 'SIG-1', fsm_state: 'ARMED' },
  paper_order: null,
  paper_status: 'SKIPPED',
  telegram: { enqueued: 2, status: 'SENT' },
  deduplicated: false,
};

function fillLevels() {
  fireEvent.change(screen.getByLabelText('TRIGGER ENTRY (₹)'), { target: { value: '24360' } });
  fireEvent.change(screen.getByLabelText('STOP LOSS (₹)'), { target: { value: '24320' } });
  fireEvent.change(screen.getByLabelText('TARGET 1 (₹)'), { target: { value: '24420' } });
  fireEvent.change(screen.getByLabelText('TARGET 2 (₹)'), { target: { value: '24470' } });
}

function submitReview() {
  const button = screen.getByRole('button', { name: /REVIEW & GENERATE SIGNAL/ });
  const form = button.closest('form');
  if (!form) throw new Error('form not found');
  fireEvent.submit(form);
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('SignalBuilder publish flow', () => {
  it('blocks submit on empty levels instead of coercing them to 0', async () => {
    getSignalEnginesMock.mockResolvedValue(ENGINES);
    render(<SignalBuilder underlying="NIFTY" />);
    await waitFor(() => expect(screen.getByText('Engine: Institutional Breakout')).toBeTruthy());

    submitReview();

    expect(generateSignalMock).not.toHaveBeenCalled();
    expect(screen.getByText('Fix the invalid levels before generating.')).toBeTruthy();
    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0);
  });

  it('requires an explicit confirm with the exact payload and sends one idempotent request', async () => {
    getSignalEnginesMock.mockResolvedValue(ENGINES);
    generateSignalMock.mockResolvedValue(SUCCESS);
    render(<SignalBuilder underlying="NIFTY" />);
    await waitFor(() => expect(screen.getByText('Engine: Institutional Breakout')).toBeTruthy());

    fillLevels();
    submitReview();

    expect(screen.getByText('CONFIRM & ARM — REVIEW EXACT PAYLOAD')).toBeTruthy();
    expect(screen.getByText('24360')).toBeTruthy();
    expect(screen.getByText('24320')).toBeTruthy();
    expect(screen.getByText('LONG_CALL')).toBeTruthy();
    expect(generateSignalMock).not.toHaveBeenCalled();

    const confirm = screen.getByRole('button', { name: /CONFIRM & ARM SIGNAL/ });
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    await waitFor(() => expect(generateSignalMock).toHaveBeenCalledTimes(1));
    const [payload, opts] = generateSignalMock.mock.calls[0];
    expect(payload.trigger_level).toBe(24360);
    expect(payload.stop_loss).toBe(24320);
    expect(payload.target_1).toBe(24420);
    expect(payload.target_2).toBe(24470);
    expect(payload.direction).toBe('LONG_CALL');
    expect(payload.strategy).toBe('BREAKOUT');
    expect(payload.notify_telegram).toBe(true);
    expect('risk_percent' in payload).toBe(false);
    expect(typeof payload.idempotency_key).toBe('string');
    expect(opts.idempotencyKey).toBe(payload.idempotency_key);

    await waitFor(() => expect(screen.getAllByText(/SIGNAL SIG-1/).length).toBeGreaterThan(0));
    expect(screen.getByText(/Telegram: SENT/)).toBeTruthy();

    // A subsequent edit clears the success outcome.
    fireEvent.change(screen.getByLabelText('TRIGGER ENTRY (₹)'), { target: { value: '24365' } });
    expect(screen.queryByText(/SIGNAL SIG-1/)).toBeNull();
  });
});

