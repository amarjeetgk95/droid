'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Card, EmptyNote, RetryButton, Stat, fmtNum } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import type { InstitutionalFlowResponse } from '@/lib/types';
import { api } from '@/lib/api';

interface Props {
  symbol: string;
  expiry?: string;
  marketClosed?: boolean;
}

interface FlowMeta {
  timestamp: string | null;
  provider: string | null;
}

function buildupBadgeClass(type: string): string {
  switch (type) {
    case 'LONG_BUILDUP':
      return 'b-bull';
    case 'SHORT_COVERING':
      return 'b-info';
    case 'SHORT_BUILDUP':
      return 'b-bear';
    case 'LONG_UNWINDING':
      return 'b-neut';
    default:
      return 'b-neut';
  }
}

function getBuildupBadge(type: string) {
  if (!type || type === '—') return <span className="faint" style={{ fontSize: 11 }}>—</span>;
  return (
    <span className={`badge ${buildupBadgeClass(type)}`}>
      {type.replace(/_/g, ' ')}
    </span>
  );
}

function positive(v: number | null | undefined): number | null {
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null;
}

function fmtChange(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—';
  return v > 0 ? `+${v.toLocaleString()}` : v.toLocaleString();
}

export function InstitutionalFlowTracker({ symbol, expiry, marketClosed = false }: Props) {
  const [data, setData] = useState<InstitutionalFlowResponse | null>(null);
  const [meta, setMeta] = useState<FlowMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const fetchData = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const res = await api.getInstitutionalFlow(symbol, expiry);
      if (requestId !== requestIdRef.current) return;
      if (res.data) {
        setData(res.data);
        setMeta({
          timestamp: res.meta?.timestamp ?? null,
          provider: res.meta?.provider ?? null,
        });
      } else {
        setError(res.error || 'Failed to load institutional flow');
      }
    } catch (err: unknown) {
      if (requestId !== requestIdRef.current) return;
      setError(err instanceof Error ? err.message : 'Error fetching flow analytics');
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  }, [symbol, expiry]);

  useEffect(() => {
    // Key change: drop the previous symbol/expiry snapshot so its numbers are
    // never shown under the new selection, and invalidate any in-flight request.
    setData(null);
    setMeta(null);
    requestIdRef.current += 1;
    void fetchData();

    let timeout: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      const jittered = 30000 * (0.8 + Math.random() * 0.4);
      timeout = setTimeout(() => {
        if (typeof document !== 'undefined' && !document.hidden) void fetchData();
        schedule();
      }, jittered);
    };
    schedule();
    const onVis = () => { if (!document.hidden) void fetchData(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
      requestIdRef.current += 1;
    };
  }, [fetchData]);

  if (loading && !data) {
    return (
      <Card title="Institutional flow" meta="scanning…">
        <div style={{ display: 'grid', gap: 8 }}>
          <div className="skel" style={{ height: 14, width: '60%' }}>.</div>
          <div className="skel" style={{ height: 14, width: '80%' }}>.</div>
          <div className="skel" style={{ height: 90, width: '100%' }}>.</div>
        </div>
        <p className="muted" style={{ margin: '10px 0 0', fontSize: 12 }}>Analyzing institutional flow…</p>
      </Card>
    );
  }

  if (error && !data) {
    return (
      <Card title="Institutional flow" meta="unavailable">
        <EmptyNote>{error}</EmptyNote>
        <div style={{ marginTop: 10 }}>
          <RetryButton onRetry={() => void fetchData()} />
        </div>
      </Card>
    );
  }

  if (!data) return null;

  const scope = `${symbol}${expiry ? ` · ${expiry}` : ''}`;
  const hasOiData =
    data.total_call_oi > 0 ||
    data.total_put_oi > 0 ||
    data.strike_flows.some((row) => row.call_oi > 0 || row.put_oi > 0);

  const freshness = (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <FreshnessClock
        lastAt={meta?.timestamp ?? null}
        fetching={loading}
        marketClosed={marketClosed}
        sourceLabel={meta?.provider ? `REST · ${meta.provider}` : 'REST · ~30s poll'}
      />
      <button type="button" className="btn" onClick={() => void fetchData()} disabled={loading}>
        {loading ? 'Refreshing…' : 'Refresh'}
      </button>
    </span>
  );

  if (!hasOiData) {
    return (
      <Card title="Institutional flow" meta={scope} action={freshness}>
        <EmptyNote>
          No open interest published for this expiry — strike walls, max pain and build-up
          classification are unavailable. Nothing is inferred from absent data.
        </EmptyNote>
      </Card>
    );
  }

  const callWall = positive(data.call_wall_strike);
  const putFloor = positive(data.put_floor_strike);
  const maxPain = positive(data.max_pain_strike);
  const wallAvailable = {
    call: callWall !== null && data.total_call_oi > 0,
    put: putFloor !== null && data.total_put_oi > 0,
    maxPain: maxPain !== null,
  };
  const pcrKnown =
    Number.isFinite(data.pcr_oi) && data.pcr_oi > 0 && data.total_call_oi > 0 && data.total_put_oi > 0;

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <Card
        title="Institutional flow"
        meta={scope}
        action={freshness}
      >
        <p className="muted" style={{ margin: '0 0 12px', fontSize: 12.5 }}>
          Call/put unwinding vs build-up and strike defense walls for <strong>{symbol}</strong>.
        </p>
        {error ? (
          <p role="alert" className="num" style={{ margin: '0 0 10px', fontSize: 12, color: 'var(--ds-bear-strong)' }}>
            Refresh failed — showing the last snapshot. {error}
          </p>
        ) : null}
        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
          <Stat
            label="Call wall"
            value={wallAvailable.call ? `${callWall!.toLocaleString('en-IN')} CE` : '—'}
            sub={wallAvailable.call ? 'Highest call OI' : 'No call OI published'}
            tone={wallAvailable.call ? 'bear' : undefined}
          />
          <Stat
            label="Put floor"
            value={wallAvailable.put ? `${putFloor!.toLocaleString('en-IN')} PE` : '—'}
            sub={wallAvailable.put ? 'Highest put OI' : 'No put OI published'}
            tone={wallAvailable.put ? 'bull' : undefined}
          />
          <Stat
            label="Max pain"
            value={wallAvailable.maxPain ? maxPain!.toLocaleString('en-IN') : '—'}
            sub={wallAvailable.maxPain ? 'Lowest seller payout' : 'No OI to compute max pain'}
          />
          <Stat
            label="PCR (OI)"
            value={pcrKnown ? fmtNum(data.pcr_oi) : '—'}
            sub={
              pcrKnown
                ? data.pcr_oi >= 1.0
                  ? 'Bullish (puts > calls)'
                  : 'Bearish (calls > puts)'
                : 'No call/put OI pair'
            }
            tone={pcrKnown ? (data.pcr_oi >= 1.0 ? 'bull' : 'bear') : undefined}
          />
          <Stat
            label="Flow sentiment"
            value={`${String(data.institutional_sentiment).replace('_', ' ')} (${data.institutional_score}/100)`}
            sub={`${data.strike_flows.length} strike rows classified`}
            tone={data.institutional_score >= 55 ? 'bull' : data.institutional_score <= 45 ? 'bear' : 'neut'}
          />
        </div>
      </Card>

      <Card title="Strike flow ladder" meta="Unwinding vs buildup">
        {data.strike_flows.length === 0 ? (
          <EmptyNote>No strike-level flow published for this expiry.</EmptyNote>
        ) : (
          <div className="tbl-wrap">
            <table className="tbl num">
              <caption className="sr-only">
                Strike flow ladder: call build-up action, call OI change, call OI, strike, put OI, put OI change and
                put build-up action for {scope}.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Call action</th>
                  <th scope="col" className="r">Call OI chg</th>
                  <th scope="col" className="r">Call OI</th>
                  <th scope="col" className="c">Strike</th>
                  <th scope="col">Put OI</th>
                  <th scope="col">Put OI chg</th>
                  <th scope="col" className="r">Put action</th>
                </tr>
              </thead>
              <tbody>
                {data.strike_flows.map((row) => (
                  <tr
                    key={row.strike}
                    style={row.is_atm ? { background: 'var(--ds-accent-wash)' } : undefined}
                  >
                    <td>{getBuildupBadge(row.call_buildup)}</td>
                    <td className={`r ${row.call_oi_change > 0 ? 'v-bear' : row.call_oi_change < 0 ? 'v-bull' : ''}`}>
                      {fmtChange(row.call_oi_change)}
                    </td>
                    <td className="r muted">{row.call_oi > 0 ? row.call_oi.toLocaleString() : '—'}</td>
                    <td className="c" style={{ fontWeight: row.is_atm ? 800 : 600, whiteSpace: 'nowrap' }}>
                      {row.strike}
                      {row.is_atm && (
                        <span className="badge b-info" style={{ marginLeft: 6 }}>
                          ATM
                        </span>
                      )}
                    </td>
                    <td className="muted">{row.put_oi > 0 ? row.put_oi.toLocaleString() : '—'}</td>
                    <td className={row.put_oi_change > 0 ? 'v-bull' : row.put_oi_change < 0 ? 'v-bear' : ''}>
                      {fmtChange(row.put_oi_change)}
                    </td>
                    <td className="r">{getBuildupBadge(row.put_buildup)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="faint" style={{ margin: '8px 0 0', fontSize: 11 }}>Auto-updates every ~30s when tab is visible.</p>
      </Card>
    </div>
  );
}
