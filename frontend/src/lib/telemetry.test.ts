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
});
