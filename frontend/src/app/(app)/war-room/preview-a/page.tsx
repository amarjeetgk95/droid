'use client';

import Link from 'next/link';

/**
 * Preview A — Kite-minimal (STATIC MOCK, no backend).
 * Generous whitespace, quiet borders, one accent, plain rows.
 * Route: /war-room/preview-a
 */

const SIGNALS = [
  { dir: 'BUY', contract: 'NIFTY 23400 CE', e: '234.5', t1: '268.0', sl: '218.0', rr: '2.0', conf: 88, ago: '2m ago', strat: 'ORB Breakout' },
  { dir: 'BUY', contract: 'NIFTY 23350 CE', e: '198.0', t1: '224.0', sl: '184.0', rr: '1.9', conf: 82, ago: '6m ago', strat: 'VWAP Bounce' },
  { dir: 'SELL', contract: 'NIFTY 23300 PE', e: '176.5', t1: '152.0', sl: '189.0', rr: '2.0', conf: 74, ago: '11m ago', strat: 'Breakdown Retest' },
];

const LEVELS = [
  { l: 'R2', v: '23,480' },
  { l: 'R1', v: '23,400' },
  { l: 'Spot', v: '23,320' },
  { l: 'S1', v: '23,240' },
  { l: 'S2', v: '23,160' },
];

export default function WarRoomPreviewA() {
  return (
    <div style={{ background: 'var(--ds-page)', minHeight: '100vh' }}>
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '28px 20px 60px', display: 'flex', flexDirection: 'column', gap: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: 'var(--ds-text-secondary)' }}>
          <span style={{ background: 'var(--ds-warn-wash)', border: '1px solid rgba(245,158,11,.35)', color: 'var(--ds-warn-strong)', borderRadius: 4, padding: '2px 8px', fontWeight: 700 }}>
            MOCK A · KITE-MINIMAL
          </span>
          <span>Static preview — no live data.</span>
          <span style={{ flex: 1 }} />
          <Link href="/war-room/preview-b" style={{ color: 'var(--ds-accent)', fontWeight: 600 }}>Compare with Mock B →</Link>
        </div>

        {/* Header — plain, lots of air */}
        <header style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>War Room</h1>
          <span style={{ fontSize: 13, color: 'var(--ds-text-secondary)' }}>NIFTY 50 · 5 min · Tuesday session</span>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 12, color: 'var(--ds-text-secondary)' }}>Feed live · updated just now</span>
        </header>

        {/* Verdict — calm, no gradient hero */}
        <section className="card">
          <div className="card-bd" style={{ padding: '20px 22px', display: 'flex', gap: 28, flexWrap: 'wrap', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.08em', color: 'var(--ds-text-secondary)' }}>TACTICAL BIAS</div>
              <div style={{ fontSize: 30, fontWeight: 700, color: 'var(--ds-bull-strong)', marginTop: 4 }}>▲ Bullish</div>
              <div style={{ fontSize: 13, color: 'var(--ds-text-secondary)', marginTop: 2 }}>Favour calls above support · invalidation below 23,240</div>
            </div>
            <div style={{ display: 'flex', gap: 28 }}>
              {[
                ['Spot', '23,320.5'],
                ['Target', '23,460.0'],
                ['Stop', '23,240.0'],
                ['Confidence', '82%'],
              ].map(([l, v]) => (
                <div key={l}>
                  <div style={{ fontSize: 11, color: 'var(--ds-text-secondary)', fontWeight: 600 }}>{l}</div>
                  <div className="num" style={{ fontSize: 17, fontWeight: 700 }}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Context strip — plain text row, no pills */}
        <div style={{ display: 'flex', gap: 24, fontSize: 13, color: 'var(--ds-text-secondary)', padding: '0 4px', flexWrap: 'wrap' }}>
          <span>PCR <b style={{ color: 'var(--ds-ink)' }}>0.92</b></span>
          <span>Max pain <b style={{ color: 'var(--ds-ink)' }}>23,300</b></span>
          <span>FII net <b style={{ color: 'var(--ds-bull-strong)' }}>+1,200 Cr</b></span>
          <span>Trend <b style={{ color: 'var(--ds-ink)' }}>1m ▲ · 5m ▲ · 15m – · 1h ▲</b></span>
        </div>

        {/* Signals — divider rows, no boxes-in-boxes */}
        <section>
          <h2 style={{ fontSize: 14, fontWeight: 700, margin: '0 0 4px' }}>Signals</h2>
          <p style={{ fontSize: 12, color: 'var(--ds-text-secondary)', margin: '0 0 8px' }}>3 active · tap a row for detail (mock)</p>
          <div className="card">
            {SIGNALS.map((s, i) => (
              <div
                key={i}
                style={{
                  display: 'flex', alignItems: 'center', gap: 16, padding: '14px 18px',
                  borderBottom: i < SIGNALS.length - 1 ? '1px solid var(--ds-border-subtle)' : 0,
                }}
              >
                <span style={{ fontSize: 12, fontWeight: 700, color: s.dir === 'BUY' ? 'var(--ds-bull-strong)' : 'var(--ds-bear-strong)', minWidth: 44 }}>
                  {s.dir === 'BUY' ? '▲ BUY' : '▼ SELL'}
                </span>
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 14, fontWeight: 600 }}>{s.contract}</span>
                  <span style={{ display: 'block', fontSize: 12, color: 'var(--ds-text-secondary)' }}>{s.strat} · {s.ago}</span>
                </span>
                <span style={{ flex: 1 }} />
                <span className="num" style={{ fontSize: 13 }}>E {s.e}</span>
                <span className="num" style={{ fontSize: 13, color: 'var(--ds-bull-strong)' }}>T {s.t1}</span>
                <span className="num" style={{ fontSize: 13, color: 'var(--ds-bear-strong)' }}>SL {s.sl}</span>
                <span className="num" style={{ fontSize: 13 }}>1:{s.rr}</span>
                <span className="num" style={{ fontSize: 13, fontWeight: 700 }}>{s.conf}%</span>
              </div>
            ))}
          </div>
        </section>

        {/* Levels + algo — two quiet cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 20 }}>
          <section className="card">
            <div className="card-bd" style={{ padding: '16px 20px' }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, margin: '0 0 8px' }}>Key levels</h3>
              {LEVELS.map((r) => (
                <div key={r.l} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid var(--ds-border-subtle)', fontSize: 13 }}>
                  <span style={{ color: 'var(--ds-text-secondary)' }}>{r.l}</span>
                  <span className="num" style={{ fontWeight: 600 }}>{r.v}</span>
                </div>
              ))}
            </div>
          </section>
          <section className="card">
            <div className="card-bd" style={{ padding: '16px 20px', fontSize: 13 }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, margin: '0 0 8px' }}>Algo · Paper</h3>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>
                <span style={{ color: 'var(--ds-text-secondary)' }}>Open positions</span><b>2</b>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>
                <span style={{ color: 'var(--ds-text-secondary)' }}>Unrealised P&amp;L</span><b style={{ color: 'var(--ds-bull-strong)' }}>+₹4,250</b>
              </div>
              <button type="button" className="btn w-full" style={{ marginTop: 12 }}>Open full option chain</button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
