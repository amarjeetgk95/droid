// Pure helper functions used by the chart. Framework-agnostic, no React deps.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function genData(intervalMin, n = 700, basePrice) {
  const step = intervalMin * 60 * 1000;
  const now = Math.floor(Date.now() / step) * step;
  let price = basePrice ?? 62000 + Math.random() * 4000;
  const out = [];
  const vol = 0.0022 * Math.sqrt(intervalMin);
  for (let i = n - 1; i >= 0; i--) {
    const t = now - i * step;
    const drift = Math.sin(i / 40) * 0.0006 + (Math.random() - 0.5) * vol * 2;
    const o = price;
    const c = Math.max(100, o * (1 + drift));
    const wick = Math.abs(o - c) + o * vol * Math.random() * 1.4;
    const h = Math.max(o, c) + wick * Math.random();
    const l = Math.min(o, c) - wick * Math.random();
    const v = Math.abs(c - o) / o * 90000 + Math.random() * 900 + 200;
    out.push({ t, o, h, l, c, v });
    price = c;
  }
  return out;
}

export const fmtP = (p) =>
  p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Price formatting with precision that adapts to the visible range
export const fmtPrice = (p, min, max) => {
  const range = Math.abs(max - min);
  const dec = range >= 100 ? 2 : range >= 1 ? 4 : 6;
  return p.toLocaleString('en-US', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  });
};

export function fmtT(ts, tf) {
  const d = new Date(ts);
  const p = (n) => String(n).padStart(2, '0');
  if (tf >= 1440) return d.getUTCDate() + ' ' + MONTHS[d.getUTCMonth()];
  return p(d.getUTCHours()) + ':' + p(d.getUTCMinutes());
}

export function fmtDay(ts) {
  const d = new Date(ts);
  return d.getUTCDate() + ' ' + MONTHS[d.getUTCMonth()];
}

export function fmtFull(ts) {
  const d = new Date(ts);
  const p = (n) => String(n).padStart(2, '0');
  return (
    d.getUTCFullYear() +
    '-' +
    p(d.getUTCMonth() + 1) +
    '-' +
    p(d.getUTCDate()) +
    ' ' +
    p(d.getUTCHours()) +
    ':' +
    p(d.getUTCMinutes())
  );
}

export function niceSteps(min, max, count) {
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
  const out = [];
  let v = Math.ceil(min / step) * step;
  while (v < max) {
    out.push(v);
    v += step;
  }
  return out;
}

// Keep the visible window inside sensible bounds (a little margin left/right)
export const clampStart = (len, count, s) =>
  Math.max(-count * 0.15, Math.min(len - count * 0.7, s));
