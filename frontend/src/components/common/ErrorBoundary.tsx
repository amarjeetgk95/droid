'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** Optional custom fallback UI. */
  fallback?: ReactNode;
  /** Optional label used in the default fallback card. */
  label?: string;
}

interface State {
  hasError: boolean;
}

/**
 * Small per-widget error boundary — one broken card no longer unmounts the
 * whole dashboard tree.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[ErrorBoundary]${this.props.label ? ` (${this.props.label})` : ''}`, error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="bg-card rounded-lg border border-destructive/30 p-4 h-48 flex flex-col items-center justify-center gap-2">
          <p className="text-sm font-semibold text-destructive">Widget failed to render</p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="text-xs px-3 py-1 rounded-md bg-secondary hover:bg-secondary/80 text-foreground transition-colors cursor-pointer"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;