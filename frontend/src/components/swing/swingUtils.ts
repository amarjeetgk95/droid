/**
 * Pure helpers for the swing desk.
 *
 * P&L sign/colour must be derived from the value itself — never from a
 * `>= 0` boolean, which paints a flat return green and can disagree with a
 * separately-signed R multiple. Keeping these pure makes the rule testable.
 */

import { toNumber } from '@/lib/coerce';
import { fmtINR, fmtNum } from '@/components/ui/desk';

export const EXIT_REASONS = [
  { value: 'MANUAL_EXIT', label: 'Manual Exit' },
  { value: 'TARGET_1', label: 'Target 1 Hit (+1.5R)' },
  { value: 'TARGET_2', label: 'Target 2 Hit (+3.0R)' },
  { value: 'OPTION_STOP', label: 'Option Premium Stop Hit' },
  { value: 'UNDERLYING_STOP', label: 'Underlying Thesis Invalidation' },
  { value: 'THETA_DECAY', label: 'Excessive Theta Drag' },
  { value: 'EXPIRY_RISK', label: 'Expiry Proximity Risk (DTE <= 3)' },
  { value: 'TRAILING_STOP', label: 'Trailing Stop Breached' },
  { value: 'TIME_STOP', label: 'Mandatory 15:15 IST Time Stop' },
] as const;

function toFinite(v: unknown): number | null {
  return toNumber(v, { rejectEmptyString: true });
}

/** `+₹1,250.5` / `-₹1,250.5` / `₹0` / `—` for non-finite input. */
export function signedINR(v: unknown): string {
  const n = toFinite(v);
  if (n === null) return '—';
  if (n > 0) return `+${fmtINR(n)}`;
  if (n < 0) return `-${fmtINR(Math.abs(n))}`;
  return fmtINR(0);
}

/** `+1.2%` / `-0.4%` / `0.0%` / `—` for non-finite input. */
export function signedPct(v: unknown, digits = 1): string {
  const n = toFinite(v);
  if (n === null) return '—';
  return `${n > 0 ? '+' : ''}${fmtNum(n, digits)}%`;
}

/** `+1.5R` / `-0.8R` / `0.0R` / `—` for non-finite input. */
export function signedR(v: unknown, digits = 1): string {
  const n = toFinite(v);
  if (n === null) return '—';
  return `${n > 0 ? '+' : ''}${fmtNum(n, digits)}R`;
}

export type PnlTone = 'up' | 'down' | 'flat';

/** Zero and non-finite values are neutral — never green. */
export function pnlTone(v: unknown): PnlTone {
  const n = toFinite(v);
  if (n === null || n === 0) return 'flat';
  return n > 0 ? 'up' : 'down';
}

export function pnlToneClass(v: unknown): string {
  switch (pnlTone(v)) {
    case 'up':
      return 'text-up';
    case 'down':
      return 'text-down';
    default:
      return 'text-muted-foreground';
  }
}

/** Human label for a structured exit reason; unknown enums pass through raw. */
export function exitReasonLabel(reason?: string | null): string {
  if (!reason) return '—';
  return EXIT_REASONS.find((r) => r.value === reason)?.label ?? reason;
}
