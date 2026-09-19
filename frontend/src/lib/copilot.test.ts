import { describe, expect, it } from 'vitest';

import {
  applyChatChunk,
  biasTone,
  buildChatMessages,
  copilotErrorHint,
  createPendingAssistant,
  createUserMessage,
  flattenReport,
  normalizeAnalyzeReport,
  normalizeBriefing,
  normalizeHistoryList,
  normalizeModelOptions,
  normalizeStrategy,
  normalizeValidation,
  parseChatChunk,
  sortModelOptions,
  summarizeToolCall,
  summarizeToolResult,
  type CopilotMessage,
} from './copilot';

function pendingAssistant(): CopilotMessage {
  return createPendingAssistant();
}

describe('parseChatChunk', () => {
  it('parses a content chunk with attribution', () => {
    const chunk = parseChatChunk({ type: 'content', delta: 'hello', provider_used: 'openrouter', model_used: 'x-free' });
    expect(chunk).toMatchObject({ type: 'content', delta: 'hello', provider_used: 'openrouter', model_used: 'x-free' });
  });

  it('rejects unknown types and non-objects', () => {
    expect(parseChatChunk({ type: 'bogus', delta: 'x' })).toBeNull();
    expect(parseChatChunk(null)).toBeNull();
    expect(parseChatChunk('data: {}')).toBeNull();
    expect(parseChatChunk({})).toBeNull();
  });

  it('defaults missing string fields instead of crashing', () => {
    expect(parseChatChunk({ type: 'done' })).toMatchObject({ delta: '', finish_reason: null });
    expect(parseChatChunk({ type: 'error' })).toMatchObject({ delta: '' });
  });
});

describe('applyChatChunk reducer', () => {
  it('appends content deltas token by token', () => {
    let msg = pendingAssistant();
    msg = applyChatChunk(msg, { type: 'content', delta: 'Hel', reasoning_delta: '' } as never);
    msg = applyChatChunk(msg, { type: 'content', delta: 'lo', reasoning_delta: '' } as never);
    expect(msg.content).toBe('Hello');
    expect(msg.pending).toBe(true);
  });

  it('accumulates reasoning separately and closes on done', () => {
    let msg = pendingAssistant();
    msg = applyChatChunk(msg, { type: 'reasoning', delta: '', reasoning_delta: 'thinking…' } as never);
    expect(msg.reasoning).toBe('thinking…');
    expect(msg.content).toBe('');
    msg = applyChatChunk(msg, { type: 'done', delta: '', reasoning_delta: '' } as never);
    expect(msg.pending).toBe(false);
  });

  it('records tool calls/results as notes and surfaces chunk errors', () => {
    let msg = pendingAssistant();
    msg = applyChatChunk(
      msg,
      { type: 'tool_call', delta: '', reasoning_delta: '', tool_call: { function: { name: 'get_market_quote' } } } as never,
    );
    msg = applyChatChunk(
      msg,
      { type: 'tool_result', delta: '', reasoning_delta: '', tool_result: { name: 'get_market_quote', result: { ltp: 1 } } } as never,
    );
    expect(msg.toolNotes).toHaveLength(2);
    expect(msg.toolNotes[0]).toContain('get_market_quote');
    msg = applyChatChunk(msg, { type: 'error', delta: 'boom', reasoning_delta: '' } as never);
    expect(msg.pending).toBe(false);
    expect(msg.error).toBe('boom');
  });

  it('tracks provider/model attribution from any chunk', () => {
    const msg = applyChatChunk(pendingAssistant(), {
      type: 'content',
      delta: 'x',
      reasoning_delta: '',
      provider_used: 'gemini',
      model_used: 'gemini-2.5-flash',
    } as never);
    expect(msg.provider).toBe('gemini');
    expect(msg.model).toBe('gemini-2.5-flash');
  });
});

describe('buildChatMessages', () => {
  it('maps history to backend roles and appends the new turn', () => {
    const history = [createUserMessage('hi'), { ...pendingAssistant(), content: 'hello', pending: false }];
    const out = buildChatMessages(history, 'again');
    expect(out).toEqual([
      { role: 'user', content: 'hi' },
      { role: 'assistant', content: 'hello' },
      { role: 'user', content: 'again' },
    ]);
  });

  it('drops errored turns and caps at 20', () => {
    const history = Array.from({ length: 30 }, (_, i) => createUserMessage(`m${i}`));
    const out = buildChatMessages(history, 'last');
    expect(out).toHaveLength(20);
    expect(out[out.length - 1]).toEqual({ role: 'user', content: 'last' });
  });
});

describe('summarizeToolCall / summarizeToolResult', () => {
  it('never throws on malformed payloads', () => {
    expect(summarizeToolCall(null)).toBeTruthy();
    expect(summarizeToolCall({})).toContain('unknown-tool');
    expect(summarizeToolResult({ name: 'q', result: { error: 'bad' } })).toContain('failed');
    expect(summarizeToolResult(undefined)).toBeTruthy();
  });
});

describe('copilotErrorHint', () => {
  it('points at /settings when no provider is configured', () => {
    const hint = copilotErrorHint('No AI provider configured for chat');
    expect(hint.kind).toBe('no-provider');
    expect(hint.hint).toContain('/settings');
  });

  it('suggests free models when paid models are disabled', () => {
    const hint = copilotErrorHint('Paid models are disabled for this key');
    expect(hint.kind).toBe('paid-disabled');
    expect(hint.hint).toContain('FREE');
  });

  it('passes other errors through honestly', () => {
    const hint = copilotErrorHint('timeout after 180s');
    expect(hint.kind).toBe('generic');
    expect(hint.hint).toBe('timeout after 180s');
  });
});

describe('normalizeBriefing', () => {
  it('extracts levels and playbook from the live envelope shape', () => {
    const card = normalizeBriefing({
      symbol: 'NIFTY',
      session_type: 'PRE_MARKET',
      executive_summary: 'enters session',
      key_levels_to_watch: { spot: 23346.4, pivot: 23315.45 },
      options_pin_and_pivots: 'pins',
      fii_dii_implication: 'balanced',
      actionable_playbook: ['defend longs'],
      provider_used: 'droid_quant_engine',
    });
    expect(card?.levels).toHaveLength(2);
    expect(card?.playbook).toEqual(['defend longs']);
    expect(card?.symbol).toBe('NIFTY');
  });

  it('returns null for non-objects and tolerates missing keys', () => {
    expect(normalizeBriefing(null)).toBeNull();
    expect(normalizeBriefing({})?.levels).toEqual([]);
  });
});

describe('normalizeAnalyzeReport / normalizeHistoryList / normalizeModelOptions', () => {
  it('splits report sections and keeps bias/confidence', () => {
    const report = normalizeAnalyzeReport({
      symbol: 'BANKNIFTY',
      market_bias: 'BULLISH',
      confidence: 82,
      executive_summary: 'summary',
      options_interpretation: 'oi',
      provider_used: 'openrouter',
    });
    expect(report?.bias).toBe('BULLISH');
    expect(report?.sections.map((s) => s.label)).toContain('Options interpretation');
  });

  it('keeps only rows with ids', () => {
    const rows = normalizeHistoryList([{ id: 'a', symbol: 'NIFTY' }, null, { symbol: 'X' }]);
    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe('a');
  });

  it('keeps only models with ids and sorts free first', () => {
    const options = sortModelOptions(
      normalizeModelOptions([{ id: 'paid/x', name: 'Paid', is_free: false }, { id: 'free/y', name: 'Free', is_free: true }, {}]),
    );
    expect(options.map((o) => o.id)).toEqual(['free/y', 'paid/x']);
  });
});

describe('normalizeValidation / normalizeStrategy / flattenReport / biasTone', () => {
  it('parses a validation verdict', () => {
    const v = normalizeValidation({ decision: 'CONFIRM', score: 78, executive_verdict: 'ok', invalidation_conditions: ['a'] });
    expect(v?.decision).toBe('CONFIRM');
    expect(v?.invalidations).toEqual(['a']);
    expect(normalizeValidation('nope')).toBeNull();
  });

  it('parses a strategy plan with legs', () => {
    const s = normalizeStrategy({
      strategy_name: 'Iron Condor',
      legs: [{ strike: 25000, option_type: 'CE', action: 'SELL', estimated_premium: 42 }],
      breakevens: [1, 2],
    });
    expect(s?.legs).toHaveLength(1);
    expect(s?.breakevens).toHaveLength(2);
    expect(normalizeStrategy([])).toBeNull();
  });

  it('flattens unknown payloads with a cap and never throws', () => {
    const rows = flattenReport({ a: 1, nested: { b: 'x' }, list: ['p', 'q'] }, 2);
    expect(rows.length).toBeLessThanOrEqual(2);
    expect(flattenReport(null)).toEqual([]);
  });

  it('maps decisions to tones', () => {
    expect(biasTone('BULLISH')).toBe('bull');
    expect(biasTone('REJECT')).toBe('bear');
    expect(biasTone('WATCH')).toBe('warn');
    expect(biasTone('???')).toBe('neut');
  });
});
