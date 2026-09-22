export type DashboardSymbol = 'NIFTY' | 'BANKNIFTY' | 'SENSEX' | 'BTCUSD';

/** Display token for unresolvable symbols. Never render a silent NIFTY fallback. */
export const UNKNOWN_SYMBOL = 'UNKNOWN' as const;
export type DisplaySymbol = DashboardSymbol | typeof UNKNOWN_SYMBOL;

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

/** Map a backend/display card symbol to the dashboard focus symbol. Order matters — full tokens first.
 *  Legacy compat: unknown cards fall back to NIFTY. New display code must use
 *  resolveCardSymbolStrict() and render UNKNOWN instead of a silent NIFTY. */
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

/** Strict card resolution: unknown cards resolve to UNKNOWN, never silent NIFTY. */
export function resolveCardSymbolStrict(cardSymbol: string | null | undefined): DisplaySymbol {
  const v = (cardSymbol || '').toUpperCase();
  if (!v.trim()) return UNKNOWN_SYMBOL;
  if (v.includes('BANKNIFTY') || v.includes('BANK NIFTY') || v.includes('NIFTY BANK') || v.includes('BANK_NIFTY')) {
    return 'BANKNIFTY';
  }
  if (v.includes('SENSEX')) return 'SENSEX';
  if (v.includes('BTC')) return 'BTCUSD';
  if (v.includes('NIFTY 50') || v.includes('NIFTY')) {
    // Bare NIFTY token only — BANK variants already returned above.
    if (v.includes('BANK') || v.includes('FIN')) return UNKNOWN_SYMBOL;
    return 'NIFTY';
  }
  return UNKNOWN_SYMBOL;
}

/** Strict dashboard normalization: unknown inputs resolve to UNKNOWN. */
export function normalizeDashboardSymbolStrict(input: string | null | undefined): DisplaySymbol {
  const v = (input || '').toUpperCase().trim();
  if (!v) return UNKNOWN_SYMBOL;
  const legacy = normalizeDashboardSymbol(input);
  // normalizeDashboardSymbol() defaults unknown → NIFTY for legacy compat.
  // Re-derive strictly: only return the legacy value when the input is a
  // recognised alias, otherwise UNKNOWN.
  if (v === 'BANKNIFTY' || v === 'NIFTY_BANK' || v === 'BANK_NIFTY' || v === 'BANK NIFTY' || v === 'NIFTY BANK') {
    return 'BANKNIFTY';
  }
  if (v === 'SENSEX' || v === 'BSE_SENSEX' || v === 'BSE SENSEX') return 'SENSEX';
  if (v === 'BTCUSD' || v === 'BTC' || v === 'BTCUSDT' || v === 'XBTUSD') return 'BTCUSD';
  if (v === 'NIFTY 50' || v === 'NIFTY50' || v === 'NIFTY') return 'NIFTY';
  if ((['NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD'] as string[]).includes(v)) return legacy;
  return UNKNOWN_SYMBOL;
}

/** Display helper: canonical symbol or UNKNOWN when the feed symbol is unmapped. */
export function displaySymbolOrUnknown(input: string | null | undefined): DisplaySymbol {
  const idx = resolveIndexSymbol(input);
  if (idx === 'NIFTY' || idx === 'BANKNIFTY' || idx === 'SENSEX') return idx;
  // INDIAVIX / FINNIFTY are valid index quotes but not dashboard focus symbols.
  if (idx !== null) return UNKNOWN_SYMBOL;
  return normalizeDashboardSymbolStrict(input);
}

/** Thrown by routing callers instead of silently defaulting to NIFTY. */
export class UnknownSymbolError extends Error {
  readonly input: string | null | undefined;
  constructor(input: string | null | undefined) {
    super(`Unknown dashboard symbol: ${input === null || input === undefined || String(input).trim() === '' ? '<blank>' : String(input)}`);
    this.name = 'UnknownSymbolError';
    this.input = input;
  }
}

/** Routing-safe normalization: unknown symbols throw, never become NIFTY. */
export function normalizeDashboardSymbolOrThrow(input: string | null | undefined): DashboardSymbol {
  const resolved = normalizeDashboardSymbolStrict(input);
  if (resolved === UNKNOWN_SYMBOL) throw new UnknownSymbolError(input);
  return resolved;
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

export type IndexQuoteSymbol = 'NIFTY' | 'BANKNIFTY' | 'FINNIFTY' | 'SENSEX' | 'INDIAVIX';

/**
 * Index matchers, most specific first. Never reorder: "NIFTY BANK" contains
 * NIFTY, and "INDIA VIX" must not fall through to the NIFTY bucket.
 */
const INDEX_MATCHERS: ReadonlyArray<readonly [IndexQuoteSymbol, RegExp]> = [
  ['BANKNIFTY', /BANKNIFTY|NIFTY\s?BANK/],
  ['FINNIFTY', /FINNIFTY|NIFTY\s?FIN|FIN\s?SERVICE/],
  ['SENSEX', /SENSEX/],
  ['INDIAVIX', /VIX/],
  ['NIFTY', /NIFTY\s?50|NIFTY/],
];

/**
 * Match a feed symbol (REST card, WS tick, broker token) to a canonical index.
 *
 * Returns `null` for anything that is not an index quote. Callers must handle
 * null explicitly — defaulting unknown symbols to NIFTY is how an INDIA VIX
 * tick used to overwrite the NIFTY readout.
 */
export function resolveIndexSymbol(input: string | null | undefined): IndexQuoteSymbol | null {
  const v = (input || '')
    .toUpperCase()
    .replace(/^(NSE|BSE):/, '')
    .replace(/(-INDEX|_INDEX)$/, '')
    .trim();
  for (const [symbol, pattern] of INDEX_MATCHERS) {
    if (pattern.test(v)) return symbol;
  }
  return null;
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
    if (instrument === 'INDIAVIX' || instrument === 'VIX' || instrument === 'INDIA VIX') {
      return sym.includes('VIX');
    }
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
