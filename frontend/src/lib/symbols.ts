export type DashboardSymbol = 'NIFTY' | 'BANKNIFTY' | 'SENSEX' | 'BTCUSD';

const KNOWN: DashboardSymbol[] = ['NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD'];

export function normalizeDashboardSymbol(input: string | null | undefined): DashboardSymbol {
  const v = (input || '').toUpperCase().trim();
  if (v === 'BANKNIFTY' || v === 'NIFTY_BANK' || v === 'BANK_NIFTY') return 'BANKNIFTY';
  if (v === 'SENSEX' || v === 'BSE_SENSEX') return 'SENSEX';
  if (v === 'BTCUSD' || v === 'BTC' || v === 'BTCUSDT' || v === 'XBTUSD') return 'BTCUSD';
  if ((KNOWN as string[]).includes(v)) return v as DashboardSymbol;
  return 'NIFTY';
}

/** Map a backend/display card symbol to the dashboard focus symbol. Order matters — full tokens first. */
export function resolveCardSymbol(cardSymbol: string): DashboardSymbol {
  const v = (cardSymbol || '').toUpperCase();
  if (v.includes('BANKNIFTY')) return 'BANKNIFTY';
  if (v.includes('SENSEX')) return 'SENSEX';
  if (v.includes('BTC')) return 'BTCUSD';
  if (v.includes('NIFTY 50') || v.includes('NIFTY')) return 'NIFTY';
  return 'NIFTY';
}
