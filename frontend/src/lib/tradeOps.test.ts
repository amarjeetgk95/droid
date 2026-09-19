import { describe, expect, it } from 'vitest';
import {
  buildSizingPayload,
  isOrderCancellable,
  modeBadgeClass,
  normalizeTradeMode,
  orderStatusTone,
  summarizeDetails,
  toAiModelRow,
  toDisplayEntries,
  toSizingPreview,
  toStrategyRow,
  toTradeAccount,
  toTradeAuditRow,
  toTradeExposure,
  toTradeOrder,
  toTradePosition,
} from './tradeOps';

describe('normalizeTradeMode', () => {
  it('accepts OFF/PAPER/LIVE case-insensitively', () => {
    expect(normalizeTradeMode('paper')).toBe('PAPER');
    expect(normalizeTradeMode(' LIVE ')).toBe('LIVE');
    expect(normalizeTradeMode('off')).toBe('OFF');
  });

  it('maps anything else to UNKNOWN', () => {
    expect(normalizeTradeMode('OBSERVE')).toBe('UNKNOWN');
    expect(normalizeTradeMode(null)).toBe('UNKNOWN');
    expect(normalizeTradeMode(42)).toBe('UNKNOWN');
  });

  it('maps modes to badge tones', () => {
    expect(modeBadgeClass('LIVE')).toBe('b-bear');
    expect(modeBadgeClass('PAPER')).toBe('b-bull');
    expect(modeBadgeClass('OFF')).toBe('b-neut');
    expect(modeBadgeClass('UNKNOWN')).toBe('b-warn');
  });
});

describe('toTradeAccount', () => {
  it('parses the REST /account shape', () => {
    const account = toTradeAccount({
      account_id: 'a1',
      mode: 'PAPER',
      is_active: true,
      capital: { investment_limit: '3000', max_capital_per_trade: '1000', max_daily_loss: '500' },
      kill_switch: { is_killed: false, kill_level: 'NONE' },
      consent_ok: true,
    });
    expect(account?.mode).toBe('PAPER');
    expect(account?.investmentLimit).toBe(3000);
    expect(account?.maxCapitalPerTrade).toBe(1000);
    expect(account?.available).toBeNull();
    expect(account?.killed).toBe(false);
    expect(account?.consentOk).toBe(true);
    expect(account?.unavailable).toBe(false);
  });

  it('parses the stream get_account_detail shape', () => {
    const account = toTradeAccount({
      account_id: 'a2',
      mode: 'LIVE',
      is_active: true,
      display_name: 'Primary',
      capital: {
        investment_limit: '50000',
        available: '12000.5',
        reserved: '3000',
        deployed: '35000',
        daily_loss: '100',
        daily_loss_limit: '2000',
        is_breached: false,
      },
      kill_switch: { is_killed: false, kill_level: 'NONE' },
      consent: { acknowledged: true },
    });
    expect(account?.mode).toBe('LIVE');
    expect(account?.available).toBe(12000.5);
    expect(account?.deployed).toBe(35000);
    expect(account?.breached).toBe(false);
    expect(account?.displayName).toBe('Primary');
  });

  it('surfaces the fail-closed unavailable flag', () => {
    const account = toTradeAccount({
      account_id: 'a3',
      mode: 'OFF',
      unavailable: true,
      reason: 'NO_DB_SESSION',
    });
    expect(account?.unavailable).toBe(true);
    expect(account?.unavailableReason).toBe('NO_DB_SESSION');
    expect(account?.investmentLimit).toBeNull();
  });

  it('returns null for non-objects', () => {
    expect(toTradeAccount(null)).toBeNull();
    expect(toTradeAccount([1])).toBeNull();
  });
});

describe('toTradeExposure', () => {
  it('parses greeks and sorts slices desc', () => {
    const exposure = toTradeExposure({
      gross_exposure: '10000',
      net_exposure: '4000',
      long_exposure: '7000',
      short_exposure: '3000',
      portfolio_delta: '1.5',
      portfolio_gamma: '0.2',
      portfolio_theta: '-3',
      portfolio_vega: '0.8',
      by_underlying: { NIFTY: '7000', BANKNIFTY: '3000' },
      by_strategy: { ORB: '10000' },
    });
    expect(exposure?.gross).toBe(10000);
    expect(exposure?.delta).toBe(1.5);
    expect(exposure?.byUnderlying[0]).toEqual({ label: 'NIFTY', value: 7000 });
    expect(exposure?.byStrategy).toHaveLength(1);
  });

  it('tolerates missing legs', () => {
    expect(toTradeExposure({})).not.toBeNull();
    expect(toTradeExposure(null)).toBeNull();
  });
});

describe('orders', () => {
  it('parses REST string-numeric rows', () => {
    const order = toTradeOrder({
      client_order_id: 'c1',
      symbol: 'NIFTY25SEP25300CE',
      side: 'BUY',
      quantity: 50,
      price: '120.5',
      order_type: 'LIMIT',
      status: 'SUBMITTED',
      fill_price: null,
      created_at: '2026-09-18T07:00:00+00:00',
      is_paper: true,
    });
    expect(order?.price).toBe(120.5);
    expect(order?.status).toBe('SUBMITTED');
    expect(order?.createdMs).toBeGreaterThan(0);
  });

  it('rejects rows without an id', () => {
    expect(toTradeOrder({ symbol: 'X' })).toBeNull();
  });

  it('tones statuses', () => {
    expect(orderStatusTone('FILLED')).toBe('bull');
    expect(orderStatusTone('CANCELLED')).toBe('bear');
    expect(orderStatusTone('REJECTED')).toBe('bear');
    expect(orderStatusTone('SUBMITTED')).toBe('info');
    expect(orderStatusTone('PARTIALLY_FILLED')).toBe('warn');
    expect(orderStatusTone('WEIRD')).toBe('neut');
  });

  it('gates cancellation to working states only', () => {
    expect(isOrderCancellable('SUBMITTED')).toBe(true);
    expect(isOrderCancellable('CREATED')).toBe(true);
    expect(isOrderCancellable('RISK_APPROVED')).toBe(true);
    expect(isOrderCancellable('FILLED')).toBe(false);
    expect(isOrderCancellable('PARTIALLY_FILLED')).toBe(false);
    expect(isOrderCancellable('CANCELLED')).toBe(false);
    expect(isOrderCancellable(null)).toBe(false);
  });
});

describe('toTradePosition', () => {
  it('parses REST string-numeric rows and the AlgoPosition shape', () => {
    const rest = toTradePosition({
      position_id: 'p1',
      symbol: 'NIFTY25SEP25300CE',
      underlying: 'NIFTY',
      side: 'LONG',
      quantity: 50,
      average_entry: '118.2',
      current_price: '125.0',
      unrealized_pnl: '340',
      is_open: true,
      strategy_id: 'ORB',
    });
    expect(rest?.avgEntry).toBe(118.2);
    expect(rest?.unrealized).toBe(340);
    expect(rest?.isOpen).toBe(true);

    const iface = toTradePosition({
      position_id: 'p2',
      symbol: 'BANKNIFTY',
      quantity: -25,
      average_price: 200,
    });
    expect(iface?.avgEntry).toBe(200);
    expect(iface?.isOpen).toBeNull();
  });
});

describe('toTradeAuditRow', () => {
  it('parses audit rows and shortens ids', () => {
    const row = toTradeAuditRow({
      event_type: 'ORDER_CANCELLED',
      timestamp: '2026-09-18T07:00:00+00:00',
      symbol: 'NIFTY25SEP25300CE',
      client_order_id: '12345678-abcdef',
      details: { reason: 'operator' },
    });
    expect(row?.eventType).toBe('ORDER_CANCELLED');
    expect(row?.clientOrderId).toBe('12345678…');
    expect(row?.detail).toBe('{"reason":"operator"}');
  });

  it('returns null without an event type', () => {
    expect(toTradeAuditRow({ symbol: 'X' })).toBeNull();
  });
});

describe('summarizeDetails', () => {
  it('truncates long strings', () => {
    expect(summarizeDetails('x'.repeat(200))?.length).toBeLessThanOrEqual(161);
    expect(summarizeDetails(null)).toBeNull();
    expect(summarizeDetails({})).toBe('{}');
  });
});

describe('sizing', () => {
  it('parses the preview response', () => {
    const preview = toSizingPreview({
      data: { quantity: 40, notional: '4800', risk_per_unit: '12.5', reason: 'ok', capped_by: null },
    });
    expect(preview?.quantity).toBe(40);
    expect(preview?.notional).toBe(4800);
    expect(preview?.riskPerUnit).toBe(12.5);
  });

  it('requires a positive entry price', () => {
    const base = {
      entryPrice: '120',
      stopPrice: '110',
      riskBudget: '500',
      lotSize: '1',
      contractMultiplier: '1',
      maxCapitalPerTrade: '',
      maxPositionSize: '',
      availableCapital: '3000',
    };
    const ok = buildSizingPayload(base);
    expect(ok.ok).toBe(true);
    if (ok.ok) expect(ok.payload.entry_price).toBe(120);

    expect(buildSizingPayload({ ...base, entryPrice: '' }).ok).toBe(false);
    expect(buildSizingPayload({ ...base, entryPrice: '-5' }).ok).toBe(false);
    expect(buildSizingPayload({ ...base, stopPrice: 'abc' }).ok).toBe(false);
  });
});

describe('compact readouts', () => {
  it('flattens records defensively', () => {
    const entries = toDisplayEntries({ drift_state: 'NORMAL', confidence_shift: 0.02, ok: true, missing: null });
    expect(entries).toContainEqual({ label: 'drift state', value: 'NORMAL' });
    expect(entries).toContainEqual({ label: 'confidence shift', value: '0.02' });
    expect(entries).toContainEqual({ label: 'ok', value: 'yes' });
    expect(entries.find((e) => e.label === 'missing')).toBeUndefined();
    expect(toDisplayEntries(null)).toEqual([]);
  });

  it('parses strategy and model rows', () => {
    expect(
      toStrategyRow({ strategy_id: 's1', name: 'ORB', lifecycle_stage: 'PAPER', is_active: true })?.name,
    ).toBe('ORB');
    expect(toStrategyRow({})).toBeNull();
    expect(
      toAiModelRow({ key: 'k', provider: 'x', status: 'CANARY', canary_pct: '5' })?.canaryPct,
    ).toBe(5);
    expect(toAiModelRow({})).toBeNull();
  });
});
