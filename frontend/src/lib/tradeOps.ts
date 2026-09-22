/* Trade Ops (OMS) normalization — pure defensive parsing for the /trade module.
   Backend payloads vary across deploy versions (REST vs command-view stream
   legs); every field is coerced so the UI never crashes on partial data.
   No React, no timers, no HTTP here — safe for vitest. */

import { toNumber } from '@/lib/coerce';
import { getObj, pickMs, pickNum, pickStr, prettyKey, shortId } from '@/lib/signalsNormalize';

/* ---------------- broker mode ---------------- */

export type TradeMode = 'OFF' | 'PAPER' | 'LIVE' | 'UNKNOWN';

/** Defensively read the broker mode; anything unrecognized is UNKNOWN. */
export function normalizeTradeMode(value: unknown): TradeMode {
  const s = typeof value === 'string' ? value.trim().toUpperCase() : '';
  if (s === 'OFF' || s === 'PAPER' || s === 'LIVE') return s;
  return 'UNKNOWN';
}

/** Badge tone for the mode pill: LIVE reads dangerous, PAPER safe. */
export function modeBadgeClass(mode: TradeMode): 'b-bear' | 'b-bull' | 'b-neut' | 'b-warn' {
  switch (mode) {
    case 'LIVE':
      return 'b-bear';
    case 'PAPER':
      return 'b-bull';
    case 'OFF':
      return 'b-neut';
    default:
      return 'b-warn';
  }
}

/* ---------------- account ---------------- */

export type TradeAccount = {
  accountId: string | null;
  mode: TradeMode;
  isActive: boolean | null;
  displayName: string | null;
  /** Stream leg reports fail-closed when there is no DB session. */
  unavailable: boolean;
  unavailableReason: string | null;
  investmentLimit: number | null;
  available: number | null;
  reserved: number | null;
  deployed: number | null;
  dailyLoss: number | null;
  dailyLossLimit: number | null;
  breached: boolean | null;
  maxCapitalPerTrade: number | null;
  maxDailyLoss: number | null;
  consentOk: boolean | null;
};

/**
 * Accept both shapes:
 * - REST GET /api/v1/algo/account: {account_id, mode, is_active,
 *   capital: {investment_limit, max_capital_per_trade, max_daily_loss} | null,
 *   consent_ok}
 * - stream `algo.account` (get_account_detail): {account_id, mode, is_active,
 *   display_name, unavailable?, capital: {investment_limit, available,
 *   reserved, deployed, daily_loss, daily_loss_limit, is_breached},
 *   consent: {acknowledged}}
 */
export function toTradeAccount(input: unknown): TradeAccount | null {
  const o = getObj(input);
  if (!o) return null;
  const capital = getObj(o.capital);
  const consent = getObj(o.consent);
  const consentRaw = o.consent_ok ?? o.current_ok ?? consent?.acknowledged ?? null;
  return {
    accountId: pickStr(o, 'account_id'),
    mode: normalizeTradeMode(o.mode),
    isActive: typeof o.is_active === 'boolean' ? o.is_active : null,
    displayName: pickStr(o, 'display_name'),
    unavailable: o.unavailable === true,
    unavailableReason: pickStr(o, 'reason'),
    investmentLimit: capital ? pickNum(capital, 'investment_limit', 'limit') : null,
    available: capital ? pickNum(capital, 'available') : null,
    reserved: capital
      ? (pickNum(capital, 'reserved', 'reserved_pending') ?? null)
      : null,
    deployed: capital ? pickNum(capital, 'deployed') : null,
    dailyLoss: capital ? pickNum(capital, 'daily_loss') : null,
    dailyLossLimit: capital ? pickNum(capital, 'daily_loss_limit') : null,
    breached: capital && typeof capital.is_breached === 'boolean' ? capital.is_breached : null,
    maxCapitalPerTrade: capital ? pickNum(capital, 'max_capital_per_trade') : null,
    maxDailyLoss: capital ? pickNum(capital, 'max_daily_loss') : null,
    consentOk: typeof consentRaw === 'boolean' ? consentRaw : null,
  };
}

/* ---------------- exposure ---------------- */

export type ExposureSlice = { label: string; value: number | null };

export type TradeExposure = {
  gross: number | null;
  net: number | null;
  long: number | null;
  short: number | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  byUnderlying: ExposureSlice[];
  byStrategy: ExposureSlice[];
};

function toSlices(input: unknown): ExposureSlice[] {
  const o = getObj(input);
  if (!o) return [];
  const slices = Object.entries(o).map(([label, raw]) => ({
    label,
    value: toNumber(raw, { rejectBlankString: true }),
  }));
  slices.sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  return slices;
}

/** REST GET /exposure and the stream `algo.exposure` leg share one shape. */
export function toTradeExposure(input: unknown): TradeExposure | null {
  const o = getObj(input);
  if (!o) return null;
  return {
    gross: pickNum(o, 'gross_exposure', 'gross'),
    net: pickNum(o, 'net_exposure', 'net'),
    long: pickNum(o, 'long_exposure', 'long'),
    short: pickNum(o, 'short_exposure', 'short'),
    delta: pickNum(o, 'portfolio_delta', 'delta'),
    gamma: pickNum(o, 'portfolio_gamma', 'gamma'),
    theta: pickNum(o, 'portfolio_theta', 'theta'),
    vega: pickNum(o, 'portfolio_vega', 'vega'),
    byUnderlying: toSlices(o.by_underlying),
    byStrategy: toSlices(o.by_strategy),
  };
}

/* ---------------- orders ---------------- */

export type TradeOrder = {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL' | null;
  quantity: number | null;
  price: number | null;
  orderType: string | null;
  status: string;
  fillPrice: number | null;
  fillQty: number | null;
  brokerOrderId: string | null;
  rejectionReason: string | null;
  createdMs: number | null;
  isPaper: boolean | null;
};

/**
 * REST list_orders rows ({client_order_id, price/fill_price as strings,
 * created_at}) and the AlgoOrder interface shape ({client_order_id,
 * price?: number, average_price, filled_quantity, updated_at}).
 */
export function toTradeOrder(input: unknown): TradeOrder | null {
  const o = getObj(input);
  if (!o) return null;
  const id = pickStr(o, 'client_order_id', 'order_id', 'id');
  if (!id) return null;
  const sideRaw = pickStr(o, 'side');
  const side = sideRaw === 'BUY' || sideRaw === 'SELL' ? sideRaw : null;
  return {
    id,
    symbol: pickStr(o, 'symbol') ?? '—',
    side,
    quantity: pickNum(o, 'quantity', 'qty'),
    price: pickNum(o, 'price'),
    orderType: pickStr(o, 'order_type'),
    status: pickStr(o, 'status') ?? 'UNKNOWN',
    fillPrice: pickNum(o, 'fill_price', 'average_price'),
    fillQty: pickNum(o, 'fill_quantity', 'filled_quantity'),
    brokerOrderId: pickStr(o, 'broker_order_id'),
    rejectionReason: pickStr(o, 'rejection_reason'),
    createdMs: pickMs(o, 'created_at', 'created_at_ms', 'updated_at'),
    isPaper: typeof o.is_paper === 'boolean' ? o.is_paper : null,
  };
}

export type OrderTone = 'bull' | 'bear' | 'info' | 'warn' | 'neut';

/** Status pill tone for OMS order states. */
export function orderStatusTone(status: string | null): OrderTone {
  const s = (status ?? '').toUpperCase();
  if (/(FILLED)/.test(s) && !/PARTIALLY/.test(s)) return 'bull';
  if (/(CANCELLED|REJECTED|FAILED|EXPIRED)/.test(s)) return 'bear';
  if (/(CREATED|SUBMITTED|RISK_APPROVED|PENDING|OPEN)/.test(s)) return 'info';
  if (/(PARTIALLY_FILLED|PARTIAL)/.test(s)) return 'warn';
  return 'neut';
}

/**
 * Only working (non-terminal) orders can be cancelled. PARTIALLY_FILLED is
 * excluded on purpose — cancelling a partially filled broker order needs an
 * explicit exit, not a blind cancel.
 */
export function isOrderCancellable(status: string | null): boolean {
  const s = (status ?? '').toUpperCase();
  return s === 'CREATED' || s === 'RISK_APPROVED' || s === 'SUBMITTED';
}

/* ---------------- positions ---------------- */

export type TradePosition = {
  id: string;
  symbol: string;
  underlying: string | null;
  side: string | null;
  quantity: number | null;
  avgEntry: number | null;
  currentPrice: number | null;
  unrealized: number | null;
  realized: number | null;
  exitState: string | null;
  isOpen: boolean | null;
  strategyId: string | null;
};

/**
 * REST list_positions rows ({position_id, average_entry/current_price as
 * strings, is_open}) and the AlgoPosition interface shape ({position_id,
 * average_price: number, current_price?}).
 */
export function toTradePosition(input: unknown): TradePosition | null {
  const o = getObj(input);
  if (!o) return null;
  const id = pickStr(o, 'position_id', 'id');
  if (!id) return null;
  return {
    id,
    symbol: pickStr(o, 'symbol') ?? '—',
    underlying: pickStr(o, 'underlying'),
    side: pickStr(o, 'side'),
    quantity: pickNum(o, 'quantity', 'qty'),
    avgEntry: pickNum(o, 'average_entry', 'average_price', 'entry_price'),
    currentPrice: pickNum(o, 'current_price', 'ltp'),
    unrealized: pickNum(o, 'unrealized_pnl', 'unrealized'),
    realized: pickNum(o, 'realized_pnl', 'realized'),
    exitState: pickStr(o, 'exit_state'),
    isOpen: typeof o.is_open === 'boolean' ? o.is_open : null,
    strategyId: pickStr(o, 'strategy_id'),
  };
}

/* ---------------- audit ---------------- */

export type TradeAuditRow = {
  eventType: string;
  timestampMs: number | null;
  symbol: string | null;
  clientOrderId: string | null;
  detail: string | null;
};

/** Compact one-line summary of an audit `details` payload. */
export function summarizeDetails(details: unknown, limit = 160): string | null {
  if (details === null || details === undefined) return null;
  if (typeof details === 'string') {
    const s = details.trim();
    if (!s) return null;
    return s.length > limit ? `${s.slice(0, limit)}…` : s;
  }
  if (typeof details === 'object') {
    try {
      const s = JSON.stringify(details);
      return s.length > limit ? `${s.slice(0, limit)}…` : s;
    } catch {
      return null;
    }
  }
  const s = String(details);
  return s.length > limit ? `${s.slice(0, limit)}…` : s;
}

/** REST GET /audit rows. Never fabricates — unparseable rows return null. */
export function toTradeAuditRow(input: unknown): TradeAuditRow | null {
  const o = getObj(input);
  if (!o) return null;
  const eventType = pickStr(o, 'event_type', 'event', 'type');
  if (!eventType) return null;
  const clientRaw = o.client_order_id;
  return {
    eventType,
    timestampMs: pickMs(o, 'timestamp', 'created_at', 'acknowledged_at'),
    symbol: pickStr(o, 'symbol'),
    clientOrderId:
      typeof clientRaw === 'string' && clientRaw
        ? shortId(clientRaw)
        : pickStr(o, 'order_id'),
    detail:
      summarizeDetails(o.details) ??
      summarizeDetails(o.trade_risk_result) ??
      summarizeDetails(o.portfolio_risk_result),
  };
}

/* ---------------- sizing preview ---------------- */

export type SizingPreview = {
  quantity: number | null;
  notional: number | null;
  riskPerUnit: number | null;
  reason: string | null;
  cappedBy: string | null;
};

/** POST /sizing/preview response: {quantity, notional, risk_per_unit, reason, capped_by}. */
export function toSizingPreview(input: unknown): SizingPreview | null {
  const data = getObj(getObj(input)?.data ?? input);
  if (!data) return null;
  if (data.quantity === undefined && data.notional === undefined) return null;
  return {
    quantity: toNumber(data.quantity, { coerceNonString: true }),
    notional: toNumber(data.notional, { rejectBlankString: true }),
    riskPerUnit: toNumber(data.risk_per_unit, { rejectBlankString: true }),
    reason: typeof data.reason === 'string' ? data.reason : null,
    cappedBy: typeof data.capped_by === 'string' ? data.capped_by : null,
  };
}

export type SizingFormState = {
  entryPrice: string;
  stopPrice: string;
  riskBudget: string;
  lotSize: string;
  contractMultiplier: string;
  maxCapitalPerTrade: string;
  maxPositionSize: string;
  availableCapital: string;
};

function parseOptionalPositive(raw: string): number | null | 'invalid' {
  if (raw.trim() === '') return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return 'invalid';
  return n;
}

export type SizingPayloadResult =
  | { ok: true; payload: Record<string, number> }
  | { ok: false; error: string };

/**
 * Validate the sizing form into the exact POST /sizing/preview body.
 * entry_price is required and must be > 0; every other field is optional.
 */
export function buildSizingPayload(form: SizingFormState): SizingPayloadResult {
  const entry = Number(form.entryPrice);
  if (form.entryPrice.trim() === '' || !Number.isFinite(entry) || entry <= 0) {
    return { ok: false, error: 'Entry price is required and must be greater than zero.' };
  }
  const payload: Record<string, number> = { entry_price: entry };
  const optional: Array<[keyof SizingFormState, string, string]> = [
    ['stopPrice', 'stop_price', 'Stop price'],
    ['riskBudget', 'risk_budget', 'Risk budget'],
    ['lotSize', 'lot_size', 'Lot size'],
    ['contractMultiplier', 'contract_multiplier', 'Contract multiplier'],
    ['maxCapitalPerTrade', 'max_capital_per_trade', 'Max capital per trade'],
    ['maxPositionSize', 'max_position_size', 'Max position size'],
    ['availableCapital', 'available_capital', 'Available capital'],
  ];
  for (const [field, key, label] of optional) {
    const parsed = parseOptionalPositive(form[field]);
    if (parsed === 'invalid') {
      return { ok: false, error: `${label} must be a positive number, or left blank.` };
    }
    if (parsed !== null) payload[key] = field === 'lotSize' || field === 'maxPositionSize' ? Math.floor(parsed) : parsed;
  }
  return { ok: true, payload };
}

/* ---------------- compact readouts ---------------- */

export type DisplayEntry = { label: string; value: string };

function scalarText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') {
    const s = value.trim();
    return s ? s : null;
  }
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : null;
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  return null;
}

/**
 * One-level flatten of a record into label/value pairs for sg-kv lists.
 * Nested objects render as compact JSON (truncated); arrays as counts or
 * comma-joined scalars. Unknown shapes yield an empty list, never a crash.
 */
export function toDisplayEntries(input: unknown, limit = 14): DisplayEntry[] {
  const o = getObj(input);
  if (!o) return [];
  const entries: DisplayEntry[] = [];
  for (const [key, raw] of Object.entries(o)) {
    const scalar = scalarText(raw);
    if (scalar !== null) {
      entries.push({ label: prettyKey(key), value: scalar });
    } else if (Array.isArray(raw)) {
      const scalars = raw.map(scalarText).filter((s): s is string => s !== null);
      entries.push({
        label: prettyKey(key),
        value: scalars.length === raw.length && scalars.length > 0 ? scalars.join(', ') : `${raw.length} item(s)`,
      });
    } else if (raw && typeof raw === 'object') {
      try {
        const s = JSON.stringify(raw);
        entries.push({ label: prettyKey(key), value: s.length > 120 ? `${s.slice(0, 120)}…` : s });
      } catch {
        entries.push({ label: prettyKey(key), value: '—' });
      }
    }
    if (entries.length >= limit) break;
  }
  return entries;
}

export type StrategyRow = {
  id: string;
  name: string;
  stage: string | null;
  aiMode: string | null;
  active: boolean | null;
};

/** GET /strategies rows (list of dicts, never wrapped). */
export function toStrategyRow(input: unknown): StrategyRow | null {
  const o = getObj(input);
  if (!o) return null;
  const id = pickStr(o, 'strategy_id', 'id');
  if (!id) return null;
  return {
    id,
    name: pickStr(o, 'name') ?? id,
    stage: pickStr(o, 'lifecycle_stage', 'stage'),
    aiMode: pickStr(o, 'ai_mode'),
    active: typeof o.is_active === 'boolean' ? o.is_active : null,
  };
}

export type AiModelRow = {
  key: string;
  provider: string | null;
  modelId: string | null;
  version: string | null;
  status: string | null;
  canaryPct: number | null;
  lastKnownGood: boolean | null;
};

/** GET /ai-models rows. */
export function toAiModelRow(input: unknown): AiModelRow | null {
  const o = getObj(input);
  if (!o) return null;
  const key = pickStr(o, 'key');
  if (!key) return null;
  return {
    key,
    provider: pickStr(o, 'provider'),
    modelId: pickStr(o, 'model_id'),
    version: pickStr(o, 'model_version', 'version'),
    status: pickStr(o, 'status'),
    canaryPct: pickNum(o, 'canary_pct'),
    lastKnownGood: typeof o.is_last_known_good === 'boolean' ? o.is_last_known_good : null,
  };
}
