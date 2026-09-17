'use client';

import React, { useState } from 'react';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { api } from '@/lib/api';
import { toNumber, pickFirst } from '@/lib/coerce';
import { lotSizeFor } from '@/lib/paperLots';
import { Card } from '../shared/Card';

interface SizingResult {
  lots: number;
  maxLoss: number | null;
  derived: boolean;
}

export const SizingPreview: React.FC = () => {
  const [symbol, setSymbol] = useState('NIFTY');
  const [riskAmount, setRiskAmount] = useState(5000);
  const [stopDistance, setStopDistance] = useState(40);
  const [result, setResult] = useState<SizingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const action = useAsyncAction({
    errorFallback: 'Unknown sizing error',
    busyMessage: 'A sizing request is already in progress. Wait for it to finish.',
  });

  const resetResult = () => {
    setResult(null);
    setError(null);
  };

  const calculateSizing = async () => {
    resetResult();
    if (!Number.isFinite(riskAmount) || riskAmount <= 0) {
      setError('Risk budget must be a positive number.');
      return;
    }
    if (!Number.isFinite(stopDistance) || stopDistance <= 0) {
      setError('Stop distance must be a positive number.');
      return;
    }

    const outcome = await action.run(async () => {
      const res = await api.previewAlgoSizing({
        symbol,
        risk_amount: riskAmount,
        stop_distance: stopDistance,
      });
      const data = res?.data as Record<string, unknown> | undefined;
      if (!data) throw new Error('Sizing engine returned no data.');

      const engineLots = toNumber(pickFirst(data.lots, data.recommended_lots));
      const engineMaxLoss = toNumber(pickFirst(data.max_loss, data.worst_case_loss));
      const marginPerLot = toNumber(
        pickFirst(data.margin_per_lot, data.required_margin, data.margin_required),
      );

      let lots = engineLots;
      let derived = false;
      if (lots === null && marginPerLot !== null && marginPerLot > 0) {
        lots = Math.floor(riskAmount / marginPerLot);
        derived = true;
      }
      if (lots === null) {
        throw new Error(
          'Sizing engine returned no lot recommendation and no real margin figure — unavailable rather than fabricated.',
        );
      }

      let maxLoss = engineMaxLoss;
      if (maxLoss === null) {
        maxLoss = lots * stopDistance * lotSizeFor(symbol);
        derived = true;
      }

      setResult({ lots, maxLoss, derived });
      return true;
    });

    if (!outcome.ok) {
      setResult(null);
      setError(outcome.message);
    }
  };

  return (
    <Card
      title="POSITION SIZING & VOLATILITY PREVIEW"
      subtitle="Fractional Kelly & volatility-adjusted risk allocation"
    >
      <div className="space-y-3 font-mono text-xs">
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="text-ink-2 block mb-1" htmlFor="sizing-symbol">
              SYMBOL
            </label>
            <select
              id="sizing-symbol"
              value={symbol}
              onChange={(e) => {
                setSymbol(e.target.value);
                resetResult();
              }}
              className="input w-full"
            >
              <option value="NIFTY">NIFTY</option>
              <option value="BANKNIFTY">BANKNIFTY</option>
              <option value="SENSEX">SENSEX</option>
            </select>
          </div>

          <div>
            <label className="text-ink-2 block mb-1" htmlFor="sizing-risk">
              RISK BUDGET (₹)
            </label>
            <input
              id="sizing-risk"
              type="number"
              value={riskAmount}
              step={500}
              onChange={(e) => {
                setRiskAmount(Number(e.target.value));
                resetResult();
              }}
              className="input w-full num"
            />
          </div>

          <div>
            <label className="text-ink-2 block mb-1" htmlFor="sizing-stop">
              STOP DISTANCE (PTS)
            </label>
            <input
              id="sizing-stop"
              type="number"
              value={stopDistance}
              step={5}
              onChange={(e) => {
                setStopDistance(Number(e.target.value));
                resetResult();
              }}
              className="input w-full num"
            />
          </div>
        </div>

        <button
          type="button"
          onClick={calculateSizing}
          disabled={action.isPending}
          className="w-full py-1.5 rounded bg-muted hover:bg-muted-strong border border-border text-primary font-semibold disabled:opacity-50"
        >
          {action.isPending ? 'Computing…' : 'Compute Volatility-Adjusted Size'}
        </button>

        {error && (
          <div
            role="alert"
            className="rounded border border-down-line bg-down-wash px-2.5 py-1.5 text-down-strong"
          >
            Sizing unavailable: {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-2 p-2.5 rounded bg-surface-subtle border border-border text-center">
          <div>
            <div className="text-[10px] text-ink-3 uppercase">Recommended Sizing</div>
            <div className={`text-sm font-bold mt-0.5 ${result ? 'text-primary' : 'text-ink-3'}`}>
              {result ? `${result.lots} Lots` : '—'}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-ink-3 uppercase">Worst-Case Stop Loss</div>
            <div className={`text-sm font-bold mt-0.5 ${result?.maxLoss != null ? 'text-down-strong' : 'text-ink-3'}`}>
              {result?.maxLoss != null
                ? `₹${result.maxLoss.toLocaleString('en-IN')}`
                : '—'}
            </div>
          </div>
        </div>

        {result?.derived && (
          <div className="text-[10px] text-ink-3">
            Derived from backend-reported margin/premium and the official lot size — no client-side
            fallback values.
          </div>
        )}
      </div>
    </Card>
  );
};
