'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Card, DirectionBadge, EmptyNote, RetryButton, fmtNum } from '@/components/ui/desk';

type CompactSignal = {
  id: string;
  symbol: string;
  bias: unknown;
  score: unknown;
  confidence: unknown;
};

export function SupportingSignalsPanel() {
  const [rows, setRows] = useState<CompactSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    setLoading(true);
    setError(null);
    try {
      const res = (await api.getSignalsScanner()) as unknown as Record<string, unknown>;
      const raw =
        (res?.active_signals as Array<Record<string, unknown>> | undefined) ??
        (res?.new_signals as Array<Record<string, unknown>> | undefined) ??
        (res?.signals as Array<Record<string, unknown>> | undefined) ??
        [];
      const list = Array.isArray(raw) ? raw.slice(0, 8) : [];
      const compact: CompactSignal[] = list
        .filter((s) => s && (s.signal_id || s.id))
        .map((s) => {
          const id = String(s.signal_id ?? s.id ?? '');
          const symbol = String(s.underlying ?? s.instrument ?? s.symbol ?? '—');
          return {
            id,
            symbol,
            bias: s.direction,
            score: (s as Record<string, unknown>).score ?? s.confidence,
            confidence: s.confidence,
          };
        });
      setRows(compact);
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : 'signals unavailable');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void load();
    }, 60000);
    return () => clearInterval(id);
  }, [load]);

  if (loading && rows.length === 0) {
    return (
      <Card title="Supporting signals" meta="scanner">
        <div style={{ display: 'grid', gap: 8 }}>
          <div className="skel" style={{ height: 14, width: '80%' }}>.</div>
          <div className="skel" style={{ height: 14, width: '65%' }}>.</div>
          <div className="skel" style={{ height: 14, width: '72%' }}>.</div>
        </div>
      </Card>
    );
  }

  if (error && rows.length === 0) {
    return (
      <Card title="Supporting signals" meta="scanner">
        <EmptyNote>Signals unavailable.</EmptyNote>
        <div style={{ marginTop: 10 }}>
          <RetryButton onRetry={() => void load()} />
        </div>
      </Card>
    );
  }

  return (
    <Card title="Supporting signals" meta="scanner">
      {rows.length === 0 ? (
        <EmptyNote>No confirmed setups.</EmptyNote>
      ) : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Bias</th>
                <th className="r">Score</th>
                <th className="r">Conf</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const conf = fmtNum(r.confidence, 1);
                return (
                  <tr key={r.id}>
                    <td>{r.symbol}</td>
                    <td>
                      <DirectionBadge direction={r.bias} />
                    </td>
                    <td className="r num">{fmtNum(r.score, 1)}</td>
                    <td className="r num">{conf === '—' ? '—' : `${conf}%`}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted" style={{ margin: '10px 0 0', fontSize: 12 }}>
        Scanner snapshot · max 8 rows ·{' '}
        <Link href="/markets" className="text-[var(--ds-accent)] no-underline hover:underline">
          Markets
        </Link>{' '}
        ·{' '}
        <Link href="/options" className="text-[var(--ds-accent)] no-underline hover:underline">
          Options
        </Link>
      </p>
    </Card>
  );
}
