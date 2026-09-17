'use client';

import { memo, useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import { fmtINR } from '@/components/ui/desk';
import { playScalpAudio } from '@/components/scalp/scalpAudio';
import { ShieldAlert, Bot, Power } from 'lucide-react';

type AlgoMode = 'OFF' | 'PAPER' | 'LIVE';

interface AlgoAccountState {
  mode: AlgoMode;
  is_active: boolean;
  capital?: {
    investment_limit?: string;
    max_capital_per_trade?: string;
    max_daily_loss?: string;
  } | null;
  kill_switch?: {
    is_killed?: boolean;
    kill_level?: string;
  } | null;
}

interface OpenPosition {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  entry_price: number;
  current_price?: number;
  pnl?: number;
}

type ActingKind = 'mode' | 'kill' | null;

const ALGO_MODES: readonly AlgoMode[] = ['OFF', 'PAPER', 'LIVE'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function getErrorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === 'string' && err.length > 0) return err;
  if (isRecord(err) && typeof err.message === 'string' && err.message.length > 0) return err.message;
  return 'Unknown error';
}

/**
 * Executes emergency kill switch with multi-attempt retry, backoff, and signal escalation fallback.
 */
export async function executeEmergencyKill(
  maxRetries = 3,
  onAttempt?: (attempt: number) => void
): Promise<{ success: boolean; error?: string }> {
  if (typeof api.request !== 'function') {
    return { success: false, error: 'api.request is not configured' };
  }

  let lastError = 'Unknown error';
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    onAttempt?.(attempt);
    try {
      await api.request<unknown>('/api/v1/algo/kill-switch', {
        method: 'POST',
        body: JSON.stringify({ kill_level: 'HARD_STOP', reason: 'User War Room Kill Switch' }),
      });
      return { success: true };
    } catch (err) {
      lastError = getErrorMessage(err);
      if (attempt < maxRetries) {
        await new Promise((resolve) => setTimeout(resolve, attempt * 600));
      }
    }
  }

  // Escalation: attempt secondary emergency signal kill switch endpoint
  try {
    await api.request<unknown>('/api/v1/signals/kill-switch', {
      method: 'POST',
      body: JSON.stringify({ active: true, reason: 'Escalated emergency kill switch from War Room' }),
    });
    return { success: true };
  } catch (escErr) {
    lastError = `Primary kill failed (${lastError}) & Escalation failed (${getErrorMessage(escErr)})`;
  }

  try {
    playScalpAudio('panic');
  } catch {
    // Audio context may not be ready or muted
  }

  return { success: false, error: lastError };
}

/** Backend may return the object directly or wrapped in `{ data: ... }`. */
function unwrapDataEnvelope(payload: unknown): unknown {
  if (isRecord(payload) && 'data' in payload) return payload.data;
  return payload;
}

function isAlgoMode(value: unknown): value is AlgoMode {
  return value === 'OFF' || value === 'PAPER' || value === 'LIVE';
}

function parseAccount(payload: unknown): AlgoAccountState | null {
  const unwrapped = unwrapDataEnvelope(payload);
  if (!isRecord(unwrapped)) return null;
  if (!isAlgoMode(unwrapped.mode)) return null;
  const account: AlgoAccountState = {
    mode: unwrapped.mode,
    is_active: Boolean(unwrapped.is_active),
  };
  if (unwrapped.capital === null || isRecord(unwrapped.capital)) {
    account.capital = unwrapped.capital as AlgoAccountState['capital'];
  }
  if (unwrapped.kill_switch === null || isRecord(unwrapped.kill_switch)) {
    const ks = unwrapped.kill_switch as Record<string, unknown>;
    account.kill_switch = unwrapped.kill_switch === null
      ? null
      : {
          is_killed: typeof ks.is_killed === 'boolean' ? ks.is_killed : Boolean(ks.is_killed),
          kill_level: typeof ks.kill_level === 'string' ? ks.kill_level : undefined,
        };
  }
  return account;
}

function isValidPosition(item: unknown): item is OpenPosition {
  if (!isRecord(item)) return false;
  if (typeof item.id !== 'string' || item.id.length === 0) return false;
  if (typeof item.symbol !== 'string' || item.symbol.length === 0) return false;
  if (item.side !== 'BUY' && item.side !== 'SELL') return false;
  if (typeof item.quantity !== 'number' || !Number.isFinite(item.quantity)) return false;
  if (typeof item.entry_price !== 'number' || !Number.isFinite(item.entry_price)) return false;
  if ('current_price' in item && item.current_price !== undefined && typeof item.current_price !== 'number') return false;
  if ('pnl' in item && item.pnl !== undefined && typeof item.pnl !== 'number') return false;
  return true;
}

/**
 * Returns validated positions, or null when the payload shape is unusable.
 * Accepts: array directly, `{ data: [...] }`, `{ positions: [...] }`,
 * or `{ data: { positions: [...] } }`.
 */
function parsePositions(payload: unknown): OpenPosition[] | null {
  let candidate: unknown = unwrapDataEnvelope(payload);
  if (isRecord(candidate) && Array.isArray(candidate.positions)) {
    candidate = candidate.positions;
  } else if (isRecord(candidate) && isRecord(candidate.data) && Array.isArray(candidate.data.positions)) {
    // Handles double-wrapped `{ data: { positions: [...] } }` without `as any`.
    candidate = candidate.data.positions;
  }
  if (!Array.isArray(candidate)) return null;
  const valid: OpenPosition[] = [];
  for (const item of candidate) {
    if (isValidPosition(item)) valid.push(item);
  }
  // Array shape is valid even if some rows were dropped; only null when not an array.
  return valid;
}

function isKillFailureMessage(msg: string | null): boolean {
  return msg !== null && msg.startsWith('Kill switch FAILED');
}

export const AlgoControlWidget = memo(function AlgoControlWidget() {
  const [account, setAccount] = useState<AlgoAccountState>({
    mode: 'PAPER',
    is_active: true,
  });
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isFetching, setIsFetching] = useState(false);
  const [acting, setActing] = useState<ActingKind>(null);
  const [confirmKill, setConfirmKill] = useState(false);
  const [confirmLive, setConfirmLive] = useState(false);
  const [killAttempt, setKillAttempt] = useState(0);
  const fetchInFlight = useRef(false);

  const isActing = acting !== null;

  const fetchAlgoState = useCallback(async () => {
    // Core exposes request; if a build ever drops it, surface an error
    // instead of rendering fake defaults.
    if (typeof api.request !== 'function') {
      setError('Algo API unavailable: api.request is not configured.');
      return;
    }
    if (fetchInFlight.current) return;
    fetchInFlight.current = true;
    setIsFetching(true);
    try {
      const failures: string[] = [];

      try {
        const rawAccount = await api.request<unknown>('/api/v1/algo/account');
        const parsed = parseAccount(rawAccount);
        if (parsed) {
          setAccount(parsed);
        } else {
          failures.push('Failed to load algo account: unexpected response shape');
        }
      } catch (err) {
        failures.push(`Failed to load algo account: ${getErrorMessage(err)}`);
      }

      try {
        const rawPositions = await api.request<unknown>('/api/v1/algo/positions?is_open=true');
        const parsed = parsePositions(rawPositions);
        if (parsed !== null) {
          setPositions(parsed);
        } else {
          failures.push('Failed to load positions: unexpected response shape');
        }
      } catch (err) {
        failures.push(`Failed to load positions: ${getErrorMessage(err)}`);
      }

      if (failures.length > 0) {
        const combined = failures.join(' | ');
        // Never let a background poll overwrite the critical kill-failure
        // banner — trading safety requires it stays visible until the user
        // retries or dismisses it.
        setError((prev) => (isKillFailureMessage(prev) ? prev : combined));
      } else {
        // Full poll success clears fetch/mode errors but preserves a sticky
        // kill-failure until the user retries or dismisses it.
        setError((prev) => (isKillFailureMessage(prev) ? prev : null));
      }
    } finally {
      fetchInFlight.current = false;
      setIsFetching(false);
    }
  }, []);

  useEffect(() => {
    void fetchAlgoState();
    const timer = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void fetchAlgoState();
    }, 10000);
    return () => clearInterval(timer);
  }, [fetchAlgoState]);

  const handleSetMode = async (nextMode: AlgoMode) => {
    if (typeof api.request !== 'function') {
      setError(`Failed to switch to ${nextMode}: api.request is not configured.`);
      return;
    }
    if (isActing) return;
    setActing('mode');
    setError(null);
    try {
      await api.request<unknown>('/api/v1/algo/account/mode', {
        method: 'POST',
        body: JSON.stringify({ mode: nextMode }),
      });
      // Only trust the new mode after the backend confirms success.
      setAccount((prev) => ({ ...prev, mode: nextMode }));
    } catch (err) {
      // Keep the old mode — never optimistically display a mode the
      // backend rejected.
      setError(`Failed to switch to ${nextMode}: ${getErrorMessage(err)}`);
    } finally {
      setActing(null);
    }
  };

  const onSelectMode = (m: AlgoMode) => {
    if (m === account.mode) return;
    if (m === 'LIVE') {
      setConfirmLive(true);
      return;
    }
    setConfirmLive(false);
    void handleSetMode(m);
  };

  const handleEmergencyKill = async () => {
    if (typeof api.request !== 'function') {
      setError('Kill switch FAILED - backend still live: api.request is not configured.');
      return;
    }
    if (isActing) return;
    setActing('kill');
    setError(null);
    setKillAttempt(1);
    try {
      const res = await executeEmergencyKill(3, (attempt) => setKillAttempt(attempt));
      if (res.success) {
        // Only display KILLED after confirmed.
        setAccount((prev) => ({
          ...prev,
          mode: 'OFF',
          kill_switch: { is_killed: true, kill_level: 'HARD_STOP' },
        }));
        setConfirmKill(false);
      } else {
        // Critical: keep prior state, keep confirm open so user can retry
        setError(`Kill switch FAILED after 3 attempts - backend still live: ${res.error || 'Unknown error'}`);
      }
    } catch (err) {
      setError(`Kill switch FAILED - backend still live: ${getErrorMessage(err)}`);
    } finally {
      setActing(null);
      setKillAttempt(0);
    }
  };


  const totalPnL = positions.reduce((acc, p) => acc + (p.pnl ?? 0), 0);
  const isKilled = Boolean(account.kill_switch?.is_killed);

  return (
    <section className="card" aria-label="Automated algo engine">
      <div className="card-hd">
        <div className="flex items-center gap-2 min-w-0">
          <Bot className="w-4 h-4" style={{ color: 'var(--ds-ink-2)' }} />
          <h2 className="card-title" style={{ fontSize: 12 }}>Algo engine</h2>
          {isFetching ? (
            <span className="mono faint" style={{ fontSize: 10 }} aria-live="polite">
              syncing…
            </span>
          ) : null}
        </div>

        <span
          className={`badge badge-sm ${isKilled ? 'b-bear' : account.mode === 'LIVE' ? 'b-bull' : account.mode === 'PAPER' ? 'b-info' : 'b-neut'}`}
        >
          {isKilled ? 'KILLED' : `${account.mode}`}
        </span>
      </div>
      <div className="card-bd flex flex-col gap-2.5" style={{ padding: 12 }}>

      {error ? (
        <div
          role="alert"
          className="p-2.5 rounded-md border border-down-line bg-down-wash flex items-start gap-2"
        >
          <ShieldAlert className="w-4 h-4 text-down shrink-0 mt-px" />
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-bold text-down-strong break-words">{error}</p>
            <div className="flex gap-2 mt-1.5">
              <button
                type="button"
                onClick={() => void fetchAlgoState()}
                className="px-2 py-1 rounded border border-down-line text-[11px] font-semibold text-down-strong bg-card hover:bg-down-wash cursor-pointer"
              >
                Retry
              </button>
              <button
                type="button"
                onClick={() => setError(null)}
                className="px-2 py-1 rounded text-[11px] font-semibold text-down-strong hover:text-down-strong cursor-pointer"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Mode Control Selector (Segmented) */}
      <div className="seg w-full" role="group" aria-label="Algo mode" style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)' }}>
        {ALGO_MODES.map((m) => (
          <button
            key={m}
            type="button"
            disabled={isActing}
            data-active={account.mode === m}
            data-danger={m === 'LIVE' ? 'true' : undefined}
            aria-pressed={account.mode === m}
            onClick={() => onSelectMode(m)}
            className="seg-btn"
            style={{ justifyContent: 'center', fontWeight: account.mode === m && m === 'LIVE' ? 700 : undefined }}
          >
            {acting === 'mode' && account.mode !== m ? '…' : m}
          </button>
        ))}
      </div>
      {acting === 'mode' ? (
        <p className="mono faint" style={{ fontSize: 10 }} aria-live="polite">
          Switching mode — awaiting backend confirmation…
        </p>
      ) : null}

      {/* Confirmation prompt for switching to LIVE */}
      {confirmLive ? (
        <div
          role="region"
          aria-label="Confirm LIVE mode"
          className="p-3 rounded border flex flex-col gap-2"
          style={{ borderColor: 'var(--ds-warn-line)', background: 'var(--ds-warn-wash)' }}
        >
          <div className="text-xs font-bold flex items-center gap-1.5" style={{ color: 'var(--ds-warn-ink)' }}>
            <ShieldAlert className="w-4 h-4 shrink-0" />
            <span>Switch to LIVE Trading?</span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            LIVE mode will deploy real capital and execute real orders directly on your broker terminal.
            {account.capital?.investment_limit ? ` Max capital: ${account.capital.investment_limit}.` : ''}
          </p>
          <div className="flex gap-2 mt-1">
            <button
              type="button"
              disabled={isActing}
              onClick={() => {
                setConfirmLive(false);
                void handleSetMode('LIVE');
              }}
              className="btn btn-buy flex-1 font-bold"
              style={{ fontSize: 11, padding: '5px 10px', background: 'var(--ds-bull)' }}
            >
              {acting === 'mode' ? 'SWITCHING…' : 'CONFIRM LIVE'}
            </button>
            <button
              type="button"
              disabled={isActing}
              onClick={() => setConfirmLive(false)}
              className="btn"
              style={{ fontSize: 11, padding: '5px 10px' }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {/* Position & Risk Metrics */}
      <div className="pnl-strip">
        <span className="ps"><span className="ps-l">Positions</span><span className="ps-v num">{positions.length}</span></span>
        <span className="ps">
          <span className="ps-l">Unreal P&amp;L</span>
          <span className={`ps-v num ${totalPnL > 0 ? 'v-bull' : totalPnL < 0 ? 'v-bear' : ''}`}>
            {totalPnL !== 0 ? fmtINR(totalPnL) : '₹0.00'}
          </span>
        </span>
      </div>

      {/* Open Positions mini list if any */}
      {positions.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="sg-sect">Open trades</h3>
          <div className="max-h-28 overflow-y-auto space-y-1 mono" style={{ fontSize: 11.5 }}>
            {positions.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between p-2 rounded border"
                style={{ background: 'var(--ds-surface-subtle)', borderColor: 'var(--ds-border)' }}
              >
                <span className="font-bold">{p.symbol}</span>
                <span className={p.side === 'BUY' ? 'v-bull font-bold' : 'v-bear font-bold'}>
                  {p.side} {p.quantity}
                </span>
                <span className="font-bold num">{p.pnl ? fmtINR(p.pnl) : '—'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Emergency Kill Switch */}
      {confirmKill ? (
        <div className="p-3 rounded border flex flex-col gap-2" style={{ borderColor: 'var(--ds-bear)', background: 'var(--ds-bear-wash)' }}>
          <div className="text-xs font-bold flex items-center gap-1.5 v-bear">
            <ShieldAlert className="w-4 h-4" />
            <span>Confirm kill switch?</span>
          </div>
          <p className="text-[11px] muted">
            Halts all automation, cancels pending orders, and triggers fail-safe.
          </p>
          <div className="flex gap-2 mt-1">
            <button
              type="button"
              disabled={isActing}
              onClick={() => void handleEmergencyKill()}
              className="btn btn-sell flex-1"
            >
              {killAttempt > 0 ? `KILLING (${killAttempt}/3)…` : acting === 'kill' ? 'KILLING…' : 'YES, KILL ALL'}
            </button>
            <button
              type="button"
              disabled={isActing}
              onClick={() => setConfirmKill(false)}
              className="btn"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirmKill(true)}
          className="btn w-full"
          style={{ borderColor: 'var(--ds-bear)', color: 'var(--ds-bear-strong)' }}
        >
          <span className="btn-ic" style={{ justifyContent: 'center' }}>
            <Power className="w-4 h-4" />
            Kill switch
          </span>
        </button>
      )}
      </div>
    </section>
  );
});
