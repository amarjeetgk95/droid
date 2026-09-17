// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from 'vitest';
import {
  AUTH_NOTICE_STORAGE_KEY,
  DEFAULT_AUTH_ERROR,
  getAuthErrorMessage,
  readAuthNotice,
  writeAuthNotice,
} from './authMessages';

describe('getAuthErrorMessage', () => {
  it('maps network failures to a human sentence', () => {
    expect(getAuthErrorMessage(new Error('Failed to fetch'))).toMatch(/Cannot reach the authentication service/);
    expect(getAuthErrorMessage(new Error('TypeError: Failed to fetch'))).toMatch(
      /Cannot reach the authentication service/,
    );
    expect(getAuthErrorMessage({ message: 'NetworkError when attempting to fetch resource.' })).toMatch(
      /Cannot reach the authentication service/,
    );
  });

  it('maps the common Supabase failures', () => {
    expect(getAuthErrorMessage(new Error('Email not confirmed'))).toMatch(/has not been verified/);
    expect(getAuthErrorMessage(new Error('Invalid login credentials'))).toBe('Incorrect email or password.');
    expect(getAuthErrorMessage(new Error('User already registered'))).toMatch(/already exists/);
    expect(getAuthErrorMessage(new Error('Signups not allowed for this instance'))).toMatch(/disabled/);
    expect(getAuthErrorMessage(new Error('User not found'))).toMatch(/No account exists/);
    expect(getAuthErrorMessage(new Error('Email link is invalid or has expired'))).toMatch(/invalid or has expired/);
    expect(getAuthErrorMessage(new Error('Auth session missing!'))).toMatch(/session has expired/);
    expect(getAuthErrorMessage(new Error('Password should be at least 6 characters'))).toBe(
      'Password must be at least 6 characters long.',
    );
  });

  it('strips technical prefixes and keeps unknown-but-readable messages', () => {
    expect(getAuthErrorMessage(new Error('AuthApiError: Password is too short'))).toBe('Password is too short');
  });

  it('falls back for empty/unknown input and is idempotent on mapped copy', () => {
    expect(getAuthErrorMessage(null)).toBe(DEFAULT_AUTH_ERROR);
    expect(getAuthErrorMessage('')).toBe(DEFAULT_AUTH_ERROR);
    expect(getAuthErrorMessage(new Error('Failed to fetch'), 'custom')).toMatch(/Cannot reach/);

    const once = getAuthErrorMessage(new Error('Invalid login credentials'));
    expect(getAuthErrorMessage(new Error(once))).toBe(once);
  });
});

describe('auth notices', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('round-trips a notice and clears it on read', () => {
    writeAuthNotice('logout_incomplete');
    expect(readAuthNotice()).toBe('logout_incomplete');
    expect(readAuthNotice()).toBeNull();
  });

  it('ignores stale or malformed notices', () => {
    sessionStorage.setItem(
      AUTH_NOTICE_STORAGE_KEY,
      JSON.stringify({ kind: 'logout_incomplete', at: Date.now() - 120_000 }),
    );
    expect(readAuthNotice()).toBeNull();

    sessionStorage.setItem(AUTH_NOTICE_STORAGE_KEY, 'not-json');
    expect(readAuthNotice()).toBeNull();

    sessionStorage.setItem(
      AUTH_NOTICE_STORAGE_KEY,
      JSON.stringify({ kind: 'not_a_kind', at: Date.now() }),
    );
    expect(readAuthNotice()).toBeNull();
  });
});
