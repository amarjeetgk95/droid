'use client';

import { useEffect } from 'react';

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="flex items-center justify-center h-screen bg-background text-foreground">
        <div className="text-center p-8 max-w-md">
          <h2 className="text-2xl font-bold mb-4 text-destructive">Application Error</h2>
          <p className="text-muted-foreground mb-6">A critical error occurred that could not be handled.</p>
          <button onClick={() => reset()} className="bg-primary text-primary-foreground px-4 py-2 rounded font-medium hover:bg-primary/90 transition-colors">
            Reload Application
          </button>
        </div>
      </body>
    </html>
  );
}
