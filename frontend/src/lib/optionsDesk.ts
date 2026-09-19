/* Pure helpers for the Options & Strategy cockpit — chain narrowing, badge
   tones, futures availability and payoff statistics. React-free so the logic
   is unit-testable; the backend stays the single source of truth. */

import type { InstitutionalStrikeFlow } from '@/lib/types';
import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';

export type InstrumentKey = 'NIFTY' | 'BANKNIFTY' | 'SENSEX';

/** Canonicalize display/context symbols (`NIFTY 50`, `NIFTY_BANK`, …) to desk keys. */
export function normalizeInstrumentKey(input: string | null | undefined): InstrumentKey {
  const v = (input ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (v.includes('BANKNIFTY') || v === 'NIFTYBANK') return 'BANKNIFTY';
  if (v.includes('SENSEX')) return 'SENSEX';
  return 'NIFTY';
}

export type RegimeStreamEntry = {
  regimeOverview: unknown;
  optionsAnalytics: unknown;
};

/**
 * Prefer the CommandView `regime` section for read panels: `by_symbol` carries
 * per-instrument `{ regime_overview, options_analytics }`, with the top-level
 * NIFTY legs as fallback. Key matching is case-insensitive and tolerates the
 * `NIFTY 50` display alias.
 */
export function pickRegimeStreamEntry(
  sectionValue: unknown,
  instrument: string,
): RegimeStreamEntry {
  const root = getObj(sectionValue);
  if (!root) return { regimeOverview: null, optionsAnalytics: null };
  const want = normalizeInstrumentKey(instrument);
  const bySymbol = getObj(root.by_symbol);
  if (bySymbol) {
    const key = Object.keys(bySymbol).find(
      (candidate) => normalizeInstrumentKey(candidate) === want,
    );
    if (key) {
      const entry = getObj(bySymbol[key]);
      if (entry) {
        return {
          regimeOverview: entry.regime_overview ?? null,
          optionsAnalytics: entry.options_analytics ?? null,
        };
      }
    }
  }
  return {
    regimeOverview: root.regime_overview ?? null,
    optionsAnalytics: root.options_analytics ?? null,
  };
}

/** Expiry list from a chain payload (defensive: any non-string entries dropped). */
export function chainExpiries(chain: unknown): string[] {
  const o = getObj(chain);
  if (!o || !Array.isArray(o.expiries)) return [];
  return o.expiries.filter((e): e is string => typeof e === 'string' && e.length > 0);
}

export type ChainStrikeRow = {
  strike: number;
  is_atm: boolean;
  raw: Record<string, unknown>;
};

/** Strike ladder sorted ascending; rows without a numeric strike are dropped. */
export function chainStrikeRows(chain: unknown): ChainStrikeRow[] {
  const o = getObj(chain);
  if (!o || !Array.isArray(o.strikes)) return [];
  const rows: ChainStrikeRow[] = [];
  for (const entry of o.strikes) {
    const row = getObj(entry);
    if (!row) continue;
    const strike = pickNum(row, 'strike');
    if (strike === null) continue;
    rows.push({ strike, is_atm: row.is_atm === true, raw: row });
  }
  return rows.sort((a, b) => a.strike - b.strike);
}

/** ATM strike: explicit analytics field first, else the flagged ladder row. */
export function atmStrikeOf(chain: unknown, rows: ChainStrikeRow[]): number | null {
  const analytics = getObj(getObj(chain)?.analytics);
  const fromAnalytics = analytics ? pickNum(analytics, 'atm_strike') : null;
  if (fromAnalytics !== null) return fromAnalytics;
  return rows.find((row) => row.is_atm)?.strike ?? null;
}

/**
 * ATM-centred window: the `radius` strikes each side of the ATM row (all rows
 * when `radius` is null or no ATM row is flagged).
 */
export function sliceAtmWindow(rows: ChainStrikeRow[], radius: number | null): ChainStrikeRow[] {
  if (radius === null) return rows;
  const atmIndex = rows.findIndex((row) => row.is_atm);
  if (atmIndex < 0) return rows;
  return rows.slice(Math.max(0, atmIndex - radius), atmIndex + radius + 1);
}

export type SgTone = 'bull' | 'bear' | 'neut' | 'warn' | 'info';

/**
 * PCR tone. Deliberately non-directional: extreme put/call concentration is a
 * caution flag, not a trade signal, so both tails map to `warn`.
 */
export function pcrTone(pcr: number | null): SgTone {
  if (pcr === null || !Number.isFinite(pcr)) return 'neut';
  if (pcr >= 1.5 || pcr <= 0.6) return 'warn';
  return 'neut';
}

export function pcrNote(pcr: number | null): string {
  if (pcr === null || !Number.isFinite(pcr)) return 'PCR unavailable';
  if (pcr >= 1.5) return 'put-heavy positioning';
  if (pcr <= 0.6) return 'call-heavy positioning';
  return 'balanced positioning';
}

/** Institutional sentiment → badge tone (STRONG_* folds into the base tone). */
export function sentimentTone(sentiment: string | null | undefined): SgTone {
  const s = String(sentiment ?? '').toUpperCase();
  if (!s || s === 'UNKNOWN' || s === 'UNAVAILABLE') return 'neut';
  if (s.includes('BULL')) return 'bull';
  if (s.includes('BEAR')) return 'bear';
  return 'neut';
}

/** Per-side OI buildup classification → tone. */
export function buildupTone(buildup: string | null | undefined): SgTone {
  const b = String(buildup ?? '').toUpperCase();
  if (b === 'LONG_BUILDUP' || b === 'SHORT_COVERING') return 'bull';
  if (b === 'SHORT_BUILDUP' || b === 'LONG_UNWINDING') return 'bear';
  return 'neut';
}

export function netFlowTone(flow: string | null | undefined): SgTone {
  const f = String(flow ?? '').toUpperCase();
  if (f === 'BULLISH') return 'bull';
  if (f === 'BEARISH') return 'bear';
  return 'neut';
}

/** Regime state → command-bar badge (volatility/compression states warn). */
export function regimeBadge(state: string | null | undefined): { label: string; cls: string } {
  const r = String(state ?? '').toUpperCase();
  if (!r || r === 'UNKNOWN') return { label: 'REGIME UNKNOWN', cls: 'b-neut' };
  if (r.includes('BULL')) return { label: r.replace(/_/g, ' '), cls: 'b-bull' };
  if (r.includes('BEAR')) return { label: r.replace(/_/g, ' '), cls: 'b-bear' };
  if (r.includes('VOLATILE') || r.includes('COMPRESSION') || r.includes('SQUEEZE')) {
    return { label: r.replace(/_/g, ' '), cls: 'b-warn' };
  }
  return { label: r.replace(/_/g, ' '), cls: 'b-neut' };
}

/** India VIX category → badge. */
export function vixBadge(category: string | null | undefined): { label: string; cls: string } {
  const c = String(category ?? '').toUpperCase();
  if (!c) return { label: 'VIX UNKNOWN', cls: 'b-neut' };
  if (c.includes('EXTREME')) return { label: c.replace(/_/g, ' '), cls: 'b-bear' };
  if (c.includes('ELEVATED')) return { label: c.replace(/_/g, ' '), cls: 'b-warn' };
  if (c.includes('LOW')) return { label: c.replace(/_/g, ' '), cls: 'b-info' };
  return { label: c.replace(/_/g, ' '), cls: 'b-neut' };
}

export type FuturesAvailability = { available: boolean; reason: string | null };

/**
 * Futures availability gate. The broker feed is unwired server-side, so an
 * overview with a null near-leg, no contracts and an UNAVAILABLE curve is
 * *expected* — callers render the honest empty state, never a synthetic basis.
 */
export function futuresAvailability(overview: unknown): FuturesAvailability {
  const o = getObj(overview);
  if (!o) return { available: false, reason: 'Futures overview unavailable.' };
  const nearPrice = pickNum(o, 'near_future_price');
  const term = getObj(o.term_structure);
  const contracts = term && Array.isArray(term.contracts) ? term.contracts : [];
  const curveState = term ? pickStr(term, 'curve_state') : null;
  if (nearPrice !== null || contracts.length > 0) return { available: true, reason: null };
  if (curveState !== null && curveState.toUpperCase() !== 'UNAVAILABLE') {
    return { available: true, reason: null };
  }
  return {
    available: false,
    reason: 'Broker futures feed offline — no contracts published (no synthetic basis shown).',
  };
}

export type PayoffCurvePoint = { spot: number; pnl: number };

export type PayoffStats = {
  points: number;
  maxProfit: number | null;
  maxLoss: number | null;
  /** Spots where the curve crosses zero (sign-change midpoints). */
  breakevens: number[];
};

/** Max/min/breakevens over a payoff curve (defensive: malformed points dropped). */
export function payoffStats(curve: unknown): PayoffStats {
  const empty: PayoffStats = { points: 0, maxProfit: null, maxLoss: null, breakevens: [] };
  if (!Array.isArray(curve)) return empty;
  const points: PayoffCurvePoint[] = [];
  for (const entry of curve) {
    const o = getObj(entry);
    if (!o) continue;
    const spot = pickNum(o, 'spot');
    const pnl = pickNum(o, 'pnl');
    if (spot === null || pnl === null) continue;
    points.push({ spot, pnl });
  }
  if (points.length === 0) return empty;
  let maxProfit = points[0].pnl;
  let maxLoss = points[0].pnl;
  const breakevens: number[] = [];
  for (let i = 0; i < points.length; i += 1) {
    if (points[i].pnl > maxProfit) maxProfit = points[i].pnl;
    if (points[i].pnl < maxLoss) maxLoss = points[i].pnl;
    if (i === 0) continue;
    const prev = points[i - 1].pnl;
    const curr = points[i].pnl;
    if ((prev < 0 && curr >= 0) || (prev > 0 && curr <= 0)) {
      breakevens.push(Math.round(((points[i - 1].spot + points[i].spot) / 2) * 100) / 100);
    }
  }
  return { points: points.length, maxProfit, maxLoss, breakevens };
}

/** Top strike flows by combined call+put volume (defensive parse + rank). */
export function topFlowsByVolume(flows: unknown, limit: number): InstitutionalStrikeFlow[] {
  if (!Array.isArray(flows)) return [];
  const rows: InstitutionalStrikeFlow[] = [];
  for (const entry of flows) {
    const o = getObj(entry);
    if (!o) continue;
    const strike = pickNum(o, 'strike');
    if (strike === null) continue;
    rows.push(entry as InstitutionalStrikeFlow);
  }
  return rows
    .sort((a, b) => {
      const volA = (a.call_volume ?? 0) + (a.put_volume ?? 0);
      const volB = (b.call_volume ?? 0) + (b.put_volume ?? 0);
      return volB - volA;
    })
    .slice(0, Math.max(0, limit));
}

/** First non-empty string in a record (rationale/assessment rendering). */
export function firstText(record: Record<string, unknown>, ...keys: string[]): string | null {
  return pickStr(record, ...keys);
}
