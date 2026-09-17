'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Badge } from '../shared/Badge';
import { directionToLong, errorMessage, finiteNumber } from './forgeLogic';

export interface ContractSelectionSummary {
  strike: number | null;
  optionType: string | null;
  lotSize: number | null;
  brokerSymbol: string | null;
}

interface ContractSelectorProps {
  underlying: string;
  direction: 'CALL' | 'PUT';
  spot: number | null;
  /** ATM IV as a fraction (null when the chain does not publish one). */
  iv: number | null;
  marketError?: string | null;
  onSelectionChange?: (selection: ContractSelectionSummary | null) => void;
  onSelectContract?: (contract: unknown) => void;
}

interface CandidateView {
  raw: Record<string, unknown>;
  strike: number | null;
  optionType: string | null;
  premium: number | null;
  delta: number | null;
  iv: number | null;
  score: number | null;
  strikeType: string | null;
  acceptable: boolean | null;
  rejectionReasons: string[];
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === 'string' && v.length > 0);
}

function toCandidate(value: unknown): CandidateView | null {
  const rec = asRecord(value);
  if (!rec) return null;
  const greeks = asRecord(rec.greeks);
  return {
    raw: rec,
    strike: finiteNumber(rec.strike),
    optionType: typeof rec.option_type === 'string' ? rec.option_type : null,
    premium: finiteNumber(rec.market_premium),
    delta: finiteNumber(greeks?.delta),
    iv: finiteNumber(rec.live_iv),
    score: finiteNumber(rec.score),
    strikeType: typeof rec.strike_type === 'string' ? rec.strike_type : null,
    acceptable: typeof rec.is_acceptable === 'boolean' ? rec.is_acceptable : null,
    rejectionReasons: toStringList(rec.rejection_reasons),
  };
}

/**
 * Ranked contract selector (POST /api/v1/options-intelligence/select-contract).
 * Requires a live spot price; without one the panel renders an explicit
 * unavailable state instead of demo contracts.
 */
export const ContractSelector: React.FC<ContractSelectorProps> = ({
  underlying,
  direction,
  spot,
  iv,
  marketError,
  onSelectionChange,
  onSelectContract,
}) => {
  const [candidates, setCandidates] = useState<CandidateView[]>([]);
  const [selectedStrike, setSelectedStrike] = useState<number | null>(null);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [rationale, setRationale] = useState<string[]>([]);
  const [viable, setViable] = useState<boolean | null>(null);
  const [nonViability, setNonViability] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setCandidates([]);
    setSelectedStrike(null);
    setSelectedType(null);
    setRationale([]);
    setViable(null);
    setNonViability([]);
    setError(null);
    onSelectionChange?.(null);

    if (spot === null || spot <= 0) {
      setError(marketError ?? 'Live spot unavailable — contract selection is blocked.');
      return () => {
        cancelled = true;
      };
    }

    setLoading(true);
    void (async () => {
      try {
        const res = await api.selectOptimalContract({
          underlying,
          spot_price: spot,
          direction: directionToLong(direction),
          ...(iv !== null && iv > 0 ? { current_iv: iv } : {}),
        });
        if (cancelled) return;
        const rec = asRecord(res);
        const selected = asRecord(rec?.selected_contract);
        const list = Array.isArray(rec?.all_candidates)
          ? (rec?.all_candidates as unknown[]).map(toCandidate).filter((c): c is CandidateView => c !== null)
          : [];
        if (!rec || !selected || list.length === 0) {
          setError('Selector returned no ranked contracts — nothing to select.');
          onSelectionChange?.(null);
          return;
        }
        const strike = finiteNumber(rec.selected_strike) ?? finiteNumber(selected.strike);
        const optionType = typeof selected.option_type === 'string' ? selected.option_type : null;
        setCandidates(list);
        setSelectedStrike(strike);
        setSelectedType(optionType);
        setRationale(toStringList(rec.selection_rationale));
        setViable(typeof rec.is_viable === 'boolean' ? rec.is_viable : null);
        setNonViability(toStringList(rec.non_viability_reasons));
        onSelectionChange?.({
          strike,
          optionType,
          lotSize: finiteNumber(selected.lot_size),
          brokerSymbol: typeof selected.broker_symbol === 'string' ? selected.broker_symbol : null,
        });
      } catch (e) {
        if (!cancelled) {
          setError(errorMessage(e, 'Contract selection failed.'));
          onSelectionChange?.(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [underlying, direction, spot, iv, marketError, onSelectionChange]);

  return (
    <div className="space-y-2 font-mono text-xs">
      <div className="text-ink-2 font-semibold flex items-center justify-between gap-2">
        <span>OPTIMAL CONTRACT SELECTOR (ALGO-RANKED)</span>
        {loading ? <span className="text-[10px] text-primary animate-pulse">Ranking…</span> : null}
        {viable === false ? (
          <Badge variant="warning" size="xs">
            NO VIABLE CONTRACT
          </Badge>
        ) : null}
      </div>

      {error ? (
        <div role="alert" className="p-2.5 rounded bg-warn-wash border border-warn-line text-warn-ink text-[11px] leading-relaxed">
          {error}
        </div>
      ) : null}

      {!error && viable === false && nonViability.length > 0 ? (
        <div role="alert" className="p-2.5 rounded bg-warn-wash border border-warn-line text-warn-ink text-[11px]">
          {nonViability.join('; ')}
        </div>
      ) : null}

      {!error && candidates.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {candidates.map((c, idx) => {
            const isSelected = c.strike === selectedStrike && c.optionType === selectedType;
            return (
              <button
                type="button"
                key={`${c.strike}-${c.optionType}-${idx}`}
                onClick={() => onSelectContract?.(c.raw)}
                className={`text-left p-3 rounded-lg bg-surface border shadow-xs transition-all flex flex-col justify-between ${
                  isSelected ? 'border-primary' : 'border-border hover:border-primary'
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="font-bold text-ink">
                    {underlying} {c.strike ?? '—'} {c.optionType ?? ''}
                  </span>
                  <Badge variant={isSelected ? 'success' : c.acceptable === false ? 'warning' : 'neutral'} size="xs">
                    {isSelected ? 'SELECTED' : c.acceptable === false ? 'NOT VIABLE' : c.strikeType ?? 'CANDIDATE'}
                  </Badge>
                </div>

                <div className="grid grid-cols-3 gap-1 py-1 text-[11px] border-y border-border-subtle my-1 text-center">
                  <div>
                    <div className="text-[10px] text-ink-3">PREMIUM</div>
                    <div className="text-primary font-semibold">
                      {c.premium !== null ? `₹${c.premium}` : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-ink-3">DELTA</div>
                    <div className="text-ink font-semibold">{c.delta !== null ? c.delta.toFixed(3) : '—'}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-ink-3">IV</div>
                    <div className="text-ink font-semibold">
                      {c.iv !== null ? `${(c.iv * 100).toFixed(1)}%` : '—'}
                    </div>
                  </div>
                </div>

                <div className="text-[10px] text-ink-3 pt-1">
                  <div className="flex items-center justify-between">
                    <span>Score: {c.score !== null ? c.score : '—'}</span>
                    <span className="text-primary font-semibold">Select →</span>
                  </div>
                  {c.rejectionReasons.length > 0 ? (
                    <div className="text-warn-ink mt-1 leading-relaxed">{c.rejectionReasons.join('; ')}</div>
                  ) : null}
                </div>
              </button>
            );
          })}
        </div>
      ) : null}

      {!error && rationale.length > 0 ? (
        <div className="text-[10px] text-ink-3 leading-relaxed border border-border-subtle bg-secondary p-2 rounded">
          {rationale.join(' · ')}
        </div>
      ) : null}
    </div>
  );
};
