import React, { useState, useEffect } from 'react';
import { fmtFull } from './utils';

export default function StatusBar({ data, view }) {
  const [clock, setClock] = useState('--:--:--');

  useEffect(() => {
    const p = (n) => String(n).padStart(2, '0');
    const tick = () => {
      const d = new Date();
      setClock(p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ':' + p(d.getUTCSeconds()));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  let rangeInfo = '';
  if (data.length) {
    const s = Math.max(0, Math.floor(view.start));
    const e = Math.min(data.length, Math.ceil(view.start + view.count));
    if (e > s) {
      const a = data[s];
      const b = data[e - 1];
      const rng = ((b.c - a.c) / a.c) * 100;
      rangeInfo =
        `${e - s} bars · ${fmtFull(a.t)} → ${fmtFull(b.t)} · ` +
        `range ${rng >= 0 ? '+' : ''}${rng.toFixed(2)}%`;
    }
  }

  return (
    <footer className="h-[26px] flex items-center px-3 gap-4 text-[11px] text-[#6a6d78] border-t border-[#e0e3eb] bg-white shrink-0">
      <span>{clock}</span>
      <span>UTC</span>
      <span className="ml-auto">{rangeInfo || `${data.length} bars loaded · O/H/L/C`}</span>
    </footer>
  );
}
