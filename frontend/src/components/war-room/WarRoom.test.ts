import { describe, it, expect, vi } from 'vitest';
import { parseSignalTime, calcRiskReward, parseAutoExecuted, parseSignalList, toSignalStatus, shouldRefreshSignalsOnEvent, shouldRefreshVerdictOnSignalEvent } from './SignalFeedPanel';
import { calcBiasDrift } from './VerdictPanel';
import { executeEmergencyKill } from '@/lib/api/algo';
import { api } from '@/lib/api';


describe('War Room Data Logic and Formatting', () => {
  it('correctly classifies bullish and bearish direction tokens', () => {
    const isBull = (raw: string) => {
      const u = raw.toUpperCase();
      return u.includes('BULL') || u.includes('UP') || u.includes('LONG');
    };
    const isBear = (raw: string) => {
      const u = raw.toUpperCase();
      return u.includes('BEAR') || u.includes('DOWN') || u.includes('SHORT');
    };

    expect(isBull('BULLISH')).toBe(true);
    expect(isBull('STRONG_BULL')).toBe(true);
    expect(isBull('UPTREND')).toBe(true);
    expect(isBull('BEARISH')).toBe(false);

    expect(isBear('BEARISH')).toBe(true);
    expect(isBear('DOWNTREND')).toBe(true);
    expect(isBear('SHORT_SETUP')).toBe(true);
    expect(isBear('BULLISH')).toBe(false);
  });

  it('normalizes confidence scores whether given as 0..1 or 0..100', () => {
    const normalizeConf = (c: number) => Math.round(c > 1 ? c : c * 100);

    expect(normalizeConf(0.87)).toBe(87);
    expect(normalizeConf(87)).toBe(87);
    expect(normalizeConf(0.925)).toBe(93);
    expect(normalizeConf(64)).toBe(64);
  });

  it('calculates risk-reward ratio correctly without division by zero', () => {
    const calcRR = (entry: number, stopLoss: number, target: number) => {
      const risk = Math.abs(entry - stopLoss);
      const reward = Math.abs(target - entry);
      if (risk === 0) return 1;
      return Number((reward / risk).toFixed(1));
    };

    // 25000 entry, 24950 SL (50 pts risk), 25100 Target (100 pts reward) -> 1:2.0
    expect(calcRR(25000, 24950, 25100)).toBe(2.0);
    // 50 pts risk, 75 pts reward -> 1:1.5
    expect(calcRR(25000, 24950, 25075)).toBe(1.5);
  });

  it('filters signal feeds cleanly by desk type', () => {
    const signals = [
      { id: '1', deskType: 'SCALP' },
      { id: '2', deskType: 'INTRADAY' },
      { id: '3', deskType: 'SWING' },
      { id: '4', deskType: 'SCALP' },
    ];

    const filterSignals = (list: typeof signals, filter: string) => {
      if (filter === 'ALL') return list;
      return list.filter((s) => s.deskType === filter);
    };

    expect(filterSignals(signals, 'ALL')).toHaveLength(4);
    expect(filterSignals(signals, 'SCALP')).toHaveLength(2);
    expect(filterSignals(signals, 'INTRADAY')).toHaveLength(1);
    expect(filterSignals(signals, 'SWING')).toHaveLength(1);
  });

  it('finds and centers ATM strike window for instant options chain rendering', () => {
    const strikes = Array.from({ length: 30 }, (_, i) => ({
      strike: 24000 + i * 50,
      is_atm: 24000 + i * 50 === 25000,
    }));

    const atmIdx = strikes.findIndex((s) => s.is_atm);
    expect(atmIdx).toBe(20); // 24000 + 20*50 = 25000

    const start = Math.max(0, atmIdx - 8);
    const window = strikes.slice(start, start + 17);

    expect(window).toHaveLength(17);
    expect(window.some((s) => s.is_atm)).toBe(true);
  });
});

describe('SignalFeedPanel helpers (regression)', () => {
  it('parseSignalTime prefers timestamp_ms in ms, converts seconds, fails closed', () => {
    const ms = 1757920000000;
    expect(parseSignalTime({ timestamp_ms: ms }, 0)).toBe(ms);
    // seconds-epoch -> ms
    expect(parseSignalTime({ timestamp_ms: 1757920000 }, 0)).toBe(1757920000000);
    // timestamp field (seconds) fallback
    expect(parseSignalTime({ timestamp: 1757920000 }, 1)).toBe(1757920000000);
    // created_at ISO string
    expect(parseSignalTime({ created_at: '2024-01-02T03:04:05.000Z' }, 0)).toBe(
      new Date('2024-01-02T03:04:05.000Z').getTime(),
    );
    // empty object -> null (fail-closed, never invent Date.now())
    expect(parseSignalTime({}, 2)).toBeNull();
  });

  it('parseSignalTime does not blow up on numeric timestamp_ms=0 edge', () => {
    // 0 is a finite number -> converts to 0ms epoch (explicit), not the idx fallback
    expect(parseSignalTime({ timestamp_ms: 0 }, 3)).toBe(0);
  });

  it('calcRiskReward matches spec and guards zero/non-finite, caps extremes', () => {
    expect(calcRiskReward(25000, 24950, 25100)).toBe(2.0);
    expect(calcRiskReward(25000, 24950, 25075)).toBe(1.5);
    expect(calcRiskReward(100, 100, 110)).toBe(1); // risk === 0
    expect(calcRiskReward(NaN, 100, 110)).toBe(1);
    expect(calcRiskReward(100, 100.000001, 200)).toBeLessThanOrEqual(99); // capped
  });

  it('parseAutoExecuted is false by default, true only with real evidence', () => {
    expect(parseAutoExecuted({})).toBe(false);
    expect(parseAutoExecuted({ is_auto_executed: false })).toBe(false);
    expect(parseAutoExecuted({ is_auto_executed: true })).toBe(true);
    expect(parseAutoExecuted({ paper_order_id: 'PO-123' })).toBe(true);
    expect(parseAutoExecuted({ isAutoExecuted: true })).toBe(true);
    // Backend SignalInstance.paper_order is a dict once the engine executed.
    expect(parseAutoExecuted({ paper_order: { order_id: 'PO-1' } })).toBe(true);
    expect(parseAutoExecuted({ paper_order: null })).toBe(false);
  });

  it('parseSignalTime reads the backend created_at_utc field', () => {
    const ms = 1757920000000;
    expect(parseSignalTime({ created_at_utc: ms })).toBe(ms);
    // A created_at ISO string is not misread as epoch seconds by toMsEpoch.
    expect(parseSignalTime({ created_at_utc: '2024-01-02T03:04:05.000Z' })).toBeNull();
    expect(parseSignalTime({ created_at_utc: '2024-01-02T03:04:05.000Z', created_at: '2024-01-02T03:04:05.000Z' })).toBe(
      new Date('2024-01-02T03:04:05.000Z').getTime(),
    );
  });
});

describe('SignalFeedPanel backend SignalInstance mapping', () => {
  const backendRow = (overrides: Record<string, unknown> = {}) => ({
    signal_id: 'SIG-1',
    underlying: 'NIFTY',
    strategy: 'VWAP_SCALP',
    direction: 'LONG_CALL',
    signal_type: 'SCALP',
    is_scalp: true,
    spot_price: 25000,
    entry_min: 24980,
    entry_max: 25020,
    trigger: 25010,
    entry_price: null,
    stop_loss: 24950,
    target_1: 25100,
    target_2: 25150,
    confidence: 82,
    fsm_state: 'CONFIRMED',
    created_at_utc: 1757920000000,
    option_contract: { broker_symbol: 'NSE:NIFTY26SEP25000CE', lot_size: 75 },
    ttl_remaining_seconds: 120,
    data_quality: 'LIVE',
    distance_to_trigger_pts: 12.5,
    ...overrides,
  });

  it('maps option_contract.broker_symbol, fsm_state and the trigger entry fallback', () => {
    const out = parseSignalList([backendRow()], 'NIFTY');
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({
      id: 'SIG-1',
      contract: 'NSE:NIFTY26SEP25000CE',
      entry: 25010, // trigger fallback — entry_price is null pre-fill
      stopLoss: 24950,
      target1: 25100,
      target2: 25150,
      status: 'ACTIVE',
      deskType: 'SCALP',
      direction: 'BUY',
      ttlSeconds: 120,
      distancePts: 12.5,
      dataQuality: 'LIVE',
    });
  });

  it('prefers the executed entry_price over the trigger when present', () => {
    const out = parseSignalList([backendRow({ entry_price: 25005.5 })], 'NIFTY');
    expect(out[0].entry).toBe(25005.5);
  });

  it('maps every backend fsm_state to the feed badge set', () => {
    const statusFor = (fsm: string) => parseSignalList([backendRow({ signal_id: `S-${fsm}`, fsm_state: fsm })], 'NIFTY')[0].status;
    expect(statusFor('DETECTED')).toBe('ACTIVE');
    expect(statusFor('ARMED')).toBe('ACTIVE');
    expect(statusFor('TRIGGERED')).toBe('TRIGGERED');
    expect(statusFor('TARGET_1_HIT')).toBe('TARGET_REACHED');
    expect(statusFor('TARGET_2_HIT')).toBe('TARGET_REACHED');
    expect(statusFor('STOP_LOSS_HIT')).toBe('STOPPED_OUT');
    expect(statusFor('TIME_STOP_HIT')).toBe('EXPIRED');
    expect(statusFor('RUNNER_TIME_STOP_HIT')).toBe('EXPIRED');
    expect(statusFor('INVALIDATED')).toBe('EXPIRED');
  });

  it('toSignalStatus keeps the badge union closed for unknown tokens', () => {
    expect(toSignalStatus('CONFIRMED')).toBe('ACTIVE');
    expect(toSignalStatus(undefined)).toBe('ACTIVE');
    expect(toSignalStatus('NOT_A_STATE')).toBe('ACTIVE');
    expect(toSignalStatus('TRIGGERED')).toBe('TRIGGERED');
  });
});

describe('SignalFeedPanel parseSignalList robustness', () => {
  it('fails closed on malformed or incomplete signal items', () => {
    const rawList = [
      // Missing entry
      { id: '1', stop_loss: 100, target_1: 120, contract: 'NIFTY24000CE', direction: 'BUY', confidence: 80, timestamp_ms: 1000, strategy: 'ORB' },
      // Missing SL
      { id: '2', entry_price: 110, target_1: 120, contract: 'NIFTY24000CE', direction: 'BUY', confidence: 80, timestamp_ms: 1000, strategy: 'ORB' },
      // Missing Target
      { id: '3', entry_price: 110, stop_loss: 100, contract: 'NIFTY24000CE', direction: 'BUY', confidence: 80, timestamp_ms: 1000, strategy: 'ORB' },
      // Missing Timestamp
      { id: '4', entry_price: 110, stop_loss: 100, target_1: 120, contract: 'NIFTY24000CE', direction: 'BUY', confidence: 80, strategy: 'ORB' },
      // Missing Contract
      { id: '5', entry_price: 110, stop_loss: 100, target_1: 120, direction: 'BUY', confidence: 80, timestamp_ms: 1000, strategy: 'ORB' },
      // Valid complete signal
      { id: '6', entry_price: 110, stop_loss: 100, target_1: 120, contract: 'NIFTY24000CE', direction: 'BUY', confidence: 85, timestamp_ms: 1000, strategy: 'ORB' },
    ];

    const result = parseSignalList(rawList, 'NIFTY');
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('6');
    expect(result[0].contract).toBe('NIFTY24000CE');
    expect(result[0].confidence).toBe(85);
  });
});

describe('AlgoControlWidget executeEmergencyKill robustness', () => {
  it('succeeds on first attempt when backend responds OK', async () => {
    const spy = vi.spyOn(api, 'request').mockResolvedValueOnce({ status: 'ok' });
    const attempts: number[] = [];


    const res = await executeEmergencyKill(3, (att) => attempts.push(att));
    expect(res.success).toBe(true);
    expect(attempts).toEqual([1]);
    expect(spy).toHaveBeenCalledWith('/api/v1/algo/kill-switch', expect.objectContaining({ method: 'POST' }));
    spy.mockRestore();
  });

  it('retries on failure and succeeds on subsequent attempt', async () => {
    let callCount = 0;
    const spy = vi.spyOn(api, 'request').mockImplementation(async () => {
      callCount++;
      if (callCount < 2) throw new Error('Temporary gateway timeout');
      return { status: 'ok' };
    });

    const attempts: number[] = [];
    const res = await executeEmergencyKill(3, (att) => attempts.push(att));

    expect(res.success).toBe(true);
    expect(attempts).toEqual([1, 2]);
    expect(callCount).toBe(2);
    spy.mockRestore();
  });

  it('escalates to secondary emergency kill endpoint if primary fails all retries', async () => {
    const spy = vi.spyOn(api, 'request').mockImplementation(async (path: string) => {
      if (path === '/api/v1/algo/kill-switch') {
        throw new Error('Algo service down');
      }
      if (path === '/api/v1/signals/kill-switch') {
        return { active: true };
      }
      throw new Error('Unknown path');
    });

    const res = await executeEmergencyKill(2);
    expect(res.success).toBe(true);
    expect(spy).toHaveBeenCalledWith('/api/v1/signals/kill-switch', expect.objectContaining({ method: 'POST' }));
    spy.mockRestore();
  });
});

describe('Truthful metrics and levels (no synthetic fabrication)', () => {
  it('does not invent synthetic confidence when confidence is missing', () => {
    const rawConf: number | undefined = undefined;
    const confRaw = typeof rawConf === 'number' && Number.isFinite(rawConf) ? rawConf : NaN;
    const confPct = Number.isFinite(confRaw) ? Math.round(confRaw > 1 ? confRaw : confRaw * 100) : null;

    expect(confPct).toBeNull();
  });

  it('leaves pivot levels null when backend does not provide classic pivots', () => {
    const getKeyLevels = (pivots: { r1?: number; r2?: number } | null) =>
      pivots != null ? { r1: pivots.r1 ?? null, r2: pivots.r2 ?? null } : null;

    const keyLevels = getKeyLevels(null);
    // New truthful behavior: does not add spot + 160
    const r2 = keyLevels?.r2 ?? null;
    const r1 = keyLevels?.r1 ?? null;

    expect(r2).toBeNull();
    expect(r1).toBeNull();
  });

});

describe('Realtime SSE event routing (war room)', () => {
  it('refreshes signal list on lifecycle + scanner events, never on telemetry', () => {
    expect(shouldRefreshSignalsOnEvent('signal_created')).toBe(true);
    expect(shouldRefreshSignalsOnEvent('paper_execution')).toBe(true);
    expect(shouldRefreshSignalsOnEvent('scanner_update')).toBe(true);
    expect(shouldRefreshSignalsOnEvent('signal_confirmed')).toBe(true);
    expect(shouldRefreshSignalsOnEvent('fsm_transition')).toBe(true);
    expect(shouldRefreshSignalsOnEvent('FEED_STATUS')).toBe(false);
    expect(shouldRefreshSignalsOnEvent('audit_pnl_update')).toBe(false);
    expect(shouldRefreshSignalsOnEvent('')).toBe(false);
  });

  it('nudges verdict only on P0 lifecycle events (never scanner chatter)', () => {
    expect(shouldRefreshVerdictOnSignalEvent('signal_created')).toBe(true);
    expect(shouldRefreshVerdictOnSignalEvent('signal_confirmed')).toBe(true);
    expect(shouldRefreshVerdictOnSignalEvent('paper_execution')).toBe(true);
    expect(shouldRefreshVerdictOnSignalEvent('signal_outcome')).toBe(true);
    expect(shouldRefreshVerdictOnSignalEvent('scanner_update')).toBe(false);
    expect(shouldRefreshVerdictOnSignalEvent('FEED_STATUS')).toBe(false);
    expect(shouldRefreshVerdictOnSignalEvent('signal_deleted')).toBe(false);
  });
});

describe('Bias drift (liveSpot vs bias snapshot)', () => {
  it('computes signed pts + pct drift', () => {
    const d = calcBiasDrift(25100, 25000);
    expect(d).not.toBeNull();
    expect(d!.pts).toBeCloseTo(100, 6);
    expect(d!.pct).toBeCloseTo(0.4, 6);
    const down = calcBiasDrift(24950, 25000);
    expect(down!.pts).toBeCloseTo(-50, 6);
  });

  it('fails false (null) when either leg is missing or non-finite', () => {
    expect(calcBiasDrift(null, 25000)).toBeNull();
    expect(calcBiasDrift(25100, null)).toBeNull();
    expect(calcBiasDrift(undefined, 25000)).toBeNull();
    expect(calcBiasDrift(NaN, 25000)).toBeNull();
    expect(calcBiasDrift(25100, 0)).toBeNull();
    expect(calcBiasDrift(-5, 25000)).toBeNull();
  });
});

