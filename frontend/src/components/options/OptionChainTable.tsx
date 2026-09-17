'use client';

import { useCallback, type CSSProperties, type KeyboardEvent } from 'react';
import { Card, EmptyNote, fmtINR, fmtNum } from '@/components/ui/desk';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import type { OptionChainStrikeRow } from '@/lib/types';

const STANDARD_CALL_HEADS = ['OI', 'Vol', 'Bid', 'Ask', 'LTP', 'IV%'] as const;
const STANDARD_PUT_HEADS = ['IV%', 'LTP', 'Bid', 'Ask', 'Vol', 'OI'] as const;
const GREEKS_CALL_HEADS = ['Delta', 'Gamma', 'Theta', 'Vega', 'LTP', 'IV%'] as const;
const GREEKS_PUT_HEADS = ['IV%', 'LTP', 'Delta', 'Gamma', 'Theta', 'Vega'] as const;

/** Quantity in the same `k` convention the War Room chain drawer uses. */
export function fmtQty(v: number | null | undefined): string {
  if (typeof v !== 'number' || !Number.isFinite(v) || v <= 0) return '—';
  if (v < 1000) return String(Math.round(v));
  return `${Math.round(v / 1000)}k`;
}

function fmtPrice(v: number | null | undefined): string {
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? fmtINR(v) : '—';
}

function fmtIv(v: number | null | undefined): string {
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? `${fmtNum(v, 1)}%` : '—';
}

const STICKY_ROW1: CSSProperties = { position: 'sticky', top: 0, zIndex: 3 };
const STICKY_ROW2: CSSProperties = { position: 'sticky', top: 24, zIndex: 2 };

export function OptionChainTable({
  strikes,
  viewMode,
  spotPrice,
  asOf = null,
  marketClosed = false,
  fetching = false,
}: {
  strikes: OptionChainStrikeRow[];
  viewMode: 'standard' | 'greeks';
  spotPrice: number;
  asOf?: string | null;
  marketClosed?: boolean;
  fetching?: boolean;
}) {
  const onScrollKeyDown = useCallback((e: KeyboardEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    switch (e.key) {
      case 'ArrowRight':
        el.scrollLeft += 48;
        break;
      case 'ArrowLeft':
        el.scrollLeft -= 48;
        break;
      case 'ArrowDown':
        el.scrollTop += 40;
        break;
      case 'ArrowUp':
        el.scrollTop -= 40;
        break;
      default:
        return;
    }
    e.preventDefault();
  }, []);

  const callHeads = viewMode === 'standard' ? STANDARD_CALL_HEADS : GREEKS_CALL_HEADS;
  const putHeads = viewMode === 'standard' ? STANDARD_PUT_HEADS : GREEKS_PUT_HEADS;

  return (
    <Card
      title="Option chain"
      meta={`${strikes.length} strikes${spotPrice > 0 ? ` · spot ${fmtINR(spotPrice)}` : ''}`}
      action={
        <FreshnessClock
          lastAt={asOf}
          fetching={fetching}
          marketClosed={marketClosed}
          sourceLabel="REST snapshot"
        />
      }
    >
      {strikes.length === 0 ? (
        <EmptyNote>No option contracts available for this expiry.</EmptyNote>
      ) : (
        <div
          className="tbl-scroll"
          role="region"
          aria-label="Option chain matrix. Use the arrow keys to scroll horizontally and vertically."
          tabIndex={0}
          onKeyDown={onScrollKeyDown}
          style={{ maxHeight: 640, border: '1px solid var(--ds-border)', borderRadius: 4 }}
        >
          <table className="tbl num">
            <caption className="sr-only">
              Option chain, {strikes.length} strikes
              {spotPrice > 0 ? `, spot ${fmtINR(spotPrice)}` : ''}. Columns left to right: call open interest, volume,
              bid, ask, last traded price and implied volatility; strike; put implied volatility, last traded price,
              bid, ask, volume and open interest.
            </caption>
            <thead>
              <tr className="c">
                <th
                  scope="colgroup"
                  colSpan={6}
                  style={{ ...STICKY_ROW1, background: 'var(--ds-bull-wash)', color: 'var(--ds-bull-strong)' }}
                >
                  Calls · CE
                </th>
                <th
                  scope="col"
                  rowSpan={2}
                  style={{
                    position: 'sticky',
                    top: 0,
                    left: 0,
                    zIndex: 5,
                    background: 'var(--ds-accent-wash)',
                    color: 'var(--ds-accent)',
                    boxShadow: 'inset -1px 0 0 var(--ds-border)',
                  }}
                >
                  Strike
                </th>
                <th
                  scope="colgroup"
                  colSpan={6}
                  style={{ ...STICKY_ROW1, background: 'var(--ds-bear-wash)', color: 'var(--ds-bear-strong)' }}
                >
                  Puts · PE
                </th>
              </tr>
              <tr>
                {callHeads.map((head) => (
                  <th key={`ce-${head}`} scope="col" className="r" style={STICKY_ROW2}>
                    {head}
                  </th>
                ))}
                {putHeads.map((head) => (
                  <th key={`pe-${head}`} scope="col" style={STICKY_ROW2}>
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {strikes.map((row) => {
                const ce = row.call;
                const pe = row.put;
                const isAtm = row.is_atm;
                const isCallItm = spotPrice > 0 && row.strike < spotPrice;
                const isPutItm = spotPrice > 0 && row.strike > spotPrice;
                const callBg = isAtm ? 'var(--ds-accent-wash)' : isCallItm ? 'var(--ds-inset)' : undefined;
                const putBg = isAtm ? 'var(--ds-accent-wash)' : isPutItm ? 'var(--ds-inset)' : undefined;

                return (
                  <tr
                    key={row.strike}
                    style={isAtm ? { background: 'var(--ds-accent-wash)' } : undefined}
                  >
                    {viewMode === 'standard' ? (
                      <>
                        <td className="r" style={{ background: callBg }}>{fmtQty(ce?.open_interest)}</td>
                        <td className="r" style={{ background: callBg }}>{fmtQty(ce?.volume)}</td>
                        <td className="r muted" style={{ background: callBg }}>{fmtPrice(ce?.bid)}</td>
                        <td className="r muted" style={{ background: callBg }}>{fmtPrice(ce?.ask)}</td>
                        <td className="r" style={{ fontWeight: 700, background: callBg }}>{fmtPrice(ce?.ltp)}</td>
                        <td className="r muted" style={{ background: callBg }}>{fmtIv(ce?.greeks?.iv)}</td>
                      </>
                    ) : (
                      <>
                        <td className="r" style={{ background: callBg }}>{fmtNum(ce?.greeks?.delta, 3)}</td>
                        <td className="r muted" style={{ background: callBg }}>{fmtNum(ce?.greeks?.gamma, 5)}</td>
                        <td className="r" style={{ background: callBg }}>{fmtNum(ce?.greeks?.theta)}</td>
                        <td className="r" style={{ background: callBg }}>{fmtNum(ce?.greeks?.vega)}</td>
                        <td className="r" style={{ fontWeight: 700, background: callBg }}>{fmtPrice(ce?.ltp)}</td>
                        <td className="r muted" style={{ background: callBg }}>{fmtIv(ce?.greeks?.iv)}</td>
                      </>
                    )}
                    <td
                      className="c"
                      style={{
                        position: 'sticky',
                        left: 0,
                        zIndex: 1,
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                        background: isAtm ? 'var(--ds-accent-wash)' : 'var(--ds-surface-subtle)',
                        boxShadow: 'inset -1px 0 0 var(--ds-border)',
                      }}
                    >
                      {row.strike.toLocaleString('en-IN')}
                      {isAtm && (
                        <span className="badge b-info" style={{ marginLeft: 6 }}>
                          ATM
                        </span>
                      )}
                    </td>
                    {viewMode === 'standard' ? (
                      <>
                        <td className="muted" style={{ background: putBg }}>{fmtIv(pe?.greeks?.iv)}</td>
                        <td style={{ fontWeight: 700, background: putBg }}>{fmtPrice(pe?.ltp)}</td>
                        <td className="muted" style={{ background: putBg }}>{fmtPrice(pe?.bid)}</td>
                        <td className="muted" style={{ background: putBg }}>{fmtPrice(pe?.ask)}</td>
                        <td style={{ background: putBg }}>{fmtQty(pe?.volume)}</td>
                        <td style={{ background: putBg }}>{fmtQty(pe?.open_interest)}</td>
                      </>
                    ) : (
                      <>
                        <td className="muted" style={{ background: putBg }}>{fmtIv(pe?.greeks?.iv)}</td>
                        <td style={{ fontWeight: 700, background: putBg }}>{fmtPrice(pe?.ltp)}</td>
                        <td className="muted" style={{ background: putBg }}>{fmtNum(pe?.greeks?.delta, 3)}</td>
                        <td className="muted" style={{ background: putBg }}>{fmtNum(pe?.greeks?.gamma, 5)}</td>
                        <td style={{ background: putBg }}>{fmtNum(pe?.greeks?.theta)}</td>
                        <td style={{ background: putBg }}>{fmtNum(pe?.greeks?.vega)}</td>
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {strikes.length > 0 ? (
        <p className="faint" style={{ margin: '6px 0 0', fontSize: 11 }}>
          Scroll horizontally for all 13 columns · Strike column is frozen · focus the table and use the arrow keys to
          pan.
        </p>
      ) : null}
    </Card>
  );
}
