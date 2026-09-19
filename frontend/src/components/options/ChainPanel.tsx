'use client';

import { useMemo, useState } from 'react';
import { toNumber } from '@/lib/coerce';
import { fmtExpiry } from '@/lib/signalsNormalize';
import { safeInt, safeNum } from '@/lib/utils';
import type { OptionChainResponse } from '@/lib/types';
import { chainStrikeRows, sliceAtmWindow } from '@/lib/optionsDesk';

type WindowOption = { id: string; label: string; radius: number | null };

const WINDOWS: WindowOption[] = [
  { id: 'atm12', label: 'ATM ±12', radius: 12 },
  { id: 'atm6', label: 'ATM ±6', radius: 6 },
  { id: 'all', label: 'Full ladder', radius: null },
];

export function ChainPanel({
  chain,
  loading,
  instrument,
}: {
  chain: OptionChainResponse | null;
  loading: boolean;
  instrument: string;
}) {
  const [windowId, setWindowId] = useState('atm12');

  const rows = useMemo(() => chainStrikeRows(chain), [chain]);
  const radius = useMemo(
    () => WINDOWS.find((w) => w.id === windowId)?.radius ?? 12,
    [windowId],
  );
  const visible = useMemo(() => sliceAtmWindow(rows, radius), [rows, radius]);

  if (loading && !chain) {
    return (
      <section className="panel">
        <p className="sg-empty">Loading option chain…</p>
      </section>
    );
  }

  if (!chain || rows.length === 0) {
    return (
      <section className="panel">
        <p className="sg-empty">
          Option chain unavailable for {instrument}. The chain republishes on the next poll while
          the backend feed is reachable — no cached ladder is shown.
        </p>
      </section>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="pnl-strip" aria-label="Chain summary">
        <span className="ps">
          <span className="ps-l">Spot</span>
          <span className="ps-v num">{safeNum(chain.spot_price)}</span>
        </span>
        <span className="ps">
          <span className="ps-l">Futures</span>
          <span className="ps-v num">{safeNum(chain.futures_price)}</span>
        </span>
        <span className="ps">
          <span className="ps-l">Expiry</span>
          <span className="ps-v">{fmtExpiry(chain.expiry)}</span>
        </span>
        <span className="ps">
          <span className="ps-l">Strikes</span>
          <span className="ps-v num">{rows.length}</span>
        </span>
        <span className="ps">
          <span className="ps-l">Showing</span>
          <span className="ps-v num">{visible.length}</span>
        </span>
      </div>

      <div className="ds-filters">
        <span className="seg" title="Strike window around ATM">
          {WINDOWS.map((option) => (
            <button
              key={option.id}
              type="button"
              className="seg-btn"
              data-active={windowId === option.id}
              onClick={() => setWindowId(option.id)}
            >
              {option.label}
            </button>
          ))}
        </span>
        <span className="sg-note">
          Premiums and Greeks print from the live chain; empty legs mean the backend published no
          quote for that strike.
        </span>
      </div>

      <div className="tbl-scroll">
        <table className="sg-table">
          <thead>
            <tr>
              <th>Strike</th>
              <th className="r">Call LTP</th>
              <th className="r">Call OI</th>
              <th className="r">Call IV %</th>
              <th className="r">Call Δ</th>
              <th className="r">Put LTP</th>
              <th className="r">Put OI</th>
              <th className="r">Put IV %</th>
              <th className="r">Put Δ</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => {
              const call = row.raw.call as Record<string, unknown> | null | undefined;
              const put = row.raw.put as Record<string, unknown> | null | undefined;
              const callGreeks =
                call && typeof call.greeks === 'object' ? (call.greeks as Record<string, unknown>) : null;
              const putGreeks =
                put && typeof put.greeks === 'object' ? (put.greeks as Record<string, unknown>) : null;
              return (
                <tr key={row.strike} data-active={row.is_atm}>
                  <td>
                    <span className="sg-sym num">{safeNum(row.strike, '—', 0)}</span>{' '}
                    {row.is_atm ? <span className="sg-tag info">ATM</span> : null}
                  </td>
                  <td className="r num">{safeNum(toNumber(call?.ltp))}</td>
                  <td className="r num">{safeInt(toNumber(call?.open_interest))}</td>
                  <td className="r num">{safeNum(callGreeks ? toNumber(callGreeks.iv) : null, '—', 1)}</td>
                  <td className="r num">{safeNum(callGreeks ? toNumber(callGreeks.delta) : null)}</td>
                  <td className="r num">{safeNum(toNumber(put?.ltp))}</td>
                  <td className="r num">{safeInt(toNumber(put?.open_interest))}</td>
                  <td className="r num">{safeNum(putGreeks ? toNumber(putGreeks.iv) : null, '—', 1)}</td>
                  <td className="r num">{safeNum(putGreeks ? toNumber(putGreeks.delta) : null)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
