'use client';

import React, { useState } from 'react';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import {
  collectPathScenarios,
  directionToOptionType,
  errorMessage,
  meanScenarioPnl,
  type PathScenarioView,
} from './forgeLogic';

interface PathSimulatorProps {
  underlying: string;
  spot: number | null;
  iv: number | null;
  dteDays: number | null;
  atmStrike: number | null;
  direction: 'CALL' | 'PUT';
  stop: number | null;
  target: number | null;
  quantity: number | null;
  marketError?: string | null;
}

interface SimulationState {
  scenarios: PathScenarioView[];
  viable: boolean | null;
  rationale: string[];
  entryPremium: number | null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/**
 * Path-dependent P&L simulation (POST /api/v1/options-intelligence/simulate-path).
 * Every input (spot, ATM strike, IV, DTE, stop, target, sized quantity) is a
 * real published/entered value; incomplete inputs render a blocked state.
 */
export const PathSimulator: React.FC<PathSimulatorProps> = ({
  underlying,
  spot,
  iv,
  dteDays,
  atmStrike,
  direction,
  stop,
  target,
  quantity,
  marketError,
}) => {
  const [simulating, setSimulating] = useState(false);
  const [simulation, setSimulation] = useState<SimulationState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const missing: string[] = [];
  if (spot === null) missing.push('live spot');
  if (atmStrike === null) missing.push('ATM strike');
  if (iv === null) missing.push('ATM IV');
  if (dteDays === null) missing.push('days to expiry');
  if (stop === null) missing.push('stop loss level');
  if (target === null) missing.push('target level');
  if (quantity === null) missing.push('sized quantity (contract lot)');
  const inputsReady = missing.length === 0;

  const handleSimulate = async () => {
    if (!inputsReady || simulating) return;
    setSimulating(true);
    setError(null);
    setSimulation(null);
    try {
      const res = await api.simulateOptionPath({
        underlying,
        spot,
        strike: atmStrike,
        option_type: directionToOptionType(direction),
        dte_days: dteDays,
        iv,
        target_spot: target,
        stop_spot: stop,
        quantity,
      });
      const rec = asRecord(res);
      const scenarios = collectPathScenarios(rec);
      if (scenarios.length === 0) {
        setError('Simulation returned no scenario rows.');
        return;
      }
      setSimulation({
        scenarios,
        viable: typeof rec?.is_economically_viable === 'boolean' ? rec.is_economically_viable : null,
        rationale: Array.isArray(rec?.viability_rationale)
          ? (rec?.viability_rationale as unknown[]).filter((v): v is string => typeof v === 'string')
          : [],
        entryPremium: typeof rec?.entry_premium === 'number' ? rec.entry_premium : null,
      });
    } catch (e) {
      setError(errorMessage(e, 'Path simulation failed.'));
    } finally {
      setSimulating(false);
    }
  };

  const scenarios = simulation?.scenarios ?? [];
  const winCount = scenarios.filter((s) => s.profitable === true).length;
  const meanPnl = meanScenarioPnl(scenarios);

  return (
    <div className="p-3.5 rounded-lg bg-surface border border-border shadow-xs font-mono text-xs space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-ink font-semibold">PATH SIMULATOR (NET P&amp;L AFTER FRICTION)</span>
        <button
          type="button"
          onClick={handleSimulate}
          disabled={simulating || !inputsReady}
          title={inputsReady ? 'Run the backend path simulation' : `Blocked — missing ${missing.join(', ')}`}
          className="px-2.5 py-1 rounded border border-border bg-secondary hover:bg-muted-strong text-primary text-[11px] font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {simulating ? 'Simulating…' : 'Run Simulation'}
        </button>
      </div>

      {!inputsReady ? (
        <div role="status" className="p-2.5 rounded bg-warn-wash border border-warn-line text-warn-ink text-[11px] leading-relaxed">
          {marketError ? `${marketError} ` : ''}
          Simulation blocked — missing {missing.join(', ')}.
        </div>
      ) : null}

      {error ? (
        <div role="alert" className="p-2.5 rounded bg-down-wash border border-down-line text-down-strong text-[11px] leading-relaxed">
          Path simulation unavailable — {error}
        </div>
      ) : null}

      {simulation ? (
        <>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-ink-3">
            <span>
              Profitable paths:{' '}
              <strong className="text-up-strong">
                {winCount}/{scenarios.length}
              </strong>
            </span>
            <span>
              Mean net P&amp;L:{' '}
              <strong className={meanPnl !== null && meanPnl >= 0 ? 'text-up-strong' : 'text-down-strong'}>
                {meanPnl !== null ? `${meanPnl >= 0 ? '+' : ''}₹${meanPnl.toFixed(0)}` : '—'}
              </strong>
            </span>
            {simulation.entryPremium !== null ? (
              <span>Entry premium: ₹{simulation.entryPremium}</span>
            ) : null}
            {simulation.viable !== null ? (
              <Badge variant={simulation.viable ? 'success' : 'warning'} size="xs">
                {simulation.viable ? 'ECONOMICALLY VIABLE' : 'NOT VIABLE'}
              </Badge>
            ) : null}
          </div>

          {simulation.rationale.length > 0 ? (
            <div className="text-[10px] text-ink-3 leading-relaxed">{simulation.rationale.join(' · ')}</div>
          ) : null}

          <div className="space-y-1.5">
            {scenarios.map((sc) => (
              <div
                key={sc.key}
                className="p-2 rounded bg-secondary border border-border text-[11px]"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-ink-2">{sc.name}</span>
                  <span
                    className={`font-bold ${
                      sc.netPnl === null ? 'text-ink-3' : sc.netPnl >= 0 ? 'text-up-strong' : 'text-down-strong'
                    }`}
                  >
                    {sc.netPnl !== null ? `${sc.netPnl >= 0 ? '+' : ''}₹${sc.netPnl.toFixed(0)}` : '—'}
                  </span>
                </div>
                <div className="text-[10px] text-ink-3 mt-0.5">
                  {sc.holdingHours !== null ? `Hold ${sc.holdingHours.toFixed(1)}h` : 'Hold —'}
                  {sc.thetaDrag !== null ? ` · Theta drag ₹${sc.thetaDrag.toFixed(0)}` : ''}
                  {sc.profitable === null ? '' : ` · ${sc.profitable ? 'profitable' : 'losing path'}`}
                </div>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
};
