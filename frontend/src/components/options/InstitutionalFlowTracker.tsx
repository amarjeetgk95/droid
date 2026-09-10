'use client';

import { useState, useEffect } from 'react';
import { Card, EmptyNote, RetryButton, Stat, fmtNum } from '@/components/ui/desk';
import { InstitutionalFlowResponse } from '@/lib/types';
import { api } from '@/lib/api';

interface Props {
  symbol: string;
  expiry?: string;
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

export function InstitutionalFlowTracker({ symbol, expiry }: Props) {
  const [data, setData] = useState<InstitutionalFlowResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getInstitutionalFlow(symbol, expiry);
      if (res.data) {
        setData(res.data);
      } else {
        setError(res.error || 'Failed to load institutional flow');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error fetching flow analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
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
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchData identity intentionally excluded; effect keyed on symbol/expiry
  }, [symbol, expiry]);

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

  const isBullish = data.institutional_score >= 55;
  const isBearish = data.institutional_score <= 45;
  const sentimentCls = isBullish ? 'b-bull' : isBearish ? 'b-bear' : 'b-neut';

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <Card
        title="Institutional flow"
        meta={`${symbol}${expiry ? ` · ${expiry}` : ''}`}
        action={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span className={`badge ${sentimentCls}`}>
              {String(data.institutional_sentiment).replace('_', ' ')} ({data.institutional_score}/100)
            </span>
            <button type="button" className="btn" onClick={() => void fetchData()} disabled={loading}>
              {loading ? 'Refreshing…' : 'Refresh'}
            </button>
          </span>
        }
      >
        <p className="muted" style={{ margin: '0 0 12px', fontSize: 12.5 }}>
          Call/put unwinding vs build-up and strike defense walls for <strong>{symbol}</strong>.
        </p>
        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
          <Stat label="Call wall" value={`${Number(data.call_wall_strike).toLocaleString('en-IN')} CE`} sub="Highest call OI" tone="bear" />
          <Stat label="Put floor" value={`${Number(data.put_floor_strike).toLocaleString('en-IN')} PE`} sub="Highest put OI" tone="bull" />
          <Stat label="Max pain" value={Number(data.max_pain_strike).toLocaleString('en-IN')} sub="Lowest seller payout" />
          <Stat
            label="PCR (OI)"
            value={fmtNum(data.pcr_oi)}
            sub={data.pcr_oi >= 1.0 ? 'Bullish (puts > calls)' : 'Bearish (calls > puts)'}
            tone={data.pcr_oi >= 1.0 ? 'bull' : 'bear'}
          />
        </div>
      </Card>

      <Card title="Strike flow ladder" meta="Unwinding vs buildup">
        <div className="tbl-wrap">
          <table className="tbl num">
            <thead>
              <tr>
                <th>Call action</th>
                <th className="r">Call OI chg</th>
                <th className="r">Call OI</th>
                <th className="c">Strike</th>
                <th>Put OI</th>
                <th>Put OI chg</th>
                <th className="r">Put action</th>
              </tr>
            </thead>
            <tbody>
              {data.strike_flows.map((row) => (
                <tr
                  key={row.strike}
                  style={row.is_atm ? { background: 'var(--ds-accent-wash)' } : undefined}
                >
                  <td>{getBuildupBadge(row.call_buildup)}</td>
                  <td className={`r ${row.call_oi_change >= 0 ? 'v-bear' : 'v-bull'}`}>
                    {row.call_oi_change >= 0 ? `+${row.call_oi_change.toLocaleString()}` : row.call_oi_change.toLocaleString()}
                  </td>
                  <td className="r muted">{row.call_oi.toLocaleString()}</td>
                  <td className="c" style={{ fontWeight: row.is_atm ? 800 : 600, whiteSpace: 'nowrap' }}>
                    {row.strike}
                    {row.is_atm && (
                      <span className="badge b-info" style={{ marginLeft: 6 }}>
                        ATM
                      </span>
                    )}
                  </td>
                  <td className="muted">{row.put_oi.toLocaleString()}</td>
                  <td className={row.put_oi_change >= 0 ? 'v-bull' : 'v-bear'}>
                    {row.put_oi_change >= 0 ? `+${row.put_oi_change.toLocaleString()}` : row.put_oi_change.toLocaleString()}
                  </td>
                  <td className="r">{getBuildupBadge(row.put_buildup)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="faint" style={{ margin: '8px 0 0', fontSize: 11 }}>Auto-updates every ~30s when tab is visible.</p>
      </Card>
    </div>
  );
}
