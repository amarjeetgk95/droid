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

/** Expiry label from an audit row: explicit field, else FYERS option symbol. */
export function ledgerExpiry(o: Record<string, unknown>): string {
  const direct = pickStr(o, 'expiry');
  if (direct) {
    const f = fmtExpiry(direct);
    if (f !== '—') return f;
  }
  const contract = getObj(o.option_contract);
  if (contract) {
    const f = fmtExpiry(contract.expiry_date ?? contract.expiry);
    if (f !== '—') return f;
  }
  // FYERS weekly {YY}{M}{dd} / monthly {YY}{MMM} after the underlying.
  const sym = pickStr(o, 'option_symbol', 'broker_symbol', 'symbol') ?? '';
  const m = sym.toUpperCase().match(/^(?:NSE|BSE):(?:BANKNIFTY|NIFTY|SENSEX)(\d{2})(.+?)(CE|PE)$/);
  if (m) {
    const tail = m[2];
    const mon3 = tail.slice(0, 3);
    if (/^[A-Z]{3}$/.test(mon3)) return mon3; // monthly: no day component
    const code = tail[0];
    const dd = tail.slice(1, 3);
    const rev: Record<string, string> = { '1': 'JAN', '2': 'FEB', '3': 'MAR', '4': 'APR', '5': 'MAY', '6': 'JUN', '7': 'JUL', '8': 'AUG', '9': 'SEP', O: 'OCT', N: 'NOV', D: 'DEC' };
    if (rev[code] && /^\d{2}$/.test(dd)) return `${dd} ${rev[code]}`;
  }
  return '—';
}
export function fmtExpiry(v: unknown): string {
  if (v === null || v === undefined) return '—';
  const s = String(v).trim();
  if (!s) return '—';
  const d = new Date(s);
  if (!Number.isNaN(d.getTime()) && /\d{4}/.test(s)) {
    return d.toLocaleString('en-IN', { day: '2-digit', month: 'short' }).toUpperCase().replace(',', '');
  }
  const m = s.match(/(\d{1,2})\s*[-/]?\s*([A-Za-z]{3,9})\b/i);
  if (m) return `${m[1].padStart(2, '0')} ${m[2].slice(0, 3).toUpperCase()}`;
  return '—';
}

/** Full desk timestamp: 11 Sep 14:32:05. */
export function fmtDateTimeMs(ms: number | null): string {
  if (ms === null) return '—';
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}

export type TtlTone = 'ok' | 'warn' | 'expired';

/** TTL countdown with a warning band under 2 minutes. */
export function fmtTtl(expiresMs: number | null, now: number): { label: string; tone: TtlTone } {
  if (expiresMs === null) return { label: 'â€”', tone: 'ok' };
  const s = Math.round((expiresMs - now) / 1000);
  if (s <= 0) return { label: 'expired', tone: 'expired' };
  if (s < 60) return { label: `${s}s`, tone: s < 45 ? 'warn' : 'ok' };
  const m = Math.floor(s / 60);
  if (m < 60) return { label: `${m}m ${s % 60}s`, tone: m < 2 ? 'warn' : 'ok' };
  return { label: `${Math.floor(m / 60)}h ${m % 60}m`, tone: 'ok' };
}

/** Distance of the trigger from the current spot. */
export function fmtDist(trigger: number | null, spot: number | null): string {
  if (trigger === null || spot === null || spot === 0) return 'â€”';
  const diff = trigger - spot;
  const pct = (diff / Math.abs(spot)) * 100;
  const sign = diff > 0 ? '+' : '';
  return `${sign}${diff.toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
}

/** Confidence arrives as 0..1 or 0..100 depending on source â€” normalise to text. */
export function fmtConf(conf: number | null): string {
  if (conf === null) return 'â€”';
  return conf > 1 ? `${conf.toFixed(1)}%` : `${Math.round(conf * 100)}%`;
}

/** 0..100 usable width for confidence meters. */
export function confPct(conf: number | null): number {
  if (conf === null) return 0;
  const pct = conf > 1 ? conf : conf * 100;
  return Math.max(0, Math.min(100, pct));
}

export function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 8)}â€¦` : id;
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
    symbol: pickStr(o, 'underlying', 'instrument', 'symbol') ?? 'â€”',
    strategy: pickStr(o, 'strategy') ?? 'â€”',
    direction: o.direction ?? o.bias ?? 'NEUTRAL',
    state: pickStr(o, 'status', 'state', 'fsm_state') ?? 'â€”',
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

export type LedgerRow = {
  id: string;
  underlying: string;
  strategy: string;
  direction: unknown;
  status: string;
  outcomeLabel: string | null;
  isWinner: boolean | null;
  side: string | null;
  qty: number | null;
  entry: number | null;
  exit: number | null;
  current: number | null;
  realized: number | null;
  unrealized: number | null;
  total: number | null;
  timeMs: number | null;
  entryTimeMs: number | null;
  exitTimeMs: number | null;
  expiry: string | null;
};

export function toLedgerRow(t: unknown): LedgerRow | null {
  const o = getObj(t);
  if (!o) return null;
  const id = pickStr(o, 'signal_id', 'id');
  if (!id) return null;
  // Entry is a fill concept only. Never fall back to trigger/spot prices:
  // that renders index levels (e.g. 24925) as if they were option premiums.
  const entry = pickNum(o, 'actual_fill_price', 'fill_price', 'entry_price');
  let exit = pickNum(o, 'exit_price');
  let current = pickNum(o, 'current_price', 'ltp');
  // Same-domain rule: a premium entry (<=5000) paired with a spot-scale
  // exit/current (>5000) is legacy corruption — hide rather than display.
  if (entry !== null && entry <= 5000) {
    if (exit !== null && exit > 5000) exit = null;
    if (current !== null && current > 5000) current = null;
  }
  return {
    id,
    underlying: pickStr(o, 'underlying', 'instrument', 'symbol') ?? '—',
    strategy: pickStr(o, 'strategy') ?? '—',
    direction: o.direction ?? 'NEUTRAL',
    status: pickStr(o, 'status', 'state', 'fsm_state') ?? '—',
    outcomeLabel: pickStr(o, 'outcome_label', 'outcome'),
    isWinner: typeof o.is_winner === 'boolean' ? o.is_winner : null,
    side: pickStr(o, 'paper_side', 'side'),
    qty: pickNum(o, 'quantity', 'qty'),
    entry,
    exit,
    current,
    realized: pickNum(o, 'actual_pnl_inr', 'realized_pnl', 'pnl'),
    unrealized: pickNum(o, 'unrealized_pnl_inr'),
    total: pickNum(o, 'total_pnl_inr', 'net_pnl'),
    timeMs: pickMs(o, 'exited_at_utc', 'closed_at_ms', 'closed_at', 'updated_at_utc', 'created_at_utc'),
    entryTimeMs: pickMs(o, 'executed_at_utc', 'executed_at', 'created_at_utc', 'created_at_ms', 'created_at'),
    exitTimeMs: pickMs(o, 'exited_at_utc', 'closed_at_ms', 'closed_at'),
    expiry: ledgerExpiry(o),
  };
}

/** A ledger row with no fill and no exit is an unfilled setup, not a trade. */
export function isUnfilledLedgerRow(r: LedgerRow): boolean {
  return r.entry === null && r.exit === null;
}

export type LedgerSummary = {
  closed: number | null;
  winRate: number | null;
  realized: number | null;
  unrealized: number | null;
  total: number | null;
};

/** Backend summary keys vary (`*_inr` vs short names) — accept both. */
export function toLedgerSummary(sum: Record<string, unknown> | null): LedgerSummary | null {
  if (!sum) return null;
  return {
    closed: pickNum(sum, 'closed_trades', 'total_closed', 'closed', 'total_signals_audited'),
    winRate: pickNum(sum, 'win_rate_pct', 'win_rate', 'winRate'),
    realized: pickNum(sum, 'net_realized_pnl_inr', 'net_realized_pnl', 'realized', 'realized_pnl'),
    unrealized: pickNum(sum, 'net_unrealized_pnl_inr', 'net_unrealized_pnl', 'unrealized', 'unrealized_pnl'),
    total: pickNum(sum, 'total_pnl_inr', 'total_pnl', 'total', 'net_pnl'),
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



