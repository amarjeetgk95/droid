/* AI Copilot pure logic: message reducer, defensive SSE-chunk parsing,
   backend error-hint mapping, and report normalizers.
   No React, no I/O — safe to unit-test. */

import type {
  AIChatMessage,
  AIChatStreamChunk,
  OpenRouterModel,
} from './types';
import { asStr, getObj, pickNum, pickStr } from './signalsNormalize';

const CHAT_TYPES = ['content', 'reasoning', 'tool_call', 'tool_result', 'done', 'error'] as const;
type ChatChunkType = (typeof CHAT_TYPES)[number];

function isChatChunkType(v: unknown): v is ChatChunkType {
  return typeof v === 'string' && (CHAT_TYPES as readonly string[]).includes(v);
}

function asOptionalStr(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s ? s : null;
}

/** Defensive parse of one SSE `data:` JSON payload into an AIChatStreamChunk. Null when unusable. */
export function parseChatChunk(input: unknown): AIChatStreamChunk | null {
  const o = getObj(input);
  if (!o) return null;
  const type = o.type;
  if (!isChatChunkType(type)) return null;
  return {
    type,
    delta: typeof o.delta === 'string' ? o.delta : '',
    reasoning_delta: typeof o.reasoning_delta === 'string' ? o.reasoning_delta : '',
    tool_call: getObj(o.tool_call) as AIChatStreamChunk['tool_call'],
    tool_result: getObj(o.tool_result) as AIChatStreamChunk['tool_result'],
    finish_reason: asOptionalStr(o.finish_reason),
    provider_used: asOptionalStr(o.provider_used),
    model_used: asOptionalStr(o.model_used),
  };
}

export type CopilotRole = 'user' | 'assistant';

export interface CopilotMessage {
  id: string;
  role: CopilotRole;
  content: string;
  reasoning: string;
  toolNotes: string[];
  provider: string | null;
  model: string | null;
  pending: boolean;
  error: string | null;
}

let idCounter = 0;

export function newCopilotId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${idCounter}`;
}

export function createUserMessage(content: string): CopilotMessage {
  return {
    id: newCopilotId('u'),
    role: 'user',
    content,
    reasoning: '',
    toolNotes: [],
    provider: null,
    model: null,
    pending: false,
    error: null,
  };
}

export function createPendingAssistant(): CopilotMessage {
  return {
    id: newCopilotId('a'),
    role: 'assistant',
    content: '',
    reasoning: '',
    toolNotes: [],
    provider: null,
    model: null,
    pending: true,
    error: null,
  };
}

/** Human-readable one-liner for a `tool_call` chunk payload. Never throws. */
export function summarizeToolCall(toolCall: unknown): string {
  const o = getObj(toolCall);
  if (!o) return 'assistant requested a tool';
  const fn = getObj(o.function);
  const name = pickStr(o, 'name') ?? pickStr(fn ?? {}, 'name') ?? 'unknown-tool';
  return `calling ${name}`;
}

/** Human-readable one-liner for a `tool_result` chunk payload. Never throws. */
export function summarizeToolResult(toolResult: unknown): string {
  const o = getObj(toolResult);
  if (!o) return 'tool returned';
  const name = pickStr(o, 'name') ?? 'tool';
  const result = getObj(o.result);
  const err = result ? asStr(result.error) : null;
  return err ? `${name} failed: ${err.slice(0, 160)}` : `${name} returned market data`;
}

/**
 * Pure reducer: fold one validated stream chunk into the pending assistant
 * message. Mirrors the backend SSE contract (`app/ai/streaming.py`):
 * `content` carries `delta`, `reasoning` carries `reasoning_delta`,
 * `tool_call`/`tool_result` carry their payload objects, `done` closes the
 * turn, `error` carries the message in `delta`.
 */
export function applyChatChunk(msg: CopilotMessage, chunk: AIChatStreamChunk): CopilotMessage {
  if (chunk.provider_used) msg = { ...msg, provider: chunk.provider_used };
  if (chunk.model_used) msg = { ...msg, model: chunk.model_used };
  switch (chunk.type) {
    case 'content':
      return chunk.delta ? { ...msg, content: msg.content + chunk.delta } : msg;
    case 'reasoning':
      return chunk.reasoning_delta ? { ...msg, reasoning: msg.reasoning + chunk.reasoning_delta } : msg;
    case 'tool_call': {
      const note = summarizeToolCall(chunk.tool_call);
      return { ...msg, toolNotes: [...msg.toolNotes, note] };
    }
    case 'tool_result': {
      const note = summarizeToolResult(chunk.tool_result);
      return { ...msg, toolNotes: [...msg.toolNotes, note] };
    }
    case 'done':
      return { ...msg, pending: false };
    case 'error':
      return { ...msg, pending: false, error: chunk.delta || 'Stream error' };
    default:
      return msg;
  }
}

/** Build the backend `messages` array from visible history plus the new turn. Caps at the last 20. */
export function buildChatMessages(history: CopilotMessage[], next: string): AIChatMessage[] {
  const turns = [...history.filter((m) => !m.error), createUserMessage(next)].slice(-20);
  return turns.map((m) => ({ role: m.role, content: m.content }));
}

export type CopilotErrorKind = 'no-provider' | 'paid-disabled' | 'generic';

export interface CopilotErrorHint {
  kind: CopilotErrorKind;
  hint: string;
}

/**
 * Map raw backend/chat failures to honest, actionable hints.
 * "No AI provider configured" -> /settings setup hint; paid-gate -> free-model hint.
 */
export function copilotErrorHint(message: string): CopilotErrorHint {
  const text = message || '';
  if (/no ai provider configured/i.test(text)) {
    return {
      kind: 'no-provider',
      hint: 'No AI provider is configured on the backend. Open /settings → AI Engine, add a key (e.g. OpenRouter sk-or-v1-…), Save, then retry.',
    };
  }
  if (/paid models are disabled/i.test(text)) {
    return {
      kind: 'paid-disabled',
      hint: 'Paid models are disabled. Pick a FREE OpenRouter model (prompt = 0 and completion = 0), or enable Allow Paid Models in Settings.',
    };
  }
  return { kind: 'generic', hint: text };
}

// ---------------------------------------------------------------------------
// Report normalizers (defensive — backend payloads vary across versions)
// ---------------------------------------------------------------------------

export interface BriefingCard {
  symbol: string;
  session: string;
  summary: string;
  levels: Array<{ label: string; value: string }>;
  pinPivots: string;
  fiiDii: string;
  playbook: string[];
  provider: string;
  timestamp: string;
}

function fmtVal(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') return Number.isFinite(v) ? v.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—';
  return String(v);
}

export function normalizeBriefing(data: unknown): BriefingCard | null {
  const o = getObj(data);
  if (!o) return null;
  const levelsObj = getObj(o.key_levels_to_watch);
  const levels = levelsObj
    ? Object.entries(levelsObj).map(([label, value]) => ({ label, value: fmtVal(value) }))
    : [];
  const playbookRaw = Array.isArray(o.actionable_playbook) ? o.actionable_playbook : [];
  return {
    symbol: pickStr(o, 'symbol') ?? '—',
    session: pickStr(o, 'session_type') ?? '—',
    summary: pickStr(o, 'executive_summary') ?? 'No summary returned.',
    levels,
    pinPivots: pickStr(o, 'options_pin_and_pivots') ?? '—',
    fiiDii: pickStr(o, 'fii_dii_implication') ?? '—',
    playbook: playbookRaw.map((s) => String(s)).filter((s) => s.trim()),
    provider: pickStr(o, 'provider_used') ?? '—',
    timestamp: pickStr(o, 'timestamp') ?? '—',
  };
}

export interface AnalyzeSection {
  label: string;
  text: string;
}

export interface AnalyzeReport {
  symbol: string;
  bias: string;
  confidence: number | null;
  summary: string;
  sections: AnalyzeSection[];
  provider: string;
  timestamp: string;
}

const ANALYZE_SECTIONS: Array<[string, string]> = [
  ['options_interpretation', 'Options interpretation'],
  ['futures_flow_analysis', 'Futures flow'],
  ['regime_and_levels', 'Regime and levels'],
  ['recommended_strategy_framework', 'Strategy framework'],
  ['risk_management_notes', 'Risk management'],
  ['simple_takeaway', 'Simple takeaway'],
  ['disclaimer', 'Disclaimer'],
];

export function normalizeAnalyzeReport(data: unknown): AnalyzeReport | null {
  const o = getObj(data);
  if (!o) return null;
  const sections: AnalyzeSection[] = [];
  for (const [key, label] of ANALYZE_SECTIONS) {
    const text = asStr(o[key]);
    if (text) sections.push({ label, text });
  }
  return {
    symbol: pickStr(o, 'symbol') ?? '—',
    bias: pickStr(o, 'market_bias') ?? 'NEUTRAL',
    confidence: pickNum(o, 'confidence'),
    summary: pickStr(o, 'executive_summary') ?? 'No summary returned.',
    sections,
    provider: pickStr(o, 'provider_used') ?? '—',
    timestamp: pickStr(o, 'timestamp') ?? '—',
  };
}

export interface HistoryRow {
  id: string;
  symbol: string;
  bias: string;
  confidence: number | null;
  summary: string;
  timestamp: string;
}

export function normalizeHistoryList(data: unknown): HistoryRow[] {
  if (!Array.isArray(data)) return [];
  const rows: HistoryRow[] = [];
  for (const item of data) {
    const o = getObj(item);
    if (!o) continue;
    const id = pickStr(o, 'id');
    if (!id) continue;
    rows.push({
      id,
      symbol: pickStr(o, 'symbol') ?? '—',
      bias: pickStr(o, 'market_bias') ?? '—',
      confidence: pickNum(o, 'confidence'),
      summary: pickStr(o, 'executive_summary') ?? '—',
      timestamp: pickStr(o, 'timestamp') ?? '—',
    });
  }
  return rows;
}

export interface ModelOption {
  id: string;
  name: string;
  isFree: boolean;
}

export function normalizeModelOptions(models: unknown): ModelOption[] {
  if (!Array.isArray(models)) return [];
  const out: ModelOption[] = [];
  for (const m of models) {
    const o = getObj(m);
    if (!o) continue;
    const id = pickStr(o, 'id');
    if (!id) continue;
    out.push({
      id,
      name: pickStr(o, 'name') ?? id,
      isFree: o.is_free === true,
    });
  }
  return out;
}

/** Tone class for a market-bias / decision badge. */
export function biasTone(v: unknown): 'bull' | 'bear' | 'neut' | 'warn' | 'info' {
  const s = String(v ?? '').toUpperCase();
  if (/(BULL|CONFIRM|LONG|BUY)/.test(s)) return 'bull';
  if (/(BEAR|REJECT|SHORT|SELL|LOSS)/.test(s)) return 'bear';
  if (/(WATCH|WAIT|UNCERTAIN|VOLATILE)/.test(s)) return 'warn';
  if (/(ARMED|READY|TRIGGERED|LIVE)/.test(s)) return 'info';
  return 'neut';
}

/** Flatten an unknown deep-insight payload into capped label/value rows. Never throws. */
export function flattenReport(data: unknown, max = 40): Array<{ label: string; value: string }> {
  const rows: Array<{ label: string; value: string }> = [];
  const walk = (v: unknown, prefix: string, depth: number) => {
    if (rows.length >= max || depth > 2) return;
    const o = getObj(v);
    if (!o) {
      if (prefix) rows.push({ label: prefix, value: fmtVal(v) });
      return;
    }
    for (const [k, val] of Object.entries(o)) {
      if (rows.length >= max) return;
      const label = prefix ? `${prefix}.${k}` : k;
      if (val !== null && typeof val === 'object' && !Array.isArray(val)) {
        walk(val, label, depth + 1);
      } else if (Array.isArray(val)) {
        const items = val.map((s) => String(s)).filter((s) => s.trim());
        rows.push({ label, value: items.length > 0 ? items.slice(0, 6).join(' · ') : '—' });
      } else {
        rows.push({ label, value: fmtVal(val) });
      }
    }
  };
  walk(data, '', 0);
  return rows;
}

export interface ValidationVerdict {
  symbol: string;
  decision: string;
  score: number | null;
  riskReward: number | null;
  verdict: string;
  technical: string;
  derivatives: string;
  volatility: string;
  invalidations: string[];
  warnings: string[];
  provider: string;
}

export function normalizeValidation(data: unknown): ValidationVerdict | null {
  const o = getObj(data);
  if (!o) return null;
  const strList = (v: unknown): string[] =>
    Array.isArray(v) ? v.map((s) => String(s)).filter((s) => s.trim()) : [];
  return {
    symbol: pickStr(o, 'symbol') ?? '—',
    decision: pickStr(o, 'decision') ?? 'UNCERTAIN',
    score: pickNum(o, 'score'),
    riskReward: pickNum(o, 'risk_reward_calculated'),
    verdict: pickStr(o, 'executive_verdict') ?? 'No verdict returned.',
    technical: pickStr(o, 'technical_alignment') ?? '—',
    derivatives: pickStr(o, 'derivatives_alignment') ?? '—',
    volatility: pickStr(o, 'volatility_regime_check') ?? '—',
    invalidations: strList(o.invalidation_conditions),
    warnings: strList(o.warning_traps),
    provider: pickStr(o, 'provider_used') ?? '—',
  };
}

export interface StrategyLeg {
  strike: string;
  type: string;
  action: string;
  premium: string;
}

export interface StrategyPlan {
  symbol: string;
  name: string;
  outlook: string;
  legs: StrategyLeg[];
  maxProfit: string;
  maxLoss: string;
  riskReward: string;
  breakevens: string[];
  rationale: string;
  entry: string[];
  exit: string[];
  risk: string;
  provider: string;
}

export function normalizeStrategy(data: unknown): StrategyPlan | null {
  const o = getObj(data);
  if (!o) return null;
  const legsRaw = Array.isArray(o.legs) ? o.legs : [];
  const legs: StrategyLeg[] = [];
  for (const leg of legsRaw) {
    const lo = getObj(leg);
    if (!lo) continue;
    legs.push({
      strike: fmtVal(lo.strike),
      type: pickStr(lo, 'option_type') ?? '—',
      action: pickStr(lo, 'action') ?? '—',
      premium: fmtVal(lo.estimated_premium),
    });
  }
  const strList = (v: unknown): string[] =>
    Array.isArray(v) ? v.map((s) => String(s)).filter((s) => s.trim()) : [];
  const numList = (v: unknown): string[] =>
    Array.isArray(v) ? v.map((n) => fmtVal(n)) : [];
  return {
    symbol: pickStr(o, 'symbol') ?? '—',
    name: pickStr(o, 'strategy_name') ?? '—',
    outlook: pickStr(o, 'market_outlook') ?? '—',
    legs,
    maxProfit: fmtVal(o.max_profit_pts),
    maxLoss: fmtVal(o.max_loss_pts),
    riskReward: fmtVal(o.risk_reward_ratio),
    breakevens: numList(o.breakevens),
    rationale: pickStr(o, 'rationale') ?? '—',
    entry: strList(o.entry_rules),
    exit: strList(o.exit_rules),
    risk: pickStr(o, 'risk_management') ?? '—',
    provider: pickStr(o, 'provider_used') ?? '—',
  };
}

/** Keep only plausibly-set model options for the chat picker (free first). */
export function sortModelOptions(options: ModelOption[]): ModelOption[] {
  return [...options].sort((a, b) => Number(b.isFree) - Number(a.isFree) || a.name.localeCompare(b.name));
}

export type { OpenRouterModel };
