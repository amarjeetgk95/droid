'use client';

import { Card, EmptyNote, fmtINR } from '@/components/ui/desk';
import { MaxPainResult } from '@/lib/types';

export function PayoffChart({
  data,
  spotPrice,
}: {
  data: MaxPainResult | null;
  spotPrice: number;
}) {
  if (!data || data.strikes.length === 0) {
    return (
      <Card title="Max pain payout" meta="—">
        <EmptyNote>No Max Pain payout distribution available for this expiry.</EmptyNote>
      </Card>
    );
  }

  const maxPayout = Math.max(...data.payouts, 1);
  const minPayout = Math.min(...data.payouts);

  return (
    <Card
      title="Max pain payout"
      meta={`Min payout ${fmtINR(data.max_pain_strike)}`}
    >
      <div
        className="num"
        style={{ height: 224, display: 'flex', alignItems: 'flex-end', gap: 6, padding: '16px 8px 28px', overflowX: 'auto', borderBottom: '1px solid var(--ds-border)' }}
      >
        {data.strikes.map((strike, idx) => {
          const payout = data.payouts[idx];
          const heightPercent = Math.max(8, ((payout - minPayout) / (maxPayout - minPayout || 1)) * 100);
          const isMaxPain = strike === data.max_pain_strike;
          const isSpotNear = Math.abs(strike - spotPrice) <= 50;

          return (
            <div key={strike} title={`Strike ${strike} · Payout ₹${(payout / 10000000).toFixed(2)} Cr`} style={{ flex: 1, minWidth: 28, height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', gap: 4 }}>
              <div
                style={{
                  height: `${heightPercent}%`,
                  width: '100%',
                  borderRadius: 3,
                  background: isMaxPain
                    ? 'var(--ds-warn)'
                    : isSpotNear
                      ? 'var(--ds-accent)'
                      : 'var(--ds-inset)',
                  border: '1px solid var(--ds-border)',
                }}
              />
              <span
                className="mono"
                style={{ fontSize: 9, transform: 'rotate(-45deg)', transformOrigin: 'top left', marginTop: 6, color: isMaxPain ? 'var(--ds-warn)' : 'var(--ds-ink-3)', fontWeight: isMaxPain ? 700 : 400 }}
              >
                {strike}
              </span>
            </div>
          );
        })}
      </div>

      <div className="toolbar" style={{ marginTop: 8 }}>
        <span className="faint" style={{ fontSize: 11 }}>
          <i style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: 'var(--ds-warn)', marginRight: 5 }} />
          Max pain strike
        </span>
        <span className="faint" style={{ fontSize: 11 }}>
          <i style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: 'var(--ds-accent)', marginRight: 5 }} />
          Near spot strike
        </span>
        <span className="spacer" />
        <span className="faint" style={{ fontSize: 11 }}>Total option loss minimization model</span>
      </div>
    </Card>
  );
}
