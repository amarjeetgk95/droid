import { describe, expect, it } from 'vitest';
import {
  EXIT_REASONS,
  exitReasonLabel,
  pnlTone,
  pnlToneClass,
  signedINR,
  signedPct,
  signedR,
} from './swingUtils';

describe('swing P&L formatting', () => {
  it('signs currency from the value, not a >= 0 boolean', () => {
    expect(signedINR(1250.5)).toBe('+₹1,250.5');
    expect(signedINR(-1250.5)).toBe('-₹1,250.5');
    expect(signedINR(0)).toBe('₹0');
  });

  it('renders an explicit unavailable marker for non-finite input', () => {
    expect(signedINR(Number.NaN)).toBe('—');
    expect(signedINR(undefined)).toBe('—');
    expect(signedINR(null)).toBe('—');
    expect(signedINR('')).toBe('—');
    expect(signedPct(Number.POSITIVE_INFINITY)).toBe('—');
    expect(signedR(undefined)).toBe('—');
  });

  it('signs percentages and R multiples independently', () => {
    expect(signedPct(2.34)).toBe('+2.3%');
    expect(signedPct(-2.34)).toBe('-2.3%');
    expect(signedPct(0)).toBe('0.0%');
    expect(signedR(1.5)).toBe('+1.5R');
    expect(signedR(-0.75)).toBe('-0.8R');
    expect(signedR(0)).toBe('0.0R');
  });

  it('treats a flat return as neutral, never green', () => {
    expect(pnlTone(0)).toBe('flat');
    expect(pnlToneClass(0)).toBe('text-muted-foreground');
    expect(pnlTone(-0)).toBe('flat');
    expect(pnlTone(null)).toBe('flat');
    expect(pnlTone(0.01)).toBe('up');
    expect(pnlTone(-0.01)).toBe('down');
    expect(pnlToneClass(10)).toBe('text-up');
    expect(pnlToneClass(-10)).toBe('text-down');
  });
});

describe('swing exit reason labels', () => {
  it('maps structured enums to human labels', () => {
    expect(exitReasonLabel('TARGET_1')).toBe('Target 1 Hit (+1.5R)');
    expect(exitReasonLabel('MANUAL_EXIT')).toBe('Manual Exit');
    expect(exitReasonLabel('TIME_STOP')).toBe('Mandatory 15:15 IST Time Stop');
  });

  it('passes unknown enums through raw and marks missing ones unavailable', () => {
    expect(exitReasonLabel('CUSTOM_REASON')).toBe('CUSTOM_REASON');
    expect(exitReasonLabel(null)).toBe('—');
    expect(exitReasonLabel(undefined)).toBe('—');
  });

  it('keeps every structured select option labelled', () => {
    for (const reason of EXIT_REASONS) {
      expect(reason.label.length).toBeGreaterThan(0);
      expect(exitReasonLabel(reason.value)).toBe(reason.label);
    }
  });
});
