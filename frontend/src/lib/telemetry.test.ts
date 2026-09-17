import { describe, expect, it } from 'vitest';
import { clearTelemetry, getRecentErrors, getRecentVitals, reportError, reportWebVital } from './telemetry';

describe('telemetry buffers', () => {
  it('buffers errors newest-first with a cap', () => {
    clearTelemetry();
    reportError(new Error('boom'), { label: 'TestWidget' });
    reportError('string failure');
    const recent = getRecentErrors(10);
    expect(recent).toHaveLength(2);
    expect(recent[0].message).toBe('string failure');
    expect(recent[1].label).toBe('TestWidget');
  });

  it('buffers web vitals', () => {
    clearTelemetry();
    reportWebVital({ name: 'LCP', value: 1234, rating: 'good' });
    expect(getRecentVitals()[0]).toMatchObject({ name: 'LCP', value: 1234 });
  });

  it('returns an empty list for non-positive limits', () => {
    clearTelemetry();
    reportError(new Error('x'));
    reportWebVital({ name: 'CLS', value: 0.01 });

    expect(getRecentErrors(0)).toEqual([]);
    expect(getRecentErrors(-5)).toEqual([]);
    expect(getRecentVitals(0)).toEqual([]);
    expect(getRecentVitals(-1)).toEqual([]);
  });

  it('caps the ring buffer at 50 entries, newest first', () => {
    clearTelemetry();
    for (let i = 0; i < 60; i++) reportError(`e${i}`);

    const recent = getRecentErrors(100);
    expect(recent).toHaveLength(50);
    expect(recent[0].message).toBe('e59');
    expect(recent[49].message).toBe('e10');
  });
});
