export type DashboardSymbol = 'NIFTY' | 'BANKNIFTY' | 'SENSEX' | 'BTCUSD';

const KNOWN: DashboardSymbol[] = ['NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD'];

export function normalizeDashboardSymbol(input: string | null | undefined): DashboardSymbol {
  const v = (input || '').toUpperCase().trim();
  if (v === 'BANKNIFTY' || v === 'NIFTY_BANK' || v === 'BANK_NIFTY' || v === 'BANK NIFTY' || v === 'NIFTY BANK') {
    return 'BANKNIFTY';
  }
  if (v === 'SENSEX' || v === 'BSE_SENSEX' || v === 'BSE SENSEX') return 'SENSEX';
  if (v === 'BTCUSD' || v === 'BTC' || v === 'BTCUSDT' || v === 'XBTUSD') return 'BTCUSD';
  if (v === 'NIFTY 50' || v === 'NIFTY50') return 'NIFTY';
  if ((KNOWN as string[]).includes(v)) return v as DashboardSymbol;
  return 'NIFTY';
}

/** Map a backend/display card symbol to the dashboard focus symbol. Order matters — full tokens first. */
export function resolveCardSymbol(cardSymbol: string): DashboardSymbol {
  const v = (cardSymbol || '').toUpperCase();
  if (v.includes('BANKNIFTY') || v.includes('BANK NIFTY') || v.includes('NIFTY BANK') || v.includes('BANK_NIFTY')) {
    return 'BANKNIFTY';
  }
  if (v.includes('SENSEX')) return 'SENSEX';
  if (v.includes('BTC')) return 'BTCUSD';
  if (v.includes('NIFTY 50') || v.includes('NIFTY')) return 'NIFTY';
  return 'NIFTY';
}

/**
 * Crypto instruments ride an always-open venue: the shared dashboard regime
 * classification (and closed-session status derivation) must never apply.
 */
export function isCryptoCard(c: {
  symbol?: string | null;
  provider?: string | null;
}): boolean {
  const sym = (c.symbol || '').toUpperCase();
  const prov = (c.provider || '').toLowerCase();
  return prov.includes('binance') || sym.endsWith('USDT') || sym.endsWith('BTC');
}

/**
 * Card lookup for the shared InstrumentContext value. `instrument` may be
 * either the dashboard token ("NIFTY") or the display token ("NIFTY 50").
 */
export function findInstrumentCard<T extends { symbol?: string | null }>(
  cards: readonly T[],
  instrument: string,
): T | undefined {
  return cards.find((c) => {
    const sym = (c.symbol ?? '').replace(/^(NSE|BSE):/i, '').trim().toUpperCase();
    if (instrument === 'BANKNIFTY') return sym.includes('BANKNIFTY');
    if (instrument === 'SENSEX') return sym.includes('SENSEX');
    return (sym === 'NIFTY 50' || sym === 'NIFTY') && !sym.includes('BANKNIFTY');
  });
}

/** True when a symbol canonicalizes to the NIFTY regime family. */
export function isNiftySymbol(input: string | null | undefined): boolean {
  const v = (input || '')
    .toUpperCase()
    .replace(/^(NSE|BSE):/, '')
    .replace(/(-INDEX|_INDEX)$/, '')
    .trim()
    .replace(/\s*50$/, '')
    .replace(/\s+/g, '');
  return v === 'NIFTY';
}
