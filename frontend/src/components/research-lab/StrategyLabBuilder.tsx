'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { Card, EmptyNote, fmtINR, fmtNum } from '@/components/ui/desk';
import { Button } from '@/components/ui/button';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { useInstrument } from '@/context/InstrumentContext';
import { ErrorNote, ExportButtons, SectionLabel } from './controls';
import { exportAsJson, exportRowsAsCsv, timestampSlug } from './export';
import {
  errorMessage,
  parsePayoffResult,
  parseStrategyTemplates,
  parseTemplateStrategy,
  type StrategyTemplateRow,
  type TemplateStrategyRow,
} from './contracts';
import { PayoffCurveChart } from './PayoffCurveChart';

interface BuiltStrategy extends TemplateStrategyRow {
  source: 'template' | 'recalculated';
}

export const StrategyLabBuilder: React.FC = () => {
  const { instrument, allInstruments } = useInstrument();
  const [templates, setTemplates] = useState<StrategyTemplateRow[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);
  const [templatesError, setTemplatesError] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [underlying, setUnderlying] = useState<string>(instrument);
  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [strategy, setStrategy] = useState<BuiltStrategy | null>(null);
  const [spotOverride, setSpotOverride] = useState('');
  const [recalculating, setRecalculating] = useState(false);
  const [recalcError, setRecalcError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);

  const loadTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    setTemplatesError(null);
    try {
      const res = await api.getStrategyTemplates();
      const rows = parseStrategyTemplates(res) ?? [];
      setTemplates(rows);
      setSelectedTemplateId((prev) =>
        rows.some((t) => t.template_id === prev) ? prev : (rows[0]?.template_id ?? ''),
      );
    } catch (err) {
      setTemplates([]);
      setTemplatesError(errorMessage(err));
    } finally {
      setTemplatesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  const selectedTemplate = useMemo(
    () => templates.find((t) => t.template_id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId],
  );

  const handleBuild = async () => {
    if (!selectedTemplateId || building) return;
    setBuilding(true);
    setBuildError(null);
    setRecalcError(null);
    try {
      const params = new URLSearchParams({ template_id: selectedTemplateId, symbol: underlying });
      const res = await api.request<unknown>(
        `/api/v1/strategy/build-template?${params.toString()}`,
        { method: 'POST' },
      );
      const parsed = parseTemplateStrategy(res);
      if (!parsed || parsed.points.length < 2) {
        setStrategy(null);
        setBuildError('Template response did not include a payoff curve — no strategy to plot.');
        return;
      }
      setStrategy({ ...parsed, source: 'template' });
      setSpotOverride(parsed.spot_price === null ? '' : String(parsed.spot_price));
      setLastUpdatedAt(new Date());
    } catch (err) {
      setStrategy(null);
      setBuildError(errorMessage(err));
    } finally {
      setBuilding(false);
    }
  };

  const handleRecalculate = async () => {
    if (!strategy || recalculating) return;
    const spot = Number(spotOverride);
    if (!Number.isFinite(spot) || spot <= 0) {
      setRecalcError('Enter a positive spot price to recalculate the payoff.');
      return;
    }
    if (strategy.legs.length === 0) {
      setRecalcError('No strategy legs in scope — build from a live template first.');
      return;
    }
    setRecalculating(true);
    setRecalcError(null);
    try {
      const legs = strategy.legs.map((leg) => ({
        option_type: leg.option_type,
        side: leg.side,
        strike: leg.strike,
        quantity: leg.quantity,
        price: leg.price,
        lot_size: leg.lot_size ?? undefined,
      }));
      const res = await api.request<unknown>('/api/v1/strategy/payoff', {
        method: 'POST',
        body: JSON.stringify({ underlying, spot_price: spot, legs }),
      });
      const parsed = parsePayoffResult(res);
      if (!parsed || parsed.points.length < 2) {
        setRecalcError('Payoff response did not include a curve.');
        return;
      }
      setStrategy({
        ...strategy,
        points: parsed.points,
        spot_price: parsed.spot_price ?? spot,
        max_profit: null,
        max_loss: null,
        risk_reward: null,
        source: 'recalculated',
      });
      setLastUpdatedAt(new Date());
    } catch (err) {
      setRecalcError(errorMessage(err));
    } finally {
      setRecalculating(false);
    }
  };

  const handleExportJson = () => {
    if (!strategy) return;
    exportAsJson(`strategy-payoff-${underlying}-${timestampSlug()}.json`, strategy);
  };

  const handleExportCsv = () => {
    if (!strategy || strategy.points.length === 0) return;
    exportRowsAsCsv(
      `strategy-payoff-${underlying}-${timestampSlug()}.csv`,
      strategy.points.map((p) => ({ spot: p.spot, pnl: p.pnl })),
    );
  };

  return (
    <Card
      title="STRATEGY LAB & PAYOFF SIMULATOR"
      meta={strategy ? `${underlying} · spot ${strategy.spot_price === null ? '—' : fmtINR(strategy.spot_price)}` : 'live template builder'}
      action={<ExportButtons onJson={strategy ? handleExportJson : undefined} onCsv={strategy && strategy.points.length > 0 ? handleExportCsv : undefined} disabled={!strategy} />}
    >
      <div className="space-y-3 text-xs">
        {templatesLoading ? <p className="muted" style={{ margin: 0 }}>Loading strategy templates…</p> : null}
        {templatesError ? (
          <ErrorNote message={`Strategy templates unavailable — ${templatesError}`} onRetry={loadTemplates} />
        ) : null}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <SectionLabel>Template</SectionLabel>
            <select
              value={selectedTemplateId}
              onChange={(e) => setSelectedTemplateId(e.target.value)}
              className="input input-sm w-full"
              aria-label="Strategy template"
              disabled={templates.length === 0}
            >
              {templates.length === 0 ? <option value="">No templates</option> : null}
              {templates.map((t) => (
                <option key={t.template_id} value={t.template_id}>
                  {t.name}
                  {t.legs_count === null ? '' : ` (${t.legs_count} legs)`}
                </option>
              ))}
            </select>
          </div>
          <div>
            <SectionLabel>Underlying</SectionLabel>
            <select
              value={underlying}
              onChange={(e) => setUnderlying(e.target.value)}
              className="input input-sm w-full"
              aria-label="Underlying"
            >
              {allInstruments.map((inst) => (
                <option key={inst} value={inst}>{inst}</option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <Button type="button" onClick={() => void handleBuild()} disabled={building || !selectedTemplateId} className="w-full">
              {building ? 'Building from live spot…' : 'Build payoff from live spot'}
            </Button>
          </div>
        </div>

        {selectedTemplate?.description ? (
          <p className="muted" style={{ margin: 0 }}>{selectedTemplate.description}</p>
        ) : null}

        {buildError ? <ErrorNote message={buildError} onRetry={() => void handleBuild()} /> : null}

        {strategy ? (
          <div className="space-y-3">
            <PayoffCurveChart
              points={strategy.points}
              spotPrice={strategy.spot_price}
              maxProfit={strategy.max_profit}
              maxLoss={strategy.max_loss}
              breakevens={null}
              riskRewardRatio={strategy.risk_reward}
              premiumNote={strategy.premium_note}
            />

            {strategy.legs.length > 0 ? (
              <div>
                <SectionLabel>Strategy legs</SectionLabel>
                <div className="overflow-x-auto">
                  <table className="tbl tbl--dense w-full text-left">
                    <thead>
                      <tr>
                        <th style={{ textAlign: 'left' }}>Type</th>
                        <th style={{ textAlign: 'left' }}>Side</th>
                        <th style={{ textAlign: 'right' }}>Strike</th>
                        <th style={{ textAlign: 'right' }}>Premium</th>
                        <th style={{ textAlign: 'right' }}>Qty</th>
                        <th style={{ textAlign: 'right' }}>Lot</th>
                      </tr>
                    </thead>
                    <tbody>
                      {strategy.legs.map((leg, index) => (
                        <tr key={`${leg.option_type}-${leg.strike}-${leg.side}-${index}`}>
                          <td>{leg.option_type}</td>
                          <td className={leg.side === 'BUY' ? 'text-up-strong' : 'text-down-strong'}>{leg.side}</td>
                          <td style={{ textAlign: 'right' }} className="num">{fmtINR(leg.strike)}</td>
                          <td style={{ textAlign: 'right' }} className="num">{fmtINR(leg.price)}</td>
                          <td style={{ textAlign: 'right' }} className="num">{leg.quantity}</td>
                          <td style={{ textAlign: 'right' }} className="num">{leg.lot_size ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}

            <div className="flex flex-wrap items-end gap-2">
              <div style={{ width: 180 }}>
                <SectionLabel>Spot override (payoff only)</SectionLabel>
                <input
                  type="number"
                  min={0}
                  step="0.05"
                  value={spotOverride}
                  onChange={(e) => setSpotOverride(e.target.value)}
                  className="input input-sm w-full num"
                  aria-label="Spot override"
                />
              </div>
              <Button type="button" variant="outline" onClick={() => void handleRecalculate()} disabled={recalculating}>
                {recalculating ? 'Recalculating…' : 'Recalculate payoff'}
              </Button>
              <span className="muted" style={{ margin: 0 }}>
                {strategy.source === 'template' ? 'Server-computed from the live template spot' : 'Recalculated at the overridden spot'}
              </span>
            </div>

            {recalcError ? <ErrorNote message={recalcError} /> : null}

            {strategy.risk_reward !== null ? (
              <p className="muted" style={{ margin: 0 }}>
                Risk/reward from template: {fmtNum(strategy.risk_reward, 2)}
              </p>
            ) : null}
          </div>
        ) : (
          !buildError && !templatesLoading ? (
            <EmptyNote>
              No strategy in scope. Build a template against the live {underlying} spot to plot the
              real expiry payoff.
            </EmptyNote>
          ) : null
        )}

        <div className="flex items-center justify-end">
          <FreshnessClock
            lastAt={lastUpdatedAt}
            fetching={building || recalculating}
            sourceLabel="POST · strategy engine"
          />
        </div>
      </div>
    </Card>
  );
};
