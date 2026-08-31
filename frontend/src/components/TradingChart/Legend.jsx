import React from 'react';
import { COLORS } from './constants';
import { fmtP } from './utils';

export default function Legend({ symbol = 'BTCUSDT', data, hoverIdx, tf }) {
  const d = data[hoverIdx];
  if (!d) return null;

  const up = d.c >= d.o;
  const col = up ? COLORS.up : COLORS.down;
  const chg = ((d.c - d.o) / d.o * 100).toFixed(2);
  const prev = data[hoverIdx - 1];
  const delta = prev ? d.c - prev.c : 0;
  const dPct = prev ? (delta / prev.c) * 100 : 0;
  const tfLabel = tf >= 1440 ? '1D' : tf >= 60 ? tf / 60 + 'H' : tf + 'm';

  return (
    <div className="absolute left-3 top-2 text-[12px] pointer-events-none leading-[18px] text-[#d1d4dc]">
      <div className="font-semibold text-white mb-[2px]">
        {symbol} · {tfLabel}
      </div>
      <div className="flex gap-2 flex-wrap">
        <span className="text-[#787b86]">O</span>
        <span style={{ color: col }}>{fmtP(d.o)}</span>
        <span className="text-[#787b86]">H</span>
        <span style={{ color: col }}>{fmtP(d.h)}</span>
        <span className="text-[#787b86]">L</span>
        <span style={{ color: col }}>{fmtP(d.l)}</span>
        <span className="text-[#787b86]">C</span>
        <span style={{ color: col }}>{fmtP(d.c)}</span>
        <span style={{ color: col }}>
          {up ? '+' : ''}
          {chg}%
        </span>
        <span className="text-[#787b86]">Δ</span>
        <span style={{ color: delta >= 0 ? COLORS.up : COLORS.down }}>
          {delta >= 0 ? '+' : ''}
          {fmtP(delta)} ({dPct >= 0 ? '+' : ''}
          {dPct.toFixed(2)}%)
        </span>
      </div>
    </div>
  );
}
