'use client';

/* AlgoSafetyStrip — compact automation safety control for the War Room rail.
   Renders NOTHING only while the backend has CONFIRMED the engine OFF and
   never killed: a verdict terminal must not spend pixels on an inactive
   engine. The moment the engine is PAPER/LIVE, a kill is recorded, or the
   account probe fails (mode UNKNOWN, never a fabricated OFF), the strip
   appears with mode + halt + retry. Kill path reuses executeEmergencyKill
   (retry + escalation). */

import { memo, useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import { fmtINR } from '@/components/ui/desk';
import { executeEmergencyKill } from './AlgoControlWidget';
import { ShieldAlert, Power } from 'lucide-react';

type AlgoMode = 'OFF' | 'PAPER' | 'LIVE';
type AlgoModeView = AlgoMode | 'UNKNOWN';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Capital limits arrive as decimal strings ("3000"); render as INR, never raw. */
function fmtCapitalLimit(v: unknown): string {
  const n = typeof v === 'string' && v.trim() !== '' ? Number(v) : (v as number);
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return fmtINR(n);
}

export const AlgoSafetyStrip = memo(function AlgoSafetyStrip() {
  // 'UNKNOWN' until the backend confirms a mode — a fetch failure must never
  // masquerade as a confirmed OFF engine.
  const [mode, setMode] = useState<AlgoModeView>('UNKNOWN');
  const [isKilled, setIsKilled] = useState<boolean | null>(null);
  const [confirmKill, setConfirmKill] = useState(false);
  const [acting, setActing] = useState(false);
  const [killAttempt, setKillAttempt] = useState(0);
  const [killError, setKillError] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  // W6 additive truth: capital limits + consent gate from the account
  // payload, open-positions count from GET /positions. All optional — the
  // strip keeps its render-null-when-OFF behavior and omits whatever the
  // backend does not carry.
  const [capital, setCapital] = useState<Record<string, unknown> | null>(null);
  const [consentOk, setConsentOk] = useState<boolean | null>(null);
  const [openCount, setOpenCount] = useState<number | null>(null);
  const inFlight = useRef(false);

  const markUnknown = useCallback((reason: string) => {
    setMode('UNKNOWN');
    setIsKilled(null);
    setCapital(null);
    setConsentOk(null);
    setFetchError(reason);
    setLoaded(true);
  }, []);

  const fetchState = useCallback(async () => {
    if (typeof api.request !== 'function') {
      markUnknown('api.request is not configured');
      return;
    }
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const raw = await api.request<unknown>('/api/v1/algo/account');
      const data = isRecord(raw) && 'data' in raw ? raw.data : raw;
      if (!isRecord(data) || (data.mode !== 'OFF' && data.mode !== 'PAPER' && data.mode !== 'LIVE')) {
        markUnknown('algo account response unrecognised');
        return;
      }
      setMode(data.mode);
      const ks = data.kill_switch;
      setIsKilled(isRecord(ks) ? Boolean(ks.is_killed) : ks === true);
      // Capital line only when the payload carries it (backend omits the
      // block when no capital row exists); consent gate only on explicit false.
      setCapital(isRecord(data.capital) ? data.capital : null);
      setConsentOk(typeof data.consent_ok === 'boolean' ? data.consent_ok : null);
      setFetchError(null);
      setLoaded(true);
    } catch (err) {
      // Fail loud: the state is unknown, so render UNKNOWN + retry — never
      // an unconfirmed OFF with a kill button.
      markUnknown(err instanceof Error ? err.message : 'algo account unreachable');
    } finally {
      inFlight.current = false;
    }
  }, [markUnknown]);

  // Open-positions count only — never the position list (PaperCard owns that).
  // A failed fetch clears the count so a stale number is never presented.
  const fetchPositions = useCallback(async () => {
    if (typeof api.request !== 'function') return;
    try {
      const raw = await api.request<unknown>('/api/v1/algo/positions?is_open=true');
      const data = isRecord(raw) && 'data' in raw ? raw.data : raw;
      if (Array.isArray(data)) setOpenCount(data.length);
      else setOpenCount(null);
    } catch {
      setOpenCount(null);
    }
  }, []);

  useEffect(() => {
    void fetchState();
    void fetchPositions();
    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void fetchState();
      void fetchPositions();
    }, 15000);
    return () => clearInterval(id);
  }, [fetchState, fetchPositions]);

  const handleKill = useCallback(async () => {
    if (acting) return;
    setActing(true);
    setKillError(null);
    setKillAttempt(1);
    try {
      const res = await executeEmergencyKill(3, (n) => setKillAttempt(n));
      if (res.success) {
        setMode('OFF');
        setIsKilled(true);
        setFetchError(null);
        setConfirmKill(false);
      } else {
        setKillError(`Kill FAILED — backend still live: ${res.error ?? 'unknown error'}`);
      }
    } catch (err) {
      setKillError(`Kill FAILED — backend still live: ${err instanceof Error ? err.message : 'unknown error'}`);
    } finally {
      setActing(false);
      setKillAttempt(0);
    }
  }, [acting]);

  // Inactive engine, never killed, backend confirmed: no pixels. Any fetch
  // error keeps the strip visible so the unknown state is stated, not hidden.
  if (loaded && mode === 'OFF' && isKilled === false && fetchError === null) return null;

  const tone = isKilled ? 'down' : mode === 'LIVE' ? 'up' : mode === 'PAPER' ? 'info' : mode === 'UNKNOWN' ? 'warn' : 'neut';

  return (
    <section className="card" aria-label="Automation safety">
      <div className="card-hd">
        <h2 className="card-title">Automation</h2>
        <span className={`chip chip--${tone} num`}>{isKilled ? 'Killed' : mode}</span>
      </div>
      <div className="card-bd" style={{ display: 'grid', gap: 8 }}>
        {fetchError ? (
          <div role="alert" className="notice notice--warn" style={{ fontSize: 11, display: 'grid', gap: 6 }}>
            <span style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
              <ShieldAlert className="w-4 h-4 shrink-0" />
              <span>Automation state UNKNOWN — {fetchError}</span>
            </span>
            <button
              type="button"
              onClick={() => void fetchState()}
              className="btn"
              style={{ fontSize: 11, padding: '2px 8px', justifySelf: 'start' }}
            >
              Retry
            </button>
          </div>
        ) : null}
        {capital ? (
          <div aria-label="Algo capital limits">
            <div className="sg-kv">
              <span className="l">Investment limit</span>
              <span className="v num">{fmtCapitalLimit(capital.investment_limit)}</span>
            </div>
            <div className="sg-kv">
              <span className="l">Max per trade</span>
              <span className="v num">{fmtCapitalLimit(capital.max_capital_per_trade)}</span>
            </div>
            <div className="sg-kv">
              <span className="l">Max daily loss</span>
              <span className="v num">{fmtCapitalLimit(capital.max_daily_loss)}</span>
            </div>
          </div>
        ) : null}
        {consentOk === false ? (
          <p className="muted" style={{ margin: 0, fontSize: 11 }}>
            LIVE blocked until consent recorded
          </p>
        ) : null}
        {openCount !== null ? (
          <p className="muted num" style={{ margin: 0, fontSize: 11 }}>
            {openCount} open algo position{openCount === 1 ? '' : 's'}
          </p>
        ) : null}
        {killError ? (
          <div role="alert" className="notice notice--down" style={{ fontSize: 11 }}>
            <ShieldAlert className="w-4 h-4 shrink-0" />
            <span>{killError}</span>
          </div>
        ) : null}
        {confirmKill ? (
          <div style={{ display: 'grid', gap: 8 }}>
            <p className="muted" style={{ margin: 0, fontSize: 11 }}>
              Halts all automation, cancels pending orders, triggers fail-safe.
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" disabled={acting} onClick={() => void handleKill()} className="btn btn-sell" style={{ flex: 1, fontSize: 11 }}>
                {killAttempt > 0 ? `Killing (${killAttempt}/3)…` : acting ? 'Killing…' : 'Yes, kill all'}
              </button>
              <button type="button" disabled={acting} onClick={() => setConfirmKill(false)} className="btn" style={{ fontSize: 11 }}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmKill(true)}
            className="btn w-full"
            style={{ borderColor: 'var(--ds-bear)', color: 'var(--ds-bear-strong)', fontSize: 11 }}
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
