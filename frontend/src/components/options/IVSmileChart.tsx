'use client';

import { Card, fmtNum } from '@/components/ui/desk';
import { OptionChainStrikeRow } from '@/lib/types';

export function IVSmileChart({
  strikes,
  atmStrike,
}: {
  strikes: OptionChainStrikeRow[];
  atmStrike: number;
}) {
  if (!strikes || strikes.length === 0) return null;

  // Filter strikes that have IV values
  const validPoints = strikes
    .filter((s) => s.call?.greeks?.iv || s.put?.greeks?.iv)
    .map((s) => ({
      strike: s.strike,
      ce_iv: s.call?.greeks?.iv || null,
      pe_iv: s.put?.greeks?.iv || null,
      is_atm: s.is_atm,
    }));

  if (validPoints.length === 0) return null;

  const allIvs = validPoints
    .flatMap((p) => [p.ce_iv, p.pe_iv])
    .filter((v): v is number => v !== null && v > 0);

  const minIv = Math.max(5, Math.floor(Math.min(...allIvs, 10)) - 2);
  const maxIv = Math.ceil(Math.max(...allIvs, 25)) + 2;

  return (
    <Card
      title="IV smile & skew"
      meta={`ATM ${atmStrike} · IV ${minIv}%–${maxIv}%`}
    >
      <div
        style={{ height: 224, display: 'flex', alignItems: 'flex-end', gap: 4, padding: '16px 8px 28px', overflowX: 'auto', borderBottom: '1px solid var(--ds-border)' }}
      >
        {validPoints.map((pt) => {
          const ceHeight = pt.ce_iv ? ((pt.ce_iv - minIv) / (maxIv - minIv)) * 100 : null;
          const peHeight = pt.pe_iv ? ((pt.pe_iv - minIv) / (maxIv - minIv)) * 100 : null;

          return (
            <div
              key={pt.strike}
              title={`Strike ${pt.strike}${pt.ce_iv ? ` · Call IV ${fmtNum(pt.ce_iv, 1)}%` : ''}${pt.pe_iv ? ` · Put IV ${fmtNum(pt.pe_iv, 1)}%` : ''}`}
              style={{ flex: 1, minWidth: 28, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', alignItems: 'center', position: 'relative' }}
            >
              {pt.is_atm && (
                <div style={{ position: 'absolute', inset: 0, width: 1, margin: '0 auto', background: 'var(--ds-border-strong)' }} />
              )}
              {ceHeight !== null && (
                <div
                  style={{ position: 'absolute', bottom: `${Math.min(95, Math.max(5, ceHeight))}%`, width: 8, height: 8, borderRadius: 999, background: 'var(--ds-accent)' }}
                />
              )}
              {peHeight !== null && (
                <div
                  style={{ position: 'absolute', bottom: `${Math.min(95, Math.max(5, peHeight))}%`, width: 8, height: 8, borderRadius: 999, background: 'var(--ds-warn)' }}
                />
              )}
              <span
                className="mono"
                style={{ fontSize: 9, position: 'absolute', bottom: -20, transform: 'rotate(-45deg)', transformOrigin: 'top left', color: pt.is_atm ? 'var(--ds-accent-ink)' : 'var(--ds-ink-3)', fontWeight: pt.is_atm ? 700 : 400 }}
              >
                {pt.strike}
              </span>
            </div>
          );
        })}
      </div>

      <div className="toolbar" style={{ marginTop: 8 }}>
        <span className="faint" style={{ fontSize: 11 }}>
          <i style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 999, background: 'var(--ds-accent)', marginRight: 5 }} />
          Call IV (CE)
        </span>
        <span className="faint" style={{ fontSize: 11 }}>
          <i style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 999, background: 'var(--ds-warn)', marginRight: 5 }} />
          Put IV (PE)
        </span>
        <span className="spacer" />
        <span className="faint num" style={{ fontSize: 11 }}>ATM {atmStrike}</span>
      </div>
    </Card>
  );
}
