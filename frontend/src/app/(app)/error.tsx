'use client';

import { useEffect } from 'react';
import { TriangleAlert } from 'lucide-react';

/**
 * (app) segment error boundary. Renders inside AppShell's scrollable <main>,
 * so it uses a min-height panel (never html/body) and Next 16's `retry()`.
 */
export default function ErrorBoundary({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div
      role="alert"
      className="flex min-h-[60vh] flex-col items-center justify-center rounded-lg border border-border bg-card p-8 text-center"
    >
      <div className="mb-4 text-down-strong">
        <TriangleAlert className="h-12 w-12" aria-hidden />
      </div>
      <h2 className="mb-2 text-xl font-bold text-foreground">Desk failed to render</h2>
      <p className="mb-4 max-w-md text-sm text-ink-2">
        An unexpected error occurred in this view. The shell and other desks remain available.
      </p>
      {error?.message ? (
        <details className="mb-6 max-w-md rounded border border-border bg-secondary/50 px-3 py-2 text-left font-mono text-xs text-ink-2">
          <summary className="cursor-pointer select-none">Technical details</summary>
          <p className="mt-2 break-all whitespace-pre-wrap">{error.message}</p>
          {error?.digest ? <p className="mt-1 opacity-70">digest: {error.digest}</p> : null}
        </details>
      ) : null}
      <button
        type="button"
        onClick={() => retry()}
        className="rounded bg-primary px-4 py-2 font-medium text-primary-foreground transition-colors hover:bg-primary/90"
      >
        Try again
      </button>
    </div>
  );
}
