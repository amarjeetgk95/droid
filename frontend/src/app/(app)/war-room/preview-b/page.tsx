'use client';

import Link from 'next/link';

/**
 * Preview B — Terminal-dense (STATIC MOCK, no backend).
 * Tight tables, mono numerals, everything above the fold.
 * Route: /war-room/preview-b
 */

const ROWS = [
  { d: 'BUY', sym: 'NIFTY 23400CE', strat: 'orb', e: '234.5', t: '268.0', sl: '218.0', rr: '2.0', c: 88, age: '2m' },
  { d: 'BUY', sym: 'NIFTY 23350CE', strat: 'vwap', e: '198.0', t: '224.0', sl: '184.0', rr: '1.9', c: 82, age: '6m' },
  { d: 'SELL', sym: 'NIFTY 23300PE', strat: 'brk-ret', e: '176.5', t: '152.0', sl: '189.0', rr: '2.0', c: 74, age: '11m' },
  { d: 'BUY', sym: 'BANKNIFTY 56200CE', strat: 'orb', e: '312.0', t: '388.0', sl: '274.0', rr: '2.0', c: 79, age: '14m' },
  { d: 'SELL', sym: 'NIFTY 23250PE', strat: 'mom', e: '142.0', t: '118.5', sl: '154.0', rr: '2.0', c: 68, age: '19m' },
];

export default function WarRoomPreviewB() {
  return (
    <div style={{ background: 'var(--ds-page)', minHeight: '100vh', fontSize: 12 }}>
      <div style={{ maxWidth: 1440, margin: '0 auto', padding: '10px 12px 40px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'var(--ds-text-secondary)' }}>
          <span style={{ background: 'var(--ds-accent-wash)', border: '1px solid rgba(37,99,235,.4)', color: 'var(--ds-accent)', borderRadius: 3, padding: '1px 7px', fontWeight: 700, fontFamily: 'var(--ds-mono)' }}>
            MOCK B · TERMINAL-DENSE
          </span>
          <span className="mono">static · no live data</span>
          <span style={{ flex: 1 }} />
          <Link href="/war-room/preview-a" style={{ color: 'var(--ds-accent)', fontWeight: 600 }}>Compare with Mock A →</Link>
        </div>

        {/* Command strip */}
        <div className="sg-bar" style={{ padding: '6px 10px' }}>
          <span className="sg-title">WAR ROOM</span>
          <div className="sg-seg" aria-label="Instrument (mock)">
            {['NIFTY', 'BANK', 'SENSEX'].map((x, i) => (
              <button key={x} type="button" aria-selected={i === 0}>{x}</button>
            ))}
          </div>
          <div className="sg-seg" aria-label="Timeframe (mock)">
            {['1m', '5m', '15m', '1h'].map((x, i) => (
              <button key={x} type="button" aria-selected={i === 1}>{x}</button>
            ))}
          </div>
          <span className="sg-live on"><i />LIVE</span>
          <span className="sg-tools">
            <span className="sg-num">PCR 0.92</span>
            <span className="sg-num">MP 23300</span>
            <span className="sg-num">FII +1200Cr</span>
          </span>
        </div>

        {/* Verdict strip */}
        <div className="sg-strip">
          <span className="sg-cell"><span className="l">Bias</span><span className="v pos-num">▲ BULLISH 82%</span></span>
          <span className="sg-cell"><span className="l">Spot</span><span className="v">23,320.5</span></span>
          <span className="sg-cell"><span className="l">Tgt</span><span className="v pos-num">23,460.0</span></span>
          <span className="sg-cell"><span className="l">Inv</span><span className="v neg-num">23,240.0</span></span>
          <span className="sg-cell"><span className="l">RR</span><span className="v">1:1.7</span></span>
          <span className="sg-cell"><span className="l">MTF</span><span className="v">1m▲ 5m▲ 15m– 1h▲</span></span>
          <span className="sg-cell"><span className="l">R1/S1</span><span className="v">23400 / 23240</span></span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 300px', gap: 8, alignItems: 'start' }}>
          {/* Signal table */}
          <div className="sg-panel">
            <div className="sg-scroll">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Side</th><th>Contract</th><th>Strat</th>
                    <th className="r">Entry</th><th className="r">T1</th><th className="r">SL</th>
                    <th className="r">RR</th><th>Conf</th><th className="r">Age</th>
                  </tr>
                </thead>
                <tbody>
                  {ROWS.map((r, i) => (
                    <tr key={i}>
                      <td><span className={`sg-dir ${r.d === 'BUY' ? 'long' : 'short'}`}>{r.d}</span></td>
                      <td className="sg-num" style={{ fontWeight: 700 }}>{r.sym}</td>
                      <td className="sg-strat">{r.strat}</td>
                      <td className="sg-num r">{r.e}</td>
                      <td className="sg-num r pos-num">{r.t}</td>
                      <td className="sg-num r neg-num">{r.sl}</td>
                      <td className="sg-num r">1:{r.rr}</td>
                      <td>
                        <span className="sg-conf">
                          <span className="bar"><i style={{ width: `${r.c}%` }} /></span>
                          <span className="sg-num">{r.c}</span>
                        </span>
                      </td>
                      <td className="sg-num r">{r.age}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Right rail */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div className="sg-panel"><div className="sg-pad">
              <h3 className="sg-sect">Levels</h3>
              <div className="sg-num" style={{ display: 'grid', gap: 3 }}>
                {[['R2', '23,480'], ['R1', '23,400'], ['SPOT', '23,320.5'], ['S1', '23,240'], ['S2', '23,160']].map(([l, v]) => (
                  <div key={l} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--ds-border-subtle)', padding: '2px 0' }}>
                    <span style={{ color: 'var(--ds-ink-3)' }}>{l}</span><b>{v}</b>
                  </div>
                ))}
              </div>
            </div></div>
            <div className="sg-panel"><div className="sg-pad">
              <h3 className="sg-sect">Algo · PAPER</h3>
              <div className="sg-statgrid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <div className="sg-stat"><span className="l">Open</span><span className="v">2</span></div>
                <div className="sg-stat"><span className="l">P&amp;L</span><span className="v pos-num">+4.2k</span></div>
              </div>
              <button type="button" className="sg-primary" style={{ width: '100%', justifyContent: 'center', marginTop: 8 }}>CHAIN (O)</button>
            </div></div>
          </div>
        </div>
      </div>
    </div>
  );
}
