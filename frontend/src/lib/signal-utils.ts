/** Safe display helpers for the Signal Centre — never throw on null/undefined. */

export function safeNum(v: unknown, digits = 2): string {
  const n = typeof v === 'string' ? Number(v) : (v as number);
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return n.toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function safeInt(v: unknown): string {
  const n = typeof v === 'string' ? Number(v) : (v as number);
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return Math.round(n).toLocaleString('en-IN');
}

export function safeStr(v: unknown, fallback = '—'): string {
  if (v === null || v === undefined) return fallback;
  const s = String(v);
  return s.length ? s : fallback;
}

export function safePct(v: unknown, digits = 2): string {
  const n = typeof v === 'string' ? Number(v) : (v as number);
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return `${n.toFixed(digits)}%`;
}

export function safeState(v: unknown): string {
  const s = safeStr(v, 'UNKNOWN');
  return s.toUpperCase();
}

export function isTerminalState(state: unknown): boolean {
  const s = safeState(state);
  return ['TARGET_2_HIT', 'STOP_LOSS_HIT', 'TIME_STOP_HIT', 'RUNNER_TIME_STOP_HIT', 'EXPIRED', 'INVALIDATED', 'CLOSED'].includes(s);
}

export function isLiveState(state: unknown): boolean {
  const s = safeState(state);
  return ['CONFIRMED', 'TRIGGERED', 'ARMED', 'TARGET_1_HIT'].includes(s);
}

export function ttlLabel(signal: { fsm_state?: unknown; ttl_remaining_seconds?: unknown; time_stop_at_utc?: unknown; runner_time_stop_at_utc?: unknown; ttl_seconds?: unknown }, nowMs: number): string {
  const state = safeState(signal.fsm_state);
  if (state === 'TARGET_1_HIT' && typeof signal.runner_time_stop_at_utc === 'number') {
    const s = Math.max(0, Math.round((signal.runner_time_stop_at_utc - nowMs) / 1000));
    return `${s}s Runner TTL`;
  }
  if (state === 'CONFIRMED' && typeof signal.time_stop_at_utc === 'number') {
    const s = Math.max(0, Math.round((signal.time_stop_at_utc - nowMs) / 1000));
    return `${s}s Time-Stop`;
  }
  if (typeof signal.ttl_remaining_seconds === 'number' && Number.isFinite(signal.ttl_remaining_seconds)) {
    return `${Math.max(0, Math.round(signal.ttl_remaining_seconds))}s TTL`;
  }
  if (typeof signal.ttl_seconds === 'number') return `${signal.ttl_seconds}s TTL`;
  return 'TTL —';
}

export function withJitter(baseMs: number, ratio = 0.2): number {
  return baseMs * (1 - ratio + Math.random() * ratio * 2);
}
