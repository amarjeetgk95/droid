import { describe, expect, it } from 'vitest';
import { sanitizeReturnUrl } from './returnUrl';

describe('sanitizeReturnUrl', () => {
  it('keeps same-origin relative paths with search and hash', () => {
    expect(sanitizeReturnUrl('/markets?symbol=NIFTY#depth')).toBe('/markets?symbol=NIFTY#depth');
    expect(sanitizeReturnUrl('/settings/ai')).toBe('/settings/ai');
    expect(sanitizeReturnUrl('/')).toBe('/');
  });

  it('rejects absolute external URLs', () => {
    expect(sanitizeReturnUrl('https://evil.example/phish')).toBe('/');
    expect(sanitizeReturnUrl('http://evil.example')).toBe('/');
    expect(sanitizeReturnUrl('javascript:alert(1)')).toBe('/');
    expect(sanitizeReturnUrl('data:text/html,<script>alert(1)</script>')).toBe('/');
  });

  it('rejects scheme-relative and backslash hosts', () => {
    expect(sanitizeReturnUrl('//evil.example')).toBe('/');
    expect(sanitizeReturnUrl('/\\evil.example')).toBe('/');
  });

  it('rejects dot-segment tricks that normalise to a protocol-relative path', () => {
    expect(sanitizeReturnUrl('/..//evil.example')).toBe('/');
    expect(sanitizeReturnUrl('/%2e%2e//evil.example')).toBe('/');
    expect(sanitizeReturnUrl('/foo/../..//evil')).toBe('/');
  });

  it('rejects embedded control characters but trims surrounding whitespace', () => {
    expect(sanitizeReturnUrl('/markets\nhttps://evil.example')).toBe('/');
    expect(sanitizeReturnUrl('/markets\u0000')).toBe('/');
    expect(sanitizeReturnUrl('/mar\tkets')).toBe('/');
    // Surrounding whitespace is normalised away, then the path is accepted.
    expect(sanitizeReturnUrl('/markets\t')).toBe('/markets');
    expect(sanitizeReturnUrl('  /markets  ')).toBe('/markets');
  });

  it('falls back for empty/missing input and honours a custom fallback', () => {
    expect(sanitizeReturnUrl(null)).toBe('/');
    expect(sanitizeReturnUrl(undefined)).toBe('/');
    expect(sanitizeReturnUrl('')).toBe('/');
    expect(sanitizeReturnUrl('   ')).toBe('/');
    expect(sanitizeReturnUrl('', '/desk')).toBe('/desk');
    expect(sanitizeReturnUrl('//evil.example', '/desk')).toBe('/desk');
  });

  it('cannot be tricked into changing origin via encoded separators', () => {
    // %2F%2F is a path segment, not a host: the origin must stay same-origin.
    expect(sanitizeReturnUrl('/%2F%2Fevil.example')).toBe('/%2F%2Fevil.example');
  });
});
