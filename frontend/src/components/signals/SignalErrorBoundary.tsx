'use client';

import React from 'react';
import { AlertTriangle } from 'lucide-react';

type Props = { children: React.ReactNode; label?: string };
type State = { error: string | null };

/** Per-widget boundary so one malformed signal never unmounts the whole grid. */
export class SignalErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(err: unknown): State {
    return { error: err instanceof Error ? err.message : 'Render failed' };
  }

  componentDidCatch() {
    // Intentionally silent — per-card fallback UI is the recovery path.
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-xs">
          <p className="font-semibold text-destructive flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> {this.props.label || 'Signal'} failed to render
          </p>
          <p className="text-muted-foreground mt-1 font-mono break-words">{this.state.error.slice(0, 200)}</p>
          <button
            onClick={() => this.setState({ error: null })}
            className="mt-2 px-2 py-1 text-[11px] border rounded hover:bg-secondary"
          >
            Retry render
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
