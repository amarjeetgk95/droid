'use client';

// Single source of truth for lot sizes — mirrors backend/app/quant/margin.py
export const LOT_SIZES: Record<string, number> = {
  NIFTY: 75,
  BANKNIFTY: 30,
  FINNIFTY: 65,
  SENSEX: 10,
};

export function lotSizeFor(underlying: string): number {
  const u = (underlying || '').toUpperCase();
  if (u.includes('SENSEX')) return LOT_SIZES.SENSEX;
  if (u.includes('BANK')) return LOT_SIZES.BANKNIFTY;
  if (u.includes('FIN')) return LOT_SIZES.FINNIFTY;
  return LOT_SIZES.NIFTY;
}

// Local margin estimate mirroring backend quant/margin.py for instant preview.
// Backend /preview remains authoritative; this is for sub-second UI feedback.
// DEMO — local estimate only. Every consumer must label it DEMO and prefer
// the backend /preview value when available. Never present as a live margin.
export const PAPER_MARGIN_DEMO_LABEL = 'DEMO — local estimate only; backend /preview is authoritative';
// 1.5% ATM-premium heuristic used for option BUY estimates (DEMO, not a fill).
export const PAPER_MARGIN_PREMIUM_RATE_DEMO = 0.015;
// Per-lot short-margin bases mirroring backend quant/margin.py (DEMO, not a fill).
export const PAPER_MARGIN_BASE_LOTS_DEMO: Record<string, number> = {
  DEFAULT: 125000,
  SENSEX: 150000,
  BANK: 145000,
  FIN: 115000,
};
// Synthetic ATM-centred ladder used when the live option chain is
// unreachable (offline demo mode / backend down) so the strike
// dropdown still works with zero manual typing.
// DEMO — synthetic strikes only. Every consumer must label the ladder DEMO
// and replace it with the live chain as soon as it loads.
export const SYNTHETIC_STRIKES_DEMO_LABEL =
  'DEMO — synthetic ATM ladder (live chain unreachable)';

/** DEMO wrapper: synthetic strikes plus their provenance. Prefer the live chain. */
export function syntheticStrikesMeta(
  center: number,
  step: number,
  count = 11,
): { demo: true; strikes: number[]; source: 'DEMO'; note: string } {
  return {
    demo: true,
    strikes: syntheticStrikes(center, step, count),
    source: 'DEMO',
    note: SYNTHETIC_STRIKES_DEMO_LABEL,
  };
}

/** Explicitly DEMO strike ladder. Rename-safe front door for the synthetic path. */
export function syntheticStrikesDemo(
  center: number,
  step: number,
  count = 11,
): { demo: true; strikes: number[]; source: 'DEMO'; note: string } {
  return syntheticStrikesMeta(center, step, count);
}

/** Local margin estimates are always DEMO. Backend /preview is authoritative. */
export function isDemoMarginEstimate(): true {
  return true;
}

export const PAPER_MARGIN_ESTIMATE_SOURCE = 'local-approx' as const;

export type PaperMarginEstimate = {
  requiredMargin: number;
  premium: number;
  /** Always true — this is an approximation, never a live margin. */
  estimated: true;
  source: typeof PAPER_MARGIN_ESTIMATE_SOURCE;
  demo: true;
  note: string;
};

/** Provenance-tagged local estimate. Quantities stay identical to estimateMarginLocal. */
export function estimateMarginLocalMeta(args: {
  symbol: string;
  underlying: string;
  side: 'BUY' | 'SELL';
  price: number;
  quantity: number;
}): PaperMarginEstimate {
  return {
    ...estimateMarginLocal(args),
    estimated: true,
    source: PAPER_MARGIN_ESTIMATE_SOURCE,
    demo: true,
    note: PAPER_MARGIN_DEMO_LABEL,
  };
}

export function estimateMarginLocal(args: {
  symbol: string;
  underlying: string;
  side: 'BUY' | 'SELL';
  price: number;
  quantity: number;
}): { requiredMargin: number; premium: number } {
  const sym = (args.symbol || '').toUpperCase();
  const u = (args.underlying || '').toUpperCase();
  const price = Number.isFinite(args.price) ? args.price : 0;
  const quantity = Number.isFinite(args.quantity) ? Math.max(0, args.quantity) : 0;
  const isOpt = sym.includes('CE') || sym.includes('PE');
  if (isOpt && args.side === 'BUY') {
    // A price below the index floor means the strike/spot itself was passed in;
    // fall back to an ATM-premium estimate. Non-positive/NaN price => zero.
    // DEMO 1.5% heuristic — label DEMO in the UI, never a fill.
    const eff = price <= 0 ? 0 : price < 2000 ? price : Math.round(price * PAPER_MARGIN_PREMIUM_RATE_DEMO * 100) / 100;
    const premium = Math.round(eff * quantity * 100) / 100;
    return { requiredMargin: premium, premium };
  }
  const lot = lotSizeFor(u);
  const lots = Math.max(1, Math.floor(quantity / lot));
  // DEMO per-lot bases — label DEMO in the UI, never a fill.
  let base = PAPER_MARGIN_BASE_LOTS_DEMO.DEFAULT;
  if (u.includes('SENSEX')) base = PAPER_MARGIN_BASE_LOTS_DEMO.SENSEX;
  else if (u.includes('BANK')) base = PAPER_MARGIN_BASE_LOTS_DEMO.BANK;
  else if (u.includes('FIN')) base = PAPER_MARGIN_BASE_LOTS_DEMO.FIN;
  return { requiredMargin: base * lots, premium: 0 };
}

// Strike step per underlying — matches the ladder used across ticket + presets.
export function strikeStepFor(underlying: string): number {
  const u = (underlying || '').toUpperCase();
  if (u.includes('NIFTY') && !u.includes('BANK') && !u.includes('FIN')) return 50;
  return 100;
}

export function syntheticStrikes(center: number, step: number, count = 11): number[] {
  if (!Number.isFinite(center) || center <= 0 || !Number.isFinite(step) || step <= 0) return [];
  const n = Math.floor(count);
  if (!Number.isFinite(n) || n <= 0) return [];
  const c = Math.round(center / step) * step;
  // Exactly `count` strikes centred on ATM (odd counts put ATM dead-centre,
  // even counts bias toward the first strike at/above ATM).
  const first = Math.floor((n - 1) / 2);
  const out: number[] = [];
  for (let i = 0; i < n; i++) out.push(c + (i - first) * step);
  return out.filter((s) => s > 0);
}
export function buildOptionSymbol(underlying: string, strike: number, optionType: 'CE' | 'PE'): string {
  return `${underlying}${Math.round(strike)}${optionType}`;
}
