// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, it, expect } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { SignalFullCard } from './SignalFullCard';

afterEach(() => cleanup());

const DEMO_GATES = [
  { name: 'Strategy', score: 92, maxScore: 100, status: 'PASS' as const },
  { name: 'Tech Gates', score: 91, maxScore: 100, status: 'PASS' as const },
  { name: 'ML Model', score: 84, maxScore: 100, status: 'PASS' as const },
  { name: 'AI Confl.', score: 88, maxScore: 100, status: 'PASS' as const },
  { name: 'History', score: 79, maxScore: 100, status: 'PASS' as const },
  { name: 'Risk Eng.', score: 86, maxScore: 100, status: 'PASS' as const },
];

describe('SignalFullCard', () => {
  it('renders the institutional header, contract and hero banner for NIFTY 50', () => {
    render(
      <SignalFullCard
        underlying="NIFTY 50"
        direction="BULLISH"
        strategy="BREAKOUT"
        timeframe="1M"
        entryPrice={120.5}
        target1={145.0}
        target2={160.0}
        stopLoss={95.0}
        spotPrice={24854.3}
        spotChange={72.45}
        spotChangePct={0.29}
        contractSymbol="NIFTY 25 SEP 24850 CE"
        contractMoneyness="ATM"
        thesis="Momentum continuation above opening range high"
        keyReason="Price broke above opening range high."
        keyReasonBullets={['Bullish structure']}
        tradeNotes={['Trail SL to breakeven.']}
        validationGates={DEMO_GATES}
      />,
    );

    expect(screen.getByText('NIFTY 50')).toBeDefined();
    expect(screen.getByText('NSE')).toBeDefined();
    expect(screen.getByText('LIVE SIGNAL')).toBeDefined();
    expect(screen.getByText('BUY · BREAKOUT LONG')).toBeDefined();
    expect(screen.getByText('₹120.50')).toBeDefined();
    expect(screen.getByText('₹145.00')).toBeDefined();
    expect(screen.getByText('₹160.00')).toBeDefined();
    expect(screen.getByText('₹95.00')).toBeDefined();
  });

  it('renders strictly the 5 chronological lifecycle stages', () => {
    render(
      <SignalFullCard
        underlying="NIFTY 50"
        direction="BULLISH"
        strategy="BREAKOUT"
        currentState="TRIGGERED"
      />,
    );

    expect(screen.getByText('Detected')).toBeDefined();
    expect(screen.getByText('Armed')).toBeDefined();
    expect(screen.getByText('Triggered')).toBeDefined();
    expect(screen.getByText('Executed')).toBeDefined();
    expect(screen.getByText('Closed')).toBeDefined();
    expect(screen.getByText('Current: TRIGGERED')).toBeDefined();
  });

  it('renders No data and disables Execute when levels are missing', () => {
    render(
      <SignalFullCard
        underlying="NIFTY 50"
        direction="BULLISH"
        strategy="BREAKOUT"
      />,
    );

    expect(screen.getAllByText('No data').length).toBeGreaterThan(0);
    const execute = screen.getByRole('button', { name: /Execute Paper Order/ });
    expect((execute as HTMLButtonElement).disabled).toBe(true);
  });

  it('calculates rupee return per lot accurately for NIFTY 75 lot size', () => {
    render(
      <SignalFullCard
        underlying="NIFTY"
        direction="BULLISH"
        strategy="BREAKOUT"
        entryPrice={120.5}
        target1={145.0}
        target2={160.0}
        stopLoss={95.0}
      />,
    );

    expect(screen.getByText(/\+₹1,83[78]\/lot/)).toBeDefined();
    expect(screen.getByText(/-₹1,91[23]\/lot/)).toBeDefined();
  });

  it('renders all 6 Droid Validation Stack gates and quant score', () => {
    render(
      <SignalFullCard
        underlying="NIFTY 50"
        direction="BULLISH"
        strategy="BREAKOUT"
        quantScore={85}
        validationGates={DEMO_GATES}
      />,
    );

    expect(screen.getByText('Droid Validation Stack')).toBeDefined();
    expect(screen.getByText('Strategy')).toBeDefined();
    expect(screen.getByText('Tech Gates')).toBeDefined();
    expect(screen.getByText('ML Model')).toBeDefined();
    expect(screen.getByText('AI Confl.')).toBeDefined();
    expect(screen.getByText('History')).toBeDefined();
    expect(screen.getByText('Risk Eng.')).toBeDefined();
    expect(screen.getByText('85 / 100')).toBeDefined();
  });

  it('renders No data for a missing validation stack instead of invented scores', () => {
    render(
      <SignalFullCard
        underlying="NIFTY 50"
        direction="BULLISH"
        strategy="BREAKOUT"
      />,
    );

    expect(screen.getByText('Droid Validation Stack')).toBeDefined();
    expect(screen.getByText(/validation stack unavailable/)).toBeDefined();
  });
});
