'use client';

import React, { useCallback, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { useExecutionGuard } from '@/hooks/useExecutionGuard';
import { api } from '@/lib/api';
import { toNumber, pickFirst } from '@/lib/coerce';
import { errorMessage } from '@/lib/errors';
import { Card } from '@/components/ui/card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

type Side = 'BUY' | 'SELL';
type ExecutionMode = 'ATOMIC' | 'SEQUENTIAL_LEGGED';
type LegRiskPolicy = 'HOLD_AND_ALERT' | 'CANCEL_REMAINING';

interface BasketLeg {
  id: string;
  symbol: string;
  side: Side;
  quantity: number;
}

interface QuoteState {
  ltp: number | null;
  timestampMs: number | null;
  status: string | null;
  error: string | null;
  loading: boolean;
}

interface BasketPayload {
  orders: Array<{ symbol: string; side: Side; quantity: number; price: number; order_type: 'LIMIT' }>;
  execution_mode: ExecutionMode;
  leg_risk_policy: LegRiskPolicy;
}

interface ReviewedLeg {
  symbol: string;
  side: Side;
  quantity: number;
  price: number;
  quoteAgeSec: number | null;
}

interface BasketReview {
  payload: BasketPayload;
  legs: ReviewedLeg[];
}

const EMPTY_QUOTE: QuoteState = {
  ltp: null,
  timestampMs: null,
  status: null,
  error: null,
  loading: false,
};

const BLOCKED_FEED_STATES = new Set(['STALE', 'DOWN', 'ERROR', 'INVALID', 'DISCONNECTED', 'OFFLINE']);

const quoteKey = (symbol: string): string => symbol.trim().toUpperCase();

type LegCheck =
  | { ok: true; price: number; ageSec: number | null; feedState: string }
  | { ok: false; reason: string };

export const BasketOrderBuilder: React.FC = () => {
  const [legs, setLegs] = useState<BasketLeg[]>([]);
  const [execMode, setExecMode] = useState<ExecutionMode>('ATOMIC');
  const [legRiskPolicy, setLegRiskPolicy] = useState<LegRiskPolicy>('HOLD_AND_ALERT');
  const [quotes, setQuotes] = useState<Record<string, QuoteState>>({});
  const [review, setReview] = useState<BasketReview | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const guard = useExecutionGuard();
  const basketAction = useAsyncAction({
    guard,
    errorFallback: 'Unknown basket error',
    busyMessage: 'A basket dispatch is already in progress. Wait for it to finish.',
  });
  const legSeq = useRef(0);

  const nextLegId = () => {
    legSeq.current += 1;
    return `leg-${legSeq.current}`;
  };

  const refreshQuotes = useCallback(async (symbols: string[]) => {
    const unique = Array.from(new Set(symbols.map(quoteKey).filter(Boolean)));
    await Promise.all(
      unique.map(async (symbol) => {
        setQuotes((prev) => ({
          ...prev,
          [symbol]: { ...(prev[symbol] ?? EMPTY_QUOTE), loading: true },
        }));
        try {
          const res = await api.getQuote(symbol);
          const data = res?.data;
          if (!data) throw new Error('Quote payload missing.');
          const timestampMs = new Date(data.timestamp).getTime();
          const status = typeof data.status === 'string' ? data.status : null;
          setQuotes((prev) => ({
            ...prev,
            [symbol]: {
              ltp: toNumber(data.ltp),
              timestampMs: Number.isFinite(timestampMs) ? timestampMs : null,
              status,
              error: status && BLOCKED_FEED_STATES.has(status) ? `feed ${status}` : null,
              loading: false,
            },
          }));
        } catch (err) {
          setQuotes((prev) => ({
            ...prev,
            [symbol]: {
              ltp: null,
              timestampMs: null,
              status: null,
              error: errorMessage(err, 'Unknown basket error'),
              loading: false,
            },
          }));
        }
      }),
    );
  }, []);

  usePolling(
    () => refreshQuotes(legs.map((leg) => leg.symbol)),
    5000,
    legs.length > 0,
  );

  const checkLeg = (leg: BasketLeg): LegCheck => {
    const key = quoteKey(leg.symbol);
    if (!key) return { ok: false, reason: 'a leg has an empty symbol' };
    if (!Number.isFinite(leg.quantity) || leg.quantity <= 0) {
      return { ok: false, reason: `${key}: quantity must be a positive number` };
    }
    const quote = quotes[key];
    if (!quote) return { ok: false, reason: `${key}: no live quote loaded yet` };
    if (quote.error) return { ok: false, reason: `${key}: ${quote.error}` };
    if (quote.ltp === null) return { ok: false, reason: `${key}: quote has no LTP` };
    if (quote.status !== 'LIVE') {
      return { ok: false, reason: `${key}: feed ${quote.status ?? 'UNKNOWN'} — execution blocked` };
    }
    const freshness = guard.checkQuoteFreshness(quote.timestampMs);
    if (freshness.isStale) {
      return {
        ok: false,
        reason: `${key}: ${
          freshness.ageSec === null ? 'quote timestamp missing' : `quote stale (${freshness.ageSec}s old)`
        }`,
      };
    }
    return { ok: true, price: quote.ltp, ageSec: freshness.ageSec, feedState: quote.status };
  };

  const addLeg = () => {
    setLegs((prev) => [...prev, { id: nextLegId(), symbol: '', side: 'BUY', quantity: 0 }]);
    setSuccess(null);
  };

  const removeLeg = (id: string) => {
    setLegs((prev) => prev.filter((leg) => leg.id !== id));
    setSuccess(null);
  };

  const updateLeg = (id: string, patch: Partial<Omit<BasketLeg, 'id'>>) => {
    setLegs((prev) => prev.map((leg) => (leg.id === id ? { ...leg, ...patch } : leg)));
    setSuccess(null);
  };

  const handleReviewBasket = () => {
    setActionError(null);
    setSuccess(null);
    if (legs.length === 0) {
      setActionError('Basket blocked: add at least one leg.');
      return;
    }

    const blocked: string[] = [];
    const reviewedLegs: ReviewedLeg[] = [];
    const orders: BasketPayload['orders'] = [];

    legs.forEach((leg) => {
      const check = checkLeg(leg);
      if (!check.ok) {
        blocked.push(check.reason);
        return;
      }
      orders.push({
        symbol: quoteKey(leg.symbol),
        side: leg.side,
        quantity: leg.quantity,
        price: check.price,
        order_type: 'LIMIT',
      });
      reviewedLegs.push({
        symbol: quoteKey(leg.symbol),
        side: leg.side,
        quantity: leg.quantity,
        price: check.price,
        quoteAgeSec: check.ageSec,
      });
    });

    if (blocked.length > 0) {
      setActionError(`Basket blocked — ${blocked.join(' · ')}`);
      return;
    }

    setReview({
      payload: { orders, execution_mode: execMode, leg_risk_policy: legRiskPolicy },
      legs: reviewedLegs,
    });
  };

  const handleExecuteBasket = async () => {
    const reviewed = review;
    if (!reviewed) return;
    setActionError(null);
    setSuccess(null);

    const stale = reviewed.legs
      .map((leg) => {
        const check = checkLeg({ id: 'review', ...leg });
        return check.ok ? null : check.reason;
      })
      .filter((reason): reason is string => reason !== null);
    if (stale.length > 0) {
      throw new Error(
        `Quotes changed while confirming — nothing was sent. Blocked: ${stale.join(' · ')}. Refresh and review again.`,
      );
    }

    const outcome = await basketAction.run(async () => {
      const res = await api.createAlgoBasket(reviewed.payload);
      const data = res?.data;
      if (!data) throw new Error('Basket endpoint returned no result.');
      const statusRaw = typeof data.status === 'string' ? data.status.toUpperCase() : null;
      if (statusRaw && ['REJECTED', 'FAILED', 'ERROR'].includes(statusRaw)) {
        const reason = typeof data.reason === 'string' ? `: ${data.reason}` : '';
        throw new Error(`Basket rejected by the engine (${statusRaw})${reason}.`);
      }
      return {
        accepted:
          toNumber(pickFirst(data.accepted, data.orders_accepted, data.order_count)) ??
          reviewed.payload.orders.length,
        status: statusRaw,
      };
    });

    if (!outcome.ok) {
      setActionError(outcome.message);
      throw new Error(outcome.message);
    }

    setSuccess(
      `Basket dispatched${outcome.value.status ? ` (${outcome.value.status})` : ''} — ${
        outcome.value.accepted
      } leg(s) accepted by the engine.`,
    );
  };

  return (
    <>
      <Card
        title="MULTI-LEG BASKET ORDER BUILDER"
        subtitle="Complex option spreads with atomic legging safety"
        headerAction={
          <button
            type="button"
            onClick={addLeg}
            className="px-2.5 py-1 rounded bg-muted hover:bg-muted-strong border border-border text-primary font-mono text-xs font-semibold"
          >
            + Add Leg
          </button>
        }
      >
        <div className="space-y-4 font-mono text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 bg-surface-subtle rounded-lg border border-border">
            <div>
              <label className="text-ink-2 block mb-1 text-[11px]" htmlFor="basket-exec-mode">
                EXECUTION ATOMICITY
              </label>
              <select
                id="basket-exec-mode"
                value={execMode}
                onChange={(e) => {
                  setExecMode(e.target.value as ExecutionMode);
                  setSuccess(null);
                }}
                className="input w-full"
              >
                <option value="ATOMIC">ATOMIC (All-or-None Fill)</option>
                <option value="SEQUENTIAL_LEGGED">SEQUENTIAL LEGGED</option>
              </select>
            </div>

            <div>
              <label className="text-ink-2 block mb-1 text-[11px]" htmlFor="basket-leg-risk">
                LEG RISK POLICY
              </label>
              <select
                id="basket-leg-risk"
                value={legRiskPolicy}
                onChange={(e) => {
                  setLegRiskPolicy(e.target.value as LegRiskPolicy);
                  setSuccess(null);
                }}
                className="input w-full"
              >
                <option value="HOLD_AND_ALERT">HOLD AND ALERT ON PARTIAL</option>
                <option value="CANCEL_REMAINING">CANCEL REMAINING LEGS</option>
              </select>
            </div>
          </div>

          <div className="space-y-2">
            {legs.length === 0 ? (
              <div className="p-3 rounded bg-surface-subtle border border-border text-ink-3 text-center">
                No legs yet — add a leg and it will be priced from live quotes.
              </div>
            ) : (
              legs.map((leg, idx) => {
                const key = quoteKey(leg.symbol);
                const quote = key ? quotes[key] : undefined;
                const check = checkLeg(leg);

                return (
                  <div
                    key={leg.id}
                    className="p-2.5 rounded bg-surface-subtle border border-border flex flex-wrap items-center gap-2"
                  >
                    <span className="text-ink-3 font-bold">#{idx + 1}</span>

                    <select
                      value={leg.side}
                      aria-label={`Leg ${idx + 1} side`}
                      onChange={(e) => updateLeg(leg.id, { side: e.target.value as Side })}
                      className={`px-2 py-1 rounded font-bold border ${
                        leg.side === 'BUY'
                          ? 'bg-up-wash text-up-strong border-up-line'
                          : 'bg-down-wash text-down-strong border-down-line'
                      }`}
                    >
                      <option value="BUY">BUY</option>
                      <option value="SELL">SELL</option>
                    </select>

                    <input
                      type="text"
                      value={leg.symbol}
                      aria-label={`Leg ${idx + 1} symbol`}
                      placeholder="e.g. NIFTY 24350 CE"
                      onChange={(e) => updateLeg(leg.id, { symbol: e.target.value })}
                      onBlur={() => {
                        if (key) void refreshQuotes([key]);
                      }}
                      className="input flex-1 min-w-[140px]"
                    />

                    <div className="flex items-center gap-1">
                      <span className="text-ink-3">Qty:</span>
                      <input
                        type="number"
                        value={leg.quantity}
                        aria-label={`Leg ${idx + 1} quantity`}
                        onChange={(e) => updateLeg(leg.id, { quantity: Number(e.target.value) })}
                        className="input w-16 num"
                      />
                    </div>

                    <div className="flex items-center gap-1">
                      <span className="text-ink-3">Px:</span>
                      {check.ok ? (
                        <span className="text-ink font-semibold">
                          ₹{check.price.toLocaleString('en-IN')}
                          <span className="text-[10px] text-ink-3 ml-1">
                            {check.ageSec === null ? 'age unknown' : `${check.ageSec}s`} · {check.feedState}
                          </span>
                        </span>
                      ) : (
                        <span className="text-down-strong text-[11px]" title={check.reason}>
                          {quote?.loading && !quote?.error ? 'loading…' : 'unavailable'}
                        </span>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => removeLeg(leg.id)}
                      aria-label={`Remove leg ${idx + 1}`}
                      className="text-ink-4 hover:text-down-strong p-1 font-bold"
                    >
                      ✕
                    </button>
                  </div>
                );
              })
            )}
          </div>

          {actionError && (
            <div
              role="alert"
              className="rounded border border-down-line bg-down-wash px-2.5 py-1.5 text-down-strong"
            >
              {actionError}
            </div>
          )}

          {basketAction.lastRejectionReason === 'busy' && !actionError && (
            <div className="rounded border border-warn-line bg-warn-wash px-2.5 py-1.5 text-warn-strong">
              A previous basket action is still in progress — the duplicate click was ignored.
            </div>
          )}

          {success && (
            <div
              role="status"
              className="rounded border border-up-line bg-up-wash px-2.5 py-1.5 text-up-strong text-center"
            >
              {success}
            </div>
          )}

          <button
            type="button"
            onClick={handleReviewBasket}
            disabled={basketAction.isPending || legs.length === 0}
            className="w-full py-2.5 rounded-lg bg-primary hover:bg-accent-strong text-white font-bold tracking-wider shadow-sm transition-all disabled:opacity-40"
          >
            {basketAction.isPending ? 'Dispatching Basket…' : 'REVIEW MULTI-LEG BASKET →'}
          </button>
        </div>
      </Card>

      <ConfirmDialog
        isOpen={review !== null}
        onClose={() => setReview(null)}
        onConfirm={handleExecuteBasket}
        title="CONFIRM MULTI-LEG BASKET"
        message={
          review ? (
            <div className="space-y-3 font-mono text-xs">
              <p>
                Send this {review.payload.orders.length}-leg basket priced from live quotes? Every leg
                must still be on a LIVE feed when you confirm.
              </p>

              <dl className="rounded border border-border bg-surface-subtle p-2.5 space-y-1">
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Execution</dt>
                  <dd className="font-semibold text-ink">{review.payload.execution_mode}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Leg risk policy</dt>
                  <dd className="text-ink-2">{review.payload.leg_risk_policy}</dd>
                </div>
                {review.legs.map((leg) => (
                  <div key={`${leg.symbol}-${leg.side}`} className="flex justify-between gap-3">
                    <dt className="text-ink-3">
                      {leg.side} {leg.symbol}
                    </dt>
                    <dd className="text-ink-2">
                      {leg.quantity} qty @ ₹{leg.price.toLocaleString('en-IN')} · quote{' '}
                      {leg.quoteAgeSec === null ? 'age unknown' : `${leg.quoteAgeSec}s old`}
                    </dd>
                  </div>
                ))}
              </dl>

              <div>
                <div className="text-ink-3 mb-1">Exact request payload</div>
                <pre className="overflow-x-auto rounded border border-border bg-surface-subtle p-2.5 text-[10px] leading-relaxed text-ink-2">
                  {JSON.stringify(review.payload, null, 2)}
                </pre>
              </div>
            </div>
          ) : null
        }
        confirmLabel="CONFIRM & SEND BASKET"
        destructive={true}
      />
    </>
  );
};
