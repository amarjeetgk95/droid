'use client';

import React, { Component, type ReactNode } from 'react';
import { ShieldAlert, RefreshCw, Power } from 'lucide-react';
import { executeEmergencyKill } from './AlgoControlWidget';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  killing: boolean;
  killStatus: string | null;
  killSuccess: boolean;
}

export class WarRoomErrorBoundary extends Component<Props, State> {
  public override state: State = {
    hasError: false,
    error: null,
    killing: false,
    killStatus: null,
    killSuccess: false,
  };

  public static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  public override componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('WarRoom crash caught by WarRoomErrorBoundary:', error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null, killStatus: null });
  };

  private handleEmergencyKill = async () => {
    this.setState({ killing: true, killStatus: 'Triggering emergency kill switch...' });
    try {
      const res = await executeEmergencyKill(3, (attempt) => {
        this.setState({ killStatus: `Executing kill switch (attempt ${attempt}/3)...` });
      });
      if (res.success) {
        this.setState({ killing: false, killSuccess: true, killStatus: 'Kill switch confirmed by backend. Engine halted.' });
      } else {
        this.setState({ killing: false, killSuccess: false, killStatus: `FAILED: ${res.error || 'Unknown error'}` });
      }
    } catch (err) {
      this.setState({
        killing: false,
        killSuccess: false,
        killStatus: `FAILED: ${err instanceof Error ? err.message : String(err)}`,
      });
    }
  };

  public override render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          style={{
            background: 'var(--ds-page)',
            color: 'var(--ds-ink)',
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 24,
          }}
        >
          <div
            style={{
              maxWidth: 580,
              width: '100%',
              background: 'var(--ds-surface)',
              border: '1px solid var(--ds-bear)',
              borderRadius: 12,
              padding: 28,
              boxShadow: 'var(--ds-shadow-lg)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <ShieldAlert style={{ width: 28, height: 28, color: 'var(--ds-bear)' }} />
              <div>
                <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>War Room Desk Crash Protected</h1>
                <p style={{ margin: 0, fontSize: 12, color: 'var(--ds-text-secondary)' }}>
                  A runtime error halted the UI. Fail-safe controls remain accessible.
                </p>
              </div>
            </div>

            {/* Emergency Kill Switch Fallback */}
            <div
              style={{
                background: 'var(--ds-bear-wash)',
                border: '1px solid var(--ds-bear-line)',
                borderRadius: 8,
                padding: 16,
                marginBottom: 20,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--ds-bear-strong)' }}>Emergency Kill Switch</div>
                  <div style={{ fontSize: 11, color: 'var(--ds-text-secondary)' }}>
                    Halt all algo executions and cancel active orders immediately.
                  </div>
                </div>
                <button
                  type="button"
                  disabled={this.state.killing || this.state.killSuccess}
                  onClick={() => void this.handleEmergencyKill()}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '8px 14px',
                    background: this.state.killSuccess ? 'var(--ds-bull)' : 'var(--ds-bear-action)',
                    color: 'var(--ds-surface)',
                    border: 'none',
                    borderRadius: 6,
                    fontWeight: 700,
                    fontSize: 12,
                    cursor: this.state.killing || this.state.killSuccess ? 'not-allowed' : 'pointer',
                  }}
                >
                  <Power style={{ width: 14, height: 14 }} />
                  {this.state.killing ? 'KILLING…' : this.state.killSuccess ? 'KILLED' : 'KILL ALL'}
                </button>
              </div>
              {this.state.killStatus ? (
                <div
                  style={{
                    marginTop: 10,
                    fontSize: 11,
                    fontFamily: 'monospace',
                    color: this.state.killSuccess ? 'var(--ds-bull-strong)' : 'var(--ds-bear-strong)',
                  }}
                >
                  {this.state.killStatus}
                </div>
              ) : null}
            </div>

            {/* Error message */}
            {this.state.error?.message ? (
              <details
                style={{
                  marginBottom: 20,
                  fontSize: 11,
                  fontFamily: 'monospace',
                  background: 'var(--ds-inset)',
                  padding: 10,
                  borderRadius: 6,
                  border: '1px solid var(--ds-border)',
                  color: 'var(--ds-text-secondary)',
                }}
              >
                <summary style={{ cursor: 'pointer', fontWeight: 600 }}>Technical diagnostic details</summary>
                <p style={{ marginTop: 8, color: 'var(--ds-bear-strong)', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {this.state.error.message}
                </p>
              </details>
            ) : null}

            {/* Actions */}
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                type="button"
                onClick={this.handleReset}
                style={{
                  flex: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                  padding: '10px 16px',
                  background: 'var(--ds-surface-subtle)',
                  color: 'var(--ds-ink)',
                  border: '1px solid var(--ds-border)',
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <RefreshCw style={{ width: 14, height: 14 }} />
                Try Re-rendering Desk
              </button>
              <button
                type="button"
                onClick={() => window.location.reload()}
                style={{
                  padding: '10px 16px',
                  background: 'transparent',
                  color: 'var(--ds-text-secondary)',
                  border: '1px solid var(--ds-border)',
                  borderRadius: 6,
                  fontSize: 13,
                  cursor: 'pointer',
                }}
              >
                Full Page Reload
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}