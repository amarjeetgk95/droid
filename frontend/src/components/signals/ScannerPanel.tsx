'use client';

/* Real-time scanner grid — presentational only. Data arrives via props; the
   scan and auto-detect actions arrive as callbacks, so the same panel can be
   mounted on the signals desk and in the Lab without duplicating logic. */

import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { fmtINR, normalizeDirection } from '@/components/ui/desk';
import { asStr, prettyKey } from './signalsNormalize';

export type ScannerSignal = {
  id?: string | number;
  underlying?: unknown;
  symbol?: unknown;
  strategy?: unknown;
  direction?: unknown;
  side?: unknown;
  trigger_price?: unknown;
  stop_loss?: unknown;
  target_1?: unknown;
};

export type ScannerData = {
  scanned_underlyings?: string[];
  total_candidates: number;
  new_signals?: ScannerSignal[] | null;
  active_signals?: unknown[] | null;
  timestamp_ms?: number;
};

export type ScannerPanelProps = {
  scannerData: ScannerData | null;
  scannerLoading: boolean;
  scannerError: string | null;
  onScan: () => void | Promise<void>;
  /** When provided, renders the Auto-Detect action. */
  onAutoDetect?: () => void | Promise<void>;
};

export function DirText({ direction }: { direction: unknown }) {
  const d = normalizeDirection(direction);
  if (d === 'NEUTRAL') return <span className="sg-dir" style={{ color: 'var(--ds-ink-3)' }}>—</span>;
  const long = d === 'BULLISH';
  return <span className={`sg-dir ${long ? 'long' : 'short'}`}>{long ? 'LONG' : 'SHORT'}</span>;
}

export function ScannerPanel({
  scannerData,
  scannerLoading,
  scannerError,
  onScan,
  onAutoDetect,
}: ScannerPanelProps) {
  const [autoDetecting, setAutoDetecting] = useState(false);

  const handleAutoDetect = async () => {
    if (!onAutoDetect) return;
    setAutoDetecting(true);
    try {
      await onAutoDetect();
    } finally {
      setAutoDetecting(false);
    }
  };

  return (
    <div className="sg-pad" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>Real-Time Setup Scanner</h3>
          <p className="muted" style={{ margin: '2px 0 0', fontSize: 11.5 }}>
            Automated scanning across high-probability intraday & scalp strategies.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {onAutoDetect ? (
            <button
              type="button"
              className="sg-ibtn"
              disabled={autoDetecting}
              onClick={handleAutoDetect}
              title="Scan market and auto-register active candidate setups"
              style={{ padding: '4px 10px', height: 'auto' }}
            >
              {autoDetecting ? 'Detecting…' : '⚡ Auto-Detect'}
            </button>
          ) : null}
          <button
            type="button"
            className="sg-primary"
            disabled={scannerLoading}
            onClick={() => void onScan()}
          >
            <RefreshCw size={13} className={scannerLoading ? 'animate-spin' : ''} />
            {scannerLoading ? 'Scanning…' : 'Scan Now'}
          </button>
        </div>
      </div>

      {scannerError ? (
        <p className="sg-err">{scannerError}</p>
      ) : null}

      {scannerData ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
            <div style={{ padding: '8px 12px', background: 'var(--ds-inset)', borderRadius: 6, border: '1px solid var(--ds-border)' }}>
              <span className="sg-eyebrow" style={{ display: 'block', fontSize: 10 }}>Candidates Found</span>
              <span className="sg-num" style={{ fontSize: 16, fontWeight: 700 }}>{scannerData.total_candidates}</span>
            </div>
            <div style={{ padding: '8px 12px', background: 'var(--ds-inset)', borderRadius: 6, border: '1px solid var(--ds-border)' }}>
              <span className="sg-eyebrow" style={{ display: 'block', fontSize: 10 }}>New Signals</span>
              <span className="sg-num pos-num" style={{ fontSize: 16, fontWeight: 700 }}>{scannerData.new_signals?.length ?? 0}</span>
            </div>
            <div style={{ padding: '8px 12px', background: 'var(--ds-inset)', borderRadius: 6, border: '1px solid var(--ds-border)' }}>
              <span className="sg-eyebrow" style={{ display: 'block', fontSize: 10 }}>Active in Stream</span>
              <span className="sg-num" style={{ fontSize: 16, fontWeight: 700 }}>{scannerData.active_signals?.length ?? 0}</span>
            </div>
            <div style={{ padding: '8px 12px', background: 'var(--ds-inset)', borderRadius: 6, border: '1px solid var(--ds-border)' }}>
              <span className="sg-eyebrow" style={{ display: 'block', fontSize: 10 }}>Underlyings Scanned</span>
              <span style={{ fontSize: 11.5, color: 'var(--ds-ink-2)', display: 'block', marginTop: 2 }}>
                {scannerData.scanned_underlyings?.join(', ') || '—'}
              </span>
            </div>
          </div>

          {scannerData.new_signals?.length ? (
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Strategy</th>
                    <th>Direction</th>
                    <th className="r">Trigger</th>
                    <th className="r">Stop Loss</th>
                    <th className="r">Target</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {scannerData.new_signals.map((sig, idx) => (
                    <tr key={sig.id ?? idx}>
                      <td><span className="sg-sym">{asStr(sig.underlying) ?? asStr(sig.symbol) ?? '—'}</span></td>
                      <td><span className="sg-strat">{prettyKey(asStr(sig.strategy) ?? '—')}</span></td>
                      <td><DirText direction={sig.direction ?? sig.side} /></td>
                      <td className="r sg-num" style={{ fontWeight: 700 }}>{sig.trigger_price ? fmtINR(sig.trigger_price) : '—'}</td>
                      <td className="r sg-num neg-num">{sig.stop_loss ? fmtINR(sig.stop_loss) : '—'}</td>
                      <td className="r sg-num pos-num">{sig.target_1 ? fmtINR(sig.target_1) : '—'}</td>
                      <td><span className="sg-tag info">NEW CANDIDATE</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="sg-empty" style={{ padding: 24 }}>
              <p>No new breakthrough candidates detected in this scan cycle.</p>
            </div>
          )}
        </div>
      ) : (
        <div className="sg-empty" style={{ padding: 24 }}>
          <p>Click &quot;Scan Now&quot; to inspect all index candidates against current order book and momentum.</p>
        </div>
      )}
    </div>
  );
}

export default ScannerPanel;
