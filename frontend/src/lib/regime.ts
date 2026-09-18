import type { MarketRegimeOverview } from '@/lib/types';
import { isNiftySymbol } from '@/lib/symbols';

/**
 * The dashboard summary's `regime_overview` leg is always the NIFTY diagnosis
 * (backend `classify_market_regime("NIFTY")`). Consumers that would fetch
 * `/regime/{symbol}/overview` for a NIFTY-equivalent symbol on the same route
 * reuse the shared summary leg instead — one owner per route.
 *
 * Fail-closed: a missing/unknown symbol echo, or a non-NIFTY request, returns
 * `null` so the caller keeps its own direct fetch.
 */
export function regimeFromSummary(
  summaryRegime: MarketRegimeOverview | null | undefined,
  requestedSymbol: string,
): MarketRegimeOverview | null {
  if (!summaryRegime) return null;
  if (!isNiftySymbol(requestedSymbol)) return null;
  if (!isNiftySymbol(summaryRegime.symbol)) return null;
  return summaryRegime;
}
