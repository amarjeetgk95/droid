/* Defensive parsing + formatting shared by the signals desk.
   Backend payloads vary across deploy versions; every field is coerced
   to a safe shape so the UI never crashes on partial data. */

export function asStr(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s ? s : null;
}

export function asNum(v: unknown): number | null {
  const n = typeof v === 'string' && v.trim() !== '' ? Number(v) : (v as number);
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

export function getObj(v: unknown): Record<string, unknown> | null {
  if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>;
  return null;
}

export function pickStr(o: Record<string, unknown>, ...keys: string[]): string | null {
  for (const k of keys) {
    const s = asStr(o[k]);
    if (s) return s;
  }
  return null;
}

export function pickNum(o: Record<string, unknown>, ...keys: string[]): number | null {
  for (const k of keys) {
    const n = asNum(o[k]);
    if (n !== null) return n;
  }
  return null;
}

export function pickMs(o: Record<string, unknown>, ...keys: string[]): number | null {
  for (const k of keys) {
    const v = o[k];
    if (v === null || v === undefined || v === '') continue;
    if (typeof v === 'number' && Number.isFinite(v)) {
      // Heuristic: seconds-epoch vs ms-epoch.
      return v < 1e12 ? Math.round(v * 1000) : Math.round(v);
    }
    const d = new Date(String(v));
    const t = d.getTime();
    if (!Number.isNaN(t)) return t;
  }
  return null;
}

/* ---------------- formatting ---------------- */

export function fmtTimeMs(ms: number | null): string {
  if (ms === null) return '—';
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

export type TtlTone = 'ok' | 'warn' | 'expired';

/** TTL countdown with a warning band under 2 minutes. */
export function fmtTtl(expiresMs: number | null, now: number): { label: string; tone: TtlTone } {
  if (expiresMs === null) return { label: '—', tone: 'ok' };
  const s = Math.round((expiresMs - now) / 1000);
  if (s <= 0) return { label: 'expired', tone: 'expired' };
  if (s < 60) return { label: `${s}s`, tone: s < 45 ? 'warn' : 'ok' };
  const m = Math.floor(s / 60);
  if (m < 60) return { label: `${m}m ${s % 60}s`, tone: m < 2 ? 'warn' : 'ok' };
  return { label: `${Math.floor(m / 60)}h ${m % 60}m`, tone: 'ok' };
}

/** Distance of the trigger from the current spot. */
export function fmtDist(trigger: number | null, spot: number | null): string {
  if (trigger === null || spot === null || spot === 0) return '—';
  const diff = trigger - spot;
  const pct = (diff / Math.abs(spot)) * 100;
  const sign = diff > 0 ? '+' : '';
  return `${sign}${diff.toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
}

/** Confidence arrives as 0..1 or 0..100 depending on source — normalise to text. */
export function fmtConf(conf: number | null): string {
  if (conf === null) return '—';
  return conf > 1 ? `${conf.toFixed(1)}%` : `${Math.round(conf * 100)}%`;
}

/** 0..100 usable width for confidence meters. */
export function confPct(conf: number | null): number {
  if (conf === null) return 0;
  const pct = conf > 1 ? conf : conf * 100;
  return Math.max(0, Math.min(100, pct));
}

export function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}

/** SCALP_BREAKOUT -> "scalp breakout" style labels. */
export function prettyKey(s: string): string {
  return s.replace(/_/g, ' ').toLowerCase();
}

export function isHiddenTab(): boolean {
  return typeof document !== 'undefined' && document.hidden;
}

/* ---------------- row normalization ---------------- */

export type ActiveRow = {
  raw: Record<string, unknown>;
  id: string;
  timeMs: number | null;
  symbol: string;
  strategy: string;
  direction: unknown;
  state: string;
  confidence: number | null;
  trigger: number | null;
  sl: number | null;
  t1: number | null;
  t2: number | null;
  spot: number | null;
  expiresMs: number | null;
  desk: string | null;
  isScalp: boolean | null;
};

export function toActiveRow(s: unknown): ActiveRow | null {
  const o = getObj(s);
  if (!o) return null;
  const id = pickStr(o, 'signal_id', 'id');
  if (!id) return null;
  const isScalpRaw = o.is_scalp;
  return {
    raw: o,
    id,
    timeMs: pickMs(o, 'created_at_ms', 'created_at', 'timestamp_ms', 'timestamp', 'created_at_iso'),
    symbol: pickStr(o, 'underlying', 'instrument', 'symbol') ?? '—',
    strategy: pickStr(o, 'strategy') ?? '—',
    direction: o.direction ?? o.bias ?? 'NEUTRAL',
    state: pickStr(o, 'status', 'state', 'fsm_state') ?? '—',
    confidence: pickNum(o, 'confidence', 'score'),
    trigger: pickNum(o, 'trigger_price', 'entry_price', 'trigger', 'entry'),
    sl: pickNum(o, 'stop_loss', 'sl', 'stop'),
    t1: pickNum(o, 'target_1', 'target1', 't1'),
    t2: pickNum(o, 'target_2', 'target2', 't2'),
    spot: pickNum(o, 'spot_price', 'current_price', 'ltp', 'spot', 'underlying_price'),
    expiresMs: pickMs(o, 'expires_at_ms', 'expires_at', 'ttl_ms', 'expiry_ms'),
    desk: pickStr(o, 'desk'),
    isScalp: typeof isScalpRaw === 'boolean' ? isScalpRaw : null,
  };
}

export type AuditRow = {
  id: string;
  underlying: string;
  strategy: string;
  direction: unknown;
  status: string;
  confidence: number | null;
  pnl: number | null;
  timeMs: number | null;
};

export function toAuditRow(t: unknown): AuditRow | null {
  const o = getObj(t);
  if (!o) return null;
  const id = pickStr(o, 'signal_id', 'id');
  if (!id) return null;
  return {
    id,
    underlying: pickStr(o, 'underlying', 'instrument', 'symbol') ?? '—',
    strategy: pickStr(o, 'strategy') ?? '—',
    direction: o.direction ?? 'NEUTRAL',
    status: pickStr(o, 'status', 'state', 'fsm_state') ?? '—',
    confidence: pickNum(o, 'confidence', 'score'),
    pnl: pickNum(o, 'pnl', 'net_pnl', 'realized_pnl', 'pnl_points', 'profit_loss'),
    timeMs: pickMs(o, 'closed_at_ms', 'closed_at', 'created_at_ms', 'created_at', 'timestamp_ms', 'timestamp'),
  };
}

/* ---------------- semantic state tones ---------------- */

export type Tone = 'bull' | 'bear' | 'info' | 'warn' | 'neut';

/** Map a signal/status state to a badge tone. */
export function stateTone(state: string): Tone {
  const s = state.toUpperCase();
  if (/(CONFIRM|ACTIVE|FILLED|EXECUTED|WON|WIN)/.test(s)) return 'bull';
  if (/(ARMED|READY|TRIGGERED)/.test(s)) return 'info';
  if (/(EXPIRED|STALE)/.test(s)) return 'warn';
  if (/(CANCEL|REJECT|KILL|FAIL|LOSS|LOST)/.test(s)) return 'bear';
  return 'neut';
}



