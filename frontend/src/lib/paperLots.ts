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
    const eff = price <= 0 ? 0 : price < 2000 ? price : Math.round(price * 0.015 * 100) / 100;
    const premium = Math.round(eff * quantity * 100) / 100;
    return { requiredMargin: premium, premium };
  }
  const lot = lotSizeFor(u);
  const lots = Math.max(1, Math.floor(quantity / lot));
  let base = 125000;
  if (u.includes('SENSEX')) base = 150000;
  else if (u.includes('BANK')) base = 145000;
  else if (u.includes('FIN')) base = 115000;
  return { requiredMargin: base * lots, premium: 0 };
}

// Strike step per underlying — matches the ladder used across ticket + presets.
export function strikeStepFor(underlying: string): number {
  const u = (underlying || '').toUpperCase();
  if (u.includes('NIFTY') && !u.includes('BANK') && !u.includes('FIN')) return 50;
  return 100;
}

// Synthetic ATM-centred ladder used when the live option chain is
// unreachable (offline demo mode / backend down) so the strike
// dropdown still works with zero manual typing.
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
