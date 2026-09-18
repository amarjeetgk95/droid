/**
 * Build-time feature flags.
 *
 * `NEXT_PUBLIC_MINIMAL_UI=1` switches the shell to the consolidated
 * Command / Positions / Lab navigation and the three-column Command desk.
 * Default off until P3 parity (docs/FRONTEND_OVERHAUL_PLAN.md, P2-6): legacy
 * desks stay reachable and unchanged while the flag is off.
 */
export function isMinimalUi(): boolean {
  return process.env.NEXT_PUBLIC_MINIMAL_UI === '1';
}
