'use client';

import { Card, EmptyNote, fmtINR, fmtNum } from '@/components/ui/desk';
import { OptionChainStrikeRow } from '@/lib/types';

export function OptionChainTable({
  strikes,
  viewMode,
  spotPrice,
}: {
  strikes: OptionChainStrikeRow[];
  viewMode: 'standard' | 'greeks';
  spotPrice: number;
}) {
  return (
    <Card
      title="Option chain"
      meta={`${strikes.length} strikes${spotPrice ? ` · spot ${fmtINR(spotPrice)}` : ''}`}
    >
      {strikes.length === 0 ? (
        <EmptyNote>No option contracts available for this expiry.</EmptyNote>
      ) : (
        <div className="tbl-wrap" style={{ maxHeight: 640, overflowY: 'auto', border: '1px solid var(--ds-border)', borderRadius: 4 }}>
          <table className="tbl num">
            <thead style={{ position: 'sticky', top: 0, zIndex: 2 }}>
              <tr className="c">
                <th colSpan={6} className="c" style={{ background: 'var(--ds-bull-wash)', color: 'var(--ds-bull-strong)' }}>Calls · CE</th>
                <th className="c" style={{ background: 'var(--ds-accent-wash)', color: 'var(--ds-accent)' }}>Strike</th>
                <th colSpan={6} className="c" style={{ background: 'var(--ds-bear-wash)', color: 'var(--ds-bear-strong)' }}>Puts · PE</th>
              </tr>
              <tr>
                {viewMode === 'standard' ? (
                  <>
                    <th className="r">OI</th>
                    <th className="r">Vol</th>
                    <th className="r">Bid</th>
                    <th className="r">Ask</th>
                    <th className="r">LTP</th>
                    <th className="r">IV%</th>
                  </>
                ) : (
                  <>
                    <th className="r">Delta</th>
                    <th className="r">Gamma</th>
                    <th className="r">Theta</th>
                    <th className="r">Vega</th>
                    <th className="r">LTP</th>
                    <th className="r">IV%</th>
                  </>
                )}
                <th className="c">Strike</th>
                {viewMode === 'standard' ? (
                  <>
                    <th>IV%</th>
                    <th>LTP</th>
                    <th>Bid</th>
                    <th>Ask</th>
                    <th>Vol</th>
                    <th>OI</th>
                  </>
                ) : (
                  <>
                    <th>IV%</th>
                    <th>LTP</th>
                    <th>Delta</th>
                    <th>Gamma</th>
                    <th>Theta</th>
                    <th>Vega</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {strikes.map((row) => {
                const ce = row.call;
                const pe = row.put;
                const isAtm = row.is_atm;
                const isCallItm = spotPrice > 0 && row.strike < spotPrice;
                const isPutItm = spotPrice > 0 && row.strike > spotPrice;
                const callBg = isAtm ? 'var(--ds-accent-wash)' : isCallItm ? '#fffdf4' : undefined;
                const putBg = isAtm ? 'var(--ds-accent-wash)' : isPutItm ? '#fffdf4' : undefined;

                return (
                  <tr
                    key={row.strike}
                    style={isAtm ? { background: 'var(--ds-accent-wash)' } : undefined}
                  >
                    {viewMode === 'standard' ? (
                      <>
                        <td className="r" style={{ background: callBg }}>{ce?.open_interest ? ce.open_interest.toLocaleString('en-IN') : '—'}</td>
                        <td className="r" style={{ background: callBg }}>{ce?.volume ? ce.volume.toLocaleString('en-IN') : '—'}</td>
                        <td className="r muted" style={{ background: callBg }}>{ce?.bid ? fmtNum(ce.bid) : '—'}</td>
                        <td className="r muted" style={{ background: callBg }}>{ce?.ask ? fmtNum(ce.ask) : '—'}</td>
                        <td className="r" style={{ fontWeight: 700, background: callBg }}>{ce?.ltp ? fmtINR(ce.ltp) : '—'}</td>
                        <td className="r muted" style={{ background: callBg }}>{ce?.greeks?.iv != null ? `${fmtNum(ce.greeks.iv, 1)}%` : '—'}</td>
                      </>
                    ) : (
                      <>
                        <td className="r" style={{ background: callBg }}>{ce?.greeks?.delta !== undefined ? fmtNum(ce.greeks.delta, 3) : '—'}</td>
                        <td className="r muted" style={{ background: callBg }}>{ce?.greeks?.gamma !== undefined ? fmtNum(ce.greeks.gamma, 5) : '—'}</td>
                        <td className="r" style={{ background: callBg }}>{ce?.greeks?.theta !== undefined ? fmtNum(ce.greeks.theta) : '—'}</td>
                        <td className="r" style={{ background: callBg }}>{ce?.greeks?.vega !== undefined ? fmtNum(ce.greeks.vega) : '—'}</td>
                        <td className="r" style={{ fontWeight: 700, background: callBg }}>{ce?.ltp ? fmtINR(ce.ltp) : '—'}</td>
                        <td className="r muted" style={{ background: callBg }}>{ce?.greeks?.iv != null ? `${fmtNum(ce.greeks.iv, 1)}%` : '—'}</td>
                      </>
                    )}
                    <td className="c" style={{ fontWeight: 700, whiteSpace: 'nowrap', background: isAtm ? 'var(--ds-accent-wash)' : 'var(--ds-surface-subtle)' }}>
                      {row.strike.toLocaleString('en-IN')}
                      {isAtm && (
                        <span className="badge b-info" style={{ marginLeft: 6 }}>
                          ATM
                        </span>
                      )}
                    </td>
                    {viewMode === 'standard' ? (
                      <>
                        <td className="muted" style={{ background: putBg }}>{pe?.greeks?.iv != null ? `${fmtNum(pe.greeks.iv, 1)}%` : '—'}</td>
                        <td style={{ fontWeight: 700, background: putBg }}>{pe?.ltp ? fmtINR(pe.ltp) : '—'}</td>
                        <td className="muted" style={{ background: putBg }}>{pe?.bid ? fmtNum(pe.bid) : '—'}</td>
                        <td className="muted" style={{ background: putBg }}>{pe?.ask ? fmtNum(pe.ask) : '—'}</td>
                        <td style={{ background: putBg }}>{pe?.volume ? pe.volume.toLocaleString('en-IN') : '—'}</td>
                        <td style={{ background: putBg }}>{pe?.open_interest ? pe.open_interest.toLocaleString('en-IN') : '—'}</td>
                      </>
                    ) : (
                      <>
                        <td className="muted" style={{ background: putBg }}>{pe?.greeks?.iv != null ? `${fmtNum(pe.greeks.iv, 1)}%` : '—'}</td>
                        <td style={{ fontWeight: 700, background: putBg }}>{pe?.ltp ? fmtINR(pe.ltp) : '—'}</td>
                        <td className="muted" style={{ background: putBg }}>{pe?.greeks?.delta !== undefined ? fmtNum(pe.greeks.delta, 3) : '—'}</td>
                        <td className="muted" style={{ background: putBg }}>{pe?.greeks?.gamma !== undefined ? fmtNum(pe.greeks.gamma, 5) : '—'}</td>
                        <td style={{ background: putBg }}>{pe?.greeks?.theta !== undefined ? fmtNum(pe.greeks.theta) : '—'}</td>
                        <td style={{ background: putBg }}>{pe?.greeks?.vega !== undefined ? fmtNum(pe.greeks.vega) : '—'}</td>
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
