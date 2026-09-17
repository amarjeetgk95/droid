import type { KeyLevelsModel, MarketRegimeOverview, TechnicalIndicators, VixRegimeInfo } from '@/lib/types';
import { DEFAULT_STALE_AFTER_MS } from '@/lib/feedState';

export function finiteNum(v: unknown): number | null {
  const n = typeof v === 'string' ? Number(v) : v;
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

export function posNum(v: unknown): number | null {
  const n = finiteNum(v);
  return n !== null && n > 0 ? n : null;
}

export function normalizeSymbol(v: unknown): string | null {
  if (typeof v !== 'string' || v.trim() === '') return null;
  return v
    .trim()
    .toUpperCase()
    .replace(/^(NSE|BSE):/, '')
    .replace(/\s*50$/, '')
    .replace(/\s+/g, '');
}

export function symbolsMatch(a: unknown, b: unknown): boolean {
  const na = normalizeSymbol(a);
  const nb = normalizeSymbol(b);
  return na !== null && nb !== null && na === nb;
}

export function confidencePct(v: unknown): number | null {
  const n = finiteNum(v);
  if (n === null || n <= 0 || n > 100) return null;
  return Math.round(n);
}

export function hasIndicatorData(ind: TechnicalIndicators | null | undefined): boolean {
  if (!ind) return false;
  return (
    posNum(ind.adx_14) !== null ||
    posNum(ind.atr_14) !== null ||
    posNum(ind.supertrend_value) !== null ||
    posNum(ind.bollinger_upper) !== null ||
    posNum(ind.bollinger_middle) !== null ||
    posNum(ind.bollinger_lower) !== null ||
    posNum(ind.bollinger_bandwidth) !== null ||
    posNum(ind.ema_20) !== null ||
    posNum(ind.ema_50) !== null ||
    posNum(ind.sma_200) !== null
  );
}

export function hasVixData(vix: VixRegimeInfo | null | undefined): boolean {
  return posNum(vix?.vix_value) !== null;
}

export function hasKeyLevelData(levels: KeyLevelsModel | null | undefined): boolean {
  if (!levels) return false;
  const pivots = [
    levels.classic_pivots,
    levels.fibonacci_pivots,
    levels.camarilla_pivots,
  ].flatMap((set) =>
    set ? [set.pivot, set.r1, set.r2, set.r3, set.r4, set.s1, set.s2, set.s3, set.s4] : [],
  );
  return (
    pivots.some((v) => posNum(v) !== null) ||
    posNum(levels.prior_day_high) !== null ||
    posNum(levels.prior_day_low) !== null ||
    posNum(levels.prior_day_close) !== null ||
    posNum(levels.day_open) !== null ||
    posNum(levels.poc) !== null ||
    posNum(levels.vah) !== null ||
    posNum(levels.val) !== null ||
    posNum(levels.nearest_resistance) !== null ||
    posNum(levels.nearest_support) !== null
  );
}

export function isUsableRegimeOverview(
  overview: MarketRegimeOverview | null | undefined,
  expectedSymbol?: string,
): boolean {
  if (!overview) return false;
  if (expectedSymbol && !symbolsMatch(overview.symbol, expectedSymbol)) return false;
  if (posNum(overview.spot_price) === null) return false;
  const state = typeof overview.regime_state === 'string' ? overview.regime_state.toUpperCase() : '';
  if (state === '' || state === 'UNKNOWN') return false;
  return typeof overview.summary_headline === 'string' && overview.summary_headline.trim() !== '';
}

export function provenanceLabel(provider: unknown, timestamp: unknown): string | null {
  const parts: string[] = [];
  if (typeof provider === 'string' && provider.trim() !== '') parts.push(provider.trim());
  if (typeof timestamp === 'string' && timestamp.trim() !== '') {
    const at = new Date(timestamp);
    if (!Number.isNaN(at.getTime())) {
      parts.push(
        `snapshot ${at.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`,
      );
    }
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}

export function isStale(
  lastUpdated: Date | null | undefined,
  now: number,
  staleAfterMs: number = DEFAULT_STALE_AFTER_MS,
): boolean {
  if (!lastUpdated) return false;
  const t = lastUpdated.getTime();
  return Number.isFinite(t) && now - t > staleAfterMs;
}
