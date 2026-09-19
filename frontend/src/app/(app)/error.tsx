'use client';

import { useEffect } from 'react';

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('App route error:', error);
  }, [error]);

  return (
    <div className="card card-pad">
      <h2 className="card-title">Module failed to render</h2>
      <p className="mt-1 text-[13px] text-ink-2">{error.message || 'Unexpected error.'}</p>
      <div className="mt-3">
        <button type="button" className="btn btn-primary" onClick={reset}>
          Retry
        </button>
      </div>
    </div>
  );
}
