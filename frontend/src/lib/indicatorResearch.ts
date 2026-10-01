import type {
  BacktestRequest,
  BacktestResponse,
  BacktestSettingsInput,
  CostSettingsInput,
  ExecutionSettingsInput,
  ExitSettingsInput,
  IndicatorMetadata,
  RuleCondition,
  RuleGroup,
  RuleOperand,
  RuleSet,
} from './api/indicatorResearch';

/* ── Formatting ─────────────────────────────────────────────────────────── */

export function fmt(value: unknown, digits = 2): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtInt(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return '—';
  return Math.round(n).toLocaleString('en-IN');
}

export function fmtPct(value: unknown, digits = 2): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return '—';
  return `${n >= 0 ? '' : ''}${n.toFixed(digits)}%`;
}

/** Money with an explicit rupee sign — research results are rupee-denominated. */
export function fmtMoney(value: unknown, digits = 0): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return '—';
  const sign = n < 0 ? '-' : '';
  return `${sign}₹${Math.abs(n).toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function fmtCompact(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e7) return `${(n / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${(n / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toFixed(2);
}

/** "2025-01-01T09:15:00+05:30" → "01 Jan 09:15" (chart axes stay narrow). */
export function fmtStamp(iso: string | null | undefined, withDate = true): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const day = d.getDate().toString().padStart(2, '0');
  const month = d.toLocaleString('en-GB', { month: 'short' });
  const hh = d.getHours().toString().padStart(2, '0');
  const mm = d.getMinutes().toString().padStart(2, '0');
  return withDate ? `${day} ${month} ${hh}:${mm}` : `${hh}:${mm}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getDate().toString().padStart(2, '0')} ${d.toLocaleString('en-GB', { month: 'short' })} ${d.getFullYear()}`;
}

/** Tone for a signed number cell. */
export function tone(value: unknown): 'up' | 'down' | 'flat' {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n) || n === 0) return 'flat';
  return n > 0 ? 'up' : 'down';
}

export function toneClass(value: unknown): string {
  const t = tone(value);
  if (t === 'up') return 'text-up-strong';
  if (t === 'down') return 'text-down-strong';
  return 'text-ink-3';
}

/* ── Feature / operand labels ───────────────────────────────────────────── */

const ACRONYMS = new Set(['rsi', 'macd', 'atr', 'adx', 'cci', 'ema', 'sma', 'vwap', 'stc', 'obv', 'mfi', 'mama', 'fama', 'ebsw', 'dsp', 'sqz', 'hmm']);

export function prettify(token: string): string {
  return token
    .split(/[_.\s]+/)
    .filter(Boolean)
    .map((part) => {
      const lower = part.toLowerCase();
      if (ACRONYMS.has(lower)) return part.toUpperCase();
      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join(' ');
}

/** "fisher.value" → "Fisher · Value"; "close" → "Close". */
export function featureLabel(feature: string): string {
  const [indicator, output] = feature.split('.');
  if (!output) return prettify(indicator);
  return `${prettify(indicator)} · ${prettify(output)}`;
}

export function operandLabel(operand: RuleOperand | undefined): string {
  if (operand === undefined || operand === null) return '—';
  if (typeof operand === 'number') return String(operand);
  if (typeof operand === 'boolean') return operand ? 'True' : 'False';
  if (typeof operand === 'string') return featureLabel(operand);
  if (Array.isArray(operand)) return `${operand[0]} … ${operand[1]}`;
  if (typeof operand === 'object') {
    if ('feature' in operand) return featureLabel(operand.feature);
    return String(operand.value);
  }
  return String(operand);
}

export function operatorLabel(operator: string): string {
  const map: Record<string, string> = {
    '>': 'is above',
    '<': 'is below',
    '>=': 'is at or above',
    '<=': 'is at or below',
    '==': 'equals',
    '!=': 'does not equal',
    crosses_above: 'crosses above',
    crosses_below: 'crosses below',
    turns_up: 'turns up',
    turns_down: 'turns down',
    in_range: 'is within',
    outside_range: 'is outside',
    slope_up: 'slope is rising',
    slope_down: 'slope is falling',
    rising: 'is rising',
    falling: 'is falling',
    is_true: 'is true',
    is_false: 'is false',
  };
  return map[operator] ?? operator;
}

export function isGroup(node: RuleCondition | RuleGroup): node is RuleGroup {
  return Array.isArray((node as RuleGroup).conditions);
}

export function describeRule(node: RuleCondition | RuleGroup | null | undefined): string {
  if (!node) return '—';
  if (isGroup(node)) {
    if (!node.conditions?.length) return '—';
    const joiner = node.operator === 'AND' ? ' and ' : node.operator === 'OR' ? ' or ' : 'not ';
    if (node.operator === 'NOT') return `not (${node.conditions.map(describeRule).join(' or ')})`;
    return node.conditions.map(describeRule).join(joiner);
  }
  const left = operandLabel(node.left);
  const op = operatorLabel(node.operator);
  if (node.right === undefined || node.operator === 'turns_up' || node.operator === 'turns_down' || node.operator === 'slope_up' || node.operator === 'slope_down' || node.operator === 'rising' || node.operator === 'falling' || node.operator === 'is_true' || node.operator === 'is_false') {
    const bars = node.bars && node.bars > 1 ? ` over ${node.bars} bars` : '';
    return `${left} ${op}${bars}`;
  }
  return `${left} ${op} ${operandLabel(node.right)}`;
}

/* ── Rule building ──────────────────────────────────────────────────────── */

export function condition(
  left: RuleOperand,
  operator: string,
  right?: RuleOperand,
  extra?: Partial<RuleCondition>,
): RuleCondition {
  return { left, operator, ...(right !== undefined ? { right } : {}), enabled: true, ...extra };
}

export function group(operator: 'AND' | 'OR' | 'NOT', conditions: Array<RuleCondition | RuleGroup>): RuleGroup {
  return { operator, conditions };
}

/**
 * A starting rule set that is *actually meaningful* for the selected
 * indicator — if the backend shipped defaults we use those, otherwise we fall
 * back to a crossover of the indicator's primary output against its
 * secondary output (or a zero line for single-output oscillators).
 */
export function defaultRulesFor(meta: IndicatorMetadata | null): RuleSet {
  if (!meta) return { long: null, short: null };
  if (meta.default_rules && (meta.default_rules.long || meta.default_rules.short)) {
    return JSON.parse(JSON.stringify(meta.default_rules)) as RuleSet;
  }
  const primary = meta.outputs.find((o) => o.role !== 'histogram') ?? meta.outputs[0];
  if (!primary) return { long: null, short: null };
  const feature = `${meta.id}.${primary.name}`;
  const secondary = meta.outputs.find((o) => o.name !== primary.name && o.pane === primary.pane);
  if (secondary) {
    return {
      long: group('AND', [condition(feature, 'crosses_above', `${meta.id}.${secondary.name}`)]),
      short: group('AND', [condition(feature, 'crosses_below', `${meta.id}.${secondary.name}`)]),
    };
  }
  return {
    long: group('AND', [condition(feature, 'crosses_above', 0)]),
    short: group('AND', [condition(feature, 'crosses_below', 0)]),
  };
}

/** Deep clone so edits never mutate the catalog copy held in state. */
export function cloneRules(rules: RuleSet | null | undefined): RuleSet {
  if (!rules) return { long: null, short: null };
  return JSON.parse(JSON.stringify(rules)) as RuleSet;
}

export function countConditions(node: RuleCondition | RuleGroup | null | undefined): number {
  if (!node) return 0;
  if (isGroup(node)) {
    return (node.conditions ?? []).reduce((sum, child) => sum + countConditions(child), 0);
  }
  return node.enabled === false ? 0 : 1;
}

/* ── Result helpers ─────────────────────────────────────────────────────── */

export type MetricCell = {
  label: string;
  value: string;
  raw?: number | null;
  tone?: 'up' | 'down' | 'flat';
  hint?: string;
  undefined?: boolean;
};

/** Consistent in-sample banner text: never let a number stand alone. */
export function resultScopeLine(result: BacktestResponse | null): string | null {
  if (!result?.data) return null;
  const { instrument, timeframe, data_start, data_end, bars, version } = result.data;
  const range = data_start && data_end ? `${data_start.slice(0, 10)} → ${data_end.slice(0, 10)}` : 'unknown range';
  return `${instrument} · ${timeframe} · ${range} · ${fmtInt(bars)} bars${version ? ` · data ${version}` : ''}`;
}

/** SettingsState in the research hook is `typeof STARTING_SETTINGS`, so the
 *  three groups and the backtest flags must stay required while the leaf enums
 *  widen to the full contract union. */
type StartingSettings = BacktestSettingsInput &
  Required<
    Pick<
      BacktestRequest,
      'verify_causality' | 'include_trades' | 'include_equity_curve' | 'max_equity_points'
    >
  > & {
    execution: Required<ExecutionSettingsInput>;
    exits: Required<ExitSettingsInput>;
    costs: Required<CostSettingsInput>;
  };

export const STARTING_SETTINGS: StartingSettings = {
  execution: {
    entry_fill: 'next_open',
    size_mode: 'fixed_fraction',
    initial_capital: 1_000_000,
    allocation_pct: 1, // fraction of equity, 0–1 — the engine rejects > 1
    fixed_units: 1,
    leverage: 1,
  },
  exits: {
    stop_mode: 'none',
    stop_value: 1,
    target_mode: 'none',
    target_value: 2,
    max_bars_held: null,
    exit_on_opposite: true,
    allow_long: true,
    allow_short: true,
    exit_at_session_close: false,
  },
  costs: {
    slippage_bps: 2,
    brokerage_bps: 3,
    exchange_bps: 0.3,
    sebi_bps: 0.1,
    gst_on_fees_pct: 18,
    stt_sell_bps: 2.5,
    stamp_buy_bps: 0.3,
  },
  verify_causality: true,
  include_trades: true,
  include_equity_curve: true,
  max_equity_points: 4000,
};

export const COST_PRESETS = {
  zero: {
    label: 'Zero cost (diagnostic only)',
    costs: {
      slippage_bps: 0,
      brokerage_bps: 0,
      exchange_bps: 0,
      sebi_bps: 0,
      gst_on_fees_pct: 0,
      stt_sell_bps: 0,
      stamp_buy_bps: 0,
    },
  },
  reference: {
    label: 'DROID reference cost model',
    costs: { ...STARTING_SETTINGS.costs },
  },
  punitive: {
    label: 'Punitive (stress test)',
    costs: {
      slippage_bps: 5,
      brokerage_bps: 5,
      exchange_bps: 0.5,
      sebi_bps: 0.1,
      gst_on_fees_pct: 18,
      stt_sell_bps: 2.5,
      stamp_buy_bps: 0.3,
    },
  },
};

/** ISO date (yyyy-mm-dd) N calendar days back from today. */
export function daysAgoIso(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
