"use client";

/**
 * Lightweight query-param state without next/navigation Suspense overhead.
 * Reads initial value from window.location.search, writes via history.replaceState.
 */

export function getQueryParam(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return new URLSearchParams(window.location.search).get(key);
  } catch {
    return null;
  }
}

export function setQueryParams(params: Record<string, string | null | undefined>) {
  if (typeof window === "undefined") return;
  try {
    const url = new URL(window.location.href);
    for (const [k, v] of Object.entries(params)) {
      if (v == null || v === "") url.searchParams.delete(k);
      else url.searchParams.set(k, v);
    }
    window.history.replaceState(null, "", `${url.pathname}?${url.searchParams.toString()}${url.hash}`);
  } catch {
    // ignore — URL persistence is best-effort
  }
}
