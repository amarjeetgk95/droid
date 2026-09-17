import { describe, expect, it } from 'vitest';
import { errorMessage } from './errors';

describe('errorMessage', () => {
  it('prefers a non-empty Error message', () => {
    expect(errorMessage(new Error('boom'), 'fallback')).toBe('boom');
    expect(errorMessage(new Error(''), 'fallback')).toBe('fallback');
  });

  it('accepts a non-blank thrown string', () => {
    expect(errorMessage('direct', 'fallback')).toBe('direct');
    expect(errorMessage('   ', 'fallback')).toBe('fallback');
  });

  it('falls back to the caller text, or the canonical default', () => {
    expect(errorMessage({ nope: true }, 'sizing unavailable')).toBe('sizing unavailable');
    expect(errorMessage(undefined)).toBe('Unexpected error');
    expect(errorMessage(42)).toBe('Unexpected error');
  });
});
