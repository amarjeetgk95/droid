'use client';

import { useEffect } from 'react';

/**
 * Root error boundary. Renders inside the root layout (html/body + providers
 * are already mounted), so the fallback must be inline content only.
 */
export default function AppError({
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
    <div className="flex min-h-[70vh] items-center justify-center bg-background text-foreground p-8">
      <div className="text-center p-8 max-w-md">
        <h2 className="text-2xl font-bold mb-4 text-destructive">Application Error</h2>
        <p className="text-muted-foreground mb-6">
          A critical error occurred that could not be handled.
        </p>
        {error?.digest ? (
          <p className="text-xs font-mono text-muted-foreground mb-6">digest: {error.digest}</p>
        ) : null}
        <button
          onClick={() => retry()}
          className="bg-primary text-primary-foreground px-4 py-2 rounded font-medium hover:bg-primary/90 transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
