'use client';

/**
 * URL-as-desk-state helpers (UI plan Phase 5).
 *
 * Precedence: URL > localStorage (lib/workspace.ts, later) > defaults.
 * Next 16 static export: useSearchParams() needs a <Suspense> boundary on
 * prerendered routes — callers render their param-reading component inside
 * <Suspense> (see page shells). All mutations use router.replace so back
 * history is not polluted by every filter change.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

/**
 * Read one query param at mount + on URL changes.
 * Usage inside a component rendered under <Suspense>.
 */
export function useQueryParam(key: string): string | null {
  const params = useSearchParams();
  const raw = params.get(key);
  const [value, setValue] = useState<string | null>(raw);

  useEffect(() => {
    setValue((params.get(key)));
  }, [params, key]);

  return value;
}

/**
 * Read one query param restricted to an allowed set.
 * Falls back to `fallback` when absent or not allowed.
 */
export function useEnumQueryParam<K extends string>(
  key: string,
  allowed: readonly K[],
  fallback: K,
): K {
  const raw = useQueryParam(key);
  return useMemo(
    () => (raw !== null && (allowed as readonly string[]).includes(raw) ? (raw as K) : fallback),
    [raw, allowed, fallback],
  );
}

/**
 * Setter that writes params back to the URL without navigating.
 * Passing null removes the param (keeps URLs clean at defaults).
 */
export function useQueryParamsWriter(): (
  updates: Record<string, string | null>,
) => void {
  const router = useRouter();
  const params = useSearchParams();

  return useCallback(
    (updates: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(updates)) {
        if (v === null) next.delete(k);
        else next.set(k, v);
      }
      const qs = next.toString();
      router.replace(qs ? `?${qs}` : '?', { scroll: false });
    },
    [params, router],
  );
}

/** Encode helpers for values that need escaping (e.g. "NIFTY 50"). */
export function encodeParam(v: string): string {
  return encodeURIComponent(v);
}
export function decodeParam(v: string | null): string | null {
  if (v === null) return null;
  try {
    return decodeURIComponent(v);
  } catch {
    return v;
  }
}
