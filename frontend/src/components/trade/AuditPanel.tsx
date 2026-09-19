'use client';

import type { TradeAuditRow } from '@/lib/tradeOps';
import { fmtDateTimeMs } from '@/lib/signalsNormalize';

export function AuditPanel({ rows, loading }: { rows: TradeAuditRow[]; loading: boolean }) {
  return (
    <section className="panel">
      <header className="card-hd">
        <h3 className="card-title">Recent Audit</h3>
        <span className="card-meta">{rows.length} event(s)</span>
      </header>
      {rows.length === 0 ? (
        <p className="sg-empty">
          {loading
            ? 'Loading audit trail…'
            : 'No audit events recorded yet. Order, exit and governance actions append here.'}
        </p>
      ) : (
        <div className="tbl-scroll">
          <table className="sg-table">
            <thead>
              <tr>
                <th>Event</th>
                <th>Time</th>
                <th>Contract</th>
                <th>Order</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.eventType}-${row.timestampMs ?? 'na'}-${index}`}>
                  <td>
                    <span className="sg-tag neut">{row.eventType}</span>
                  </td>
                  <td className="mono">{fmtDateTimeMs(row.timestampMs)}</td>
                  <td>
                    <div className="sg-sym">{row.symbol ?? '—'}</div>
                  </td>
                  <td className="mono">{row.clientOrderId ?? '—'}</td>
                  <td>
                    <div className="sg-rownote">{row.detail ?? '—'}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
