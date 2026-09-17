// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';

const nav = vi.hoisted(() => ({
  params: new URLSearchParams(''),
  replace: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => nav.params,
  useRouter: () => ({ replace: nav.replace }),
}));

import {
  decodeParam,
  encodeParam,
  useEnumQueryParam,
  useQueryParam,
  useQueryParamsWriter,
} from './urlState';

afterEach(() => {
  cleanup();
  nav.replace.mockReset();
  nav.params = new URLSearchParams('');
});

function ParamProbe({ name }: { name: string }) {
  const value = useQueryParam(name);
  return <span data-testid="value">{value === null ? '<null>' : value}</span>;
}

function EnumProbe() {
  const value = useEnumQueryParam('tab', ['signals', 'crypto'] as const, 'signals');
  return <span data-testid="value">{value}</span>;
}

function WriterProbe() {
  const write = useQueryParamsWriter();
  return (
    <button data-testid="write" onClick={() => write({ tab: 'crypto', page: null })}>
      write
    </button>
  );
}

function WriterClearProbe() {
  const write = useQueryParamsWriter();
  return (
    <button data-testid="write" onClick={() => write({ tab: null })}>
      write
    </button>
  );
}

describe('encodeParam / decodeParam round-trip', () => {
  it('survives encode -> decode', () => {
    expect(decodeParam(encodeParam('NIFTY 50'))).toBe('NIFTY 50');
    expect(decodeParam(encodeParam('a+b&c=d'))).toBe('a+b&c=d');
  });

  it('decodes form-style "+" spaces produced by URLSearchParams', () => {
    expect(decodeParam('NIFTY+50')).toBe('NIFTY 50');
    expect(decodeParam('100%25+off')).toBe('100% off');
  });

  it('handles null and malformed escapes without throwing', () => {
    expect(decodeParam(null)).toBeNull();
    expect(decodeParam('bad%E0%A4%A')).toBe('bad%E0%A4%A');
  });
});

describe('useQueryParam', () => {
  it('reads the current value and follows URL changes', async () => {
    nav.params = new URLSearchParams('symbol=NIFTY+50');
    const { getByTestId, rerender } = render(<ParamProbe name="symbol" />);
    // URLSearchParams decodes form-style "+" to a space on get().
    expect(getByTestId('value').textContent).toBe('NIFTY 50');

    nav.params = new URLSearchParams('symbol=BANKNIFTY');
    rerender(<ParamProbe name="symbol" />);
    await waitFor(() => expect(getByTestId('value').textContent).toBe('BANKNIFTY'));

    nav.params = new URLSearchParams('');
    rerender(<ParamProbe name="symbol" />);
    await waitFor(() => expect(getByTestId('value').textContent).toBe('<null>'));
  });
});

describe('useEnumQueryParam', () => {
  it('ignores values outside the allowed set and follows valid changes', async () => {
    nav.params = new URLSearchParams('tab=unknown');
    const { getByTestId, rerender } = render(<EnumProbe />);
    expect(getByTestId('value').textContent).toBe('signals');

    nav.params = new URLSearchParams('tab=crypto');
    rerender(<EnumProbe />);
    await waitFor(() => expect(getByTestId('value').textContent).toBe('crypto'));
  });
});

describe('useQueryParamsWriter', () => {
  it('merges updates and removes null params', () => {
    nav.params = new URLSearchParams('tab=signals&page=2');
    const { getByTestId } = render(<WriterProbe />);

    fireEvent.click(getByTestId('write'));

    expect(nav.replace).toHaveBeenCalledTimes(1);
    expect(nav.replace).toHaveBeenCalledWith('?tab=crypto', { scroll: false });
  });

  it('falls back to a bare "?" when all params are cleared', () => {
    nav.params = new URLSearchParams('tab=signals');
    const { getByTestId } = render(<WriterClearProbe />);

    fireEvent.click(getByTestId('write'));

    expect(nav.replace).toHaveBeenCalledWith('?', { scroll: false });
  });
});
