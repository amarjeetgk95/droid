/* Pure helpers for the swing options desk — filtering, tones and entry
   eligibility. Kept free of React so the desk logic is unit-testable and the
   backend stays the single source of truth for server-side revalidation. */

import type { SwingSetupDTO } from '@/lib/api/swing';
import type { Tone } from '@/lib/signalsNormalize';

export type SwingHorizonFilter = 'ALL' | 'POSITIONAL' | 'INTRADAY';
export type SwingDirectionFilter = 'ALL' | 'BULLISH' | 'BEARISH';

export type SwingSetupFilters = {
  underlying: string;
  horizon: SwingHorizonFilter;
  direction: SwingDirectionFilter;
  state: string;
  minScore: number | null;
};

export const DEFAULT_SWING_FILTERS: SwingSetupFilters = {
  underlying: 'ALL',
  horizon: 'ALL',
  direction: 'ALL',
  state: 'ALL',
  minScore: null,
};

/**
 * Direction from the swing setup domain (LONG_CALL / LONG_PUT).
 *
 * Deliberately not `ui/desk.normalizeDirection`: that helper tests `LONG`
 * before `PUT`, so LONG_PUT would misrender as bullish.
 */
export function swingSetupDirection(setup: {
  direction?: unknown;
  option_type?: unknown;
}): 'BULLISH' | 'BEARISH' | 'NEUTRAL' {
  const d = String(setup.direction ?? '').toUpperCase();
  const t = String(setup.option_type ?? '').toUpperCase();
  if (t === 'PE' || d.includes('PUT') || d.includes('BEARISH') || d.includes('SHORT')) {
    return 'BEARISH';
  }
  if (t === 'CE' || d.includes('CALL') || d.includes('BULLISH') || d.includes('LONG')) {
    return 'BULLISH';
  }
  return 'NEUTRAL';
}

/** Lifecycle tone for `signal_state` badges. */
export function swingStateTone(state: string | null | undefined): Tone {
  const s = String(state ?? '').toUpperCase();
  if (/(ENTERED|PARTIAL_EXIT|TRAILING)/.test(s)) return 'bull';
  if (/(READY|TRIGGERED)/.test(s)) return 'info';
  if (/(THETA_WARNING|EXPIRY_WARNING)/.test(s)) return 'warn';
  if (/(INVALIDATED|EXPIRED|BLOCKED|ABSTAINED)/.test(s)) return 'bear';
  return 'neut';
}

export type SwingEntryEligibility = { eligible: boolean; reason: string | null };

/**
 * Client-side preview of the backend's §50 revalidation. The server still owns
 * the decision — this only disables obviously-blocked rows and states why.
 */
export function swingEntryEligibility(setup: SwingSetupDTO): SwingEntryEligibility {
  const state = String(setup.signal_state ?? '').toUpperCase();
  if (state === 'EXPIRED' || state === 'INVALIDATED') {
    return { eligible: false, reason: `Setup ${state.toLowerCase()} — no longer actionable.` };
  }
  if (state === 'ENTERED' || state === 'PARTIAL_EXIT' || state === 'TRAILING') {
    return { eligible: false, reason: 'Setup already has an open position.' };
  }
  if (!setup.trade_validity?.overall_valid) {
    const reasons = setup.trade_validity?.rejection_reasons ?? [];
    return {
      eligible: false,
      reason: reasons.length > 0 ? `Validity failed: ${reasons.join(', ')}` : 'Trade validity failed.',
    };
  }
  return { eligible: true, reason: null };
}

/** Filter + rank setups by score (descending). Stable for equal scores. */
export function filterSwingSetups(
  setups: SwingSetupDTO[],
  filters: SwingSetupFilters,
): SwingSetupDTO[] {
  const underlying = filters.underlying.toUpperCase();
  const state = filters.state.toUpperCase();
  return setups
    .filter((setup) => {
      if (underlying !== 'ALL' && String(setup.underlying ?? '').toUpperCase() !== underlying) {
        return false;
      }
      const horizon = String(setup.horizon ?? 'POSITIONAL').toUpperCase();
      if (filters.horizon !== 'ALL' && horizon !== filters.horizon) return false;
      if (filters.direction !== 'ALL' && swingSetupDirection(setup) !== filters.direction) {
        return false;
      }
      if (state !== 'ALL' && String(setup.signal_state ?? '').toUpperCase() !== state) return false;
      if (filters.minScore !== null && (setup.score?.total ?? 0) < filters.minScore) return false;
      return true;
    })
    .sort((a, b) => (b.score?.total ?? 0) - (a.score?.total ?? 0));
}

/** Distinct lifecycle states present in a setup list, for filter options. */
export function swingSetupStates(setups: SwingSetupDTO[]): string[] {
  const states = new Set<string>();
  for (const setup of setups) {
    const state = String(setup.signal_state ?? '').toUpperCase();
    if (state) states.add(state);
  }
  return [...states].sort();
}
