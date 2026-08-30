'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import {
  StrategyLegModel,
  StrategyPayoffResult,
  StrategyTemplate,
} from '@/lib/types';
import { TemplateSelector } from '@/components/strategy/TemplateSelector';
import { StrategyLegsTable } from '@/components/strategy/StrategyLegsTable';
import { DualPayoffChart } from '@/components/strategy/DualPayoffChart';
import { StrategyMetrics } from '@/components/strategy/StrategyMetrics';
import { Target } from 'lucide-react';

export default function StrategyPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>('bull_call_spread');
  const [result, setResult] = useState<StrategyPayoffResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Load templates on mount
  useEffect(() => {
    let isMounted = true;
    api
      .getStrategyTemplates()
      .then((res) => {
        if (isMounted) setTemplates(res.data);
      })
      .catch((err) => console.error('Failed to load templates', err));
    return () => {
      isMounted = false;
    };
  }, []);

  // Fetch strategy when template or symbol changes
  useEffect(() => {
    if (!selectedTemplateId) return;
    let isMounted = true;

    const fetchBuiltTemplate = async () => {
      try {
        const res = await api.buildStrategyTemplate(selectedTemplateId, selectedSymbol);
        if (isMounted) {
          setResult(res.data);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to instantiate template');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchBuiltTemplate();
    return () => {
      isMounted = false;
    };
  }, [selectedSymbol, selectedTemplateId]);

  // Recalculate custom payoff when legs change
  const handleRecalculatePayoff = async (legs: StrategyLegModel[]) => {
    if (!result) return;
    try {
      const res = await api.calculateStrategyPayoff({
        underlying: selectedSymbol,
        spot_price: result.spot_price,
        legs,
      });
      setResult(res.data);
    } catch (err) {
      console.error('Payoff calculation error', err);
    }
  };

  const handleUpdateLeg = (index: number, updated: Partial<StrategyLegModel>) => {
    if (!result) return;
    const newLegs = [...result.legs];
    newLegs[index] = { ...newLegs[index], ...updated };
    setSelectedTemplateId(null); // Switch to custom mode
    handleRecalculatePayoff(newLegs);
  };

  const handleAddLeg = () => {
    if (!result) return;
    const spot = result.spot_price;
    const step = selectedSymbol === 'BANKNIFTY' || selectedSymbol === 'SENSEX' ? 100 : 50;
    const newLeg: StrategyLegModel = {
      id: Math.random().toString(36).substring(7),
      option_type: 'CE',
      side: 'BUY',
      strike: Math.round(spot / step) * step,
      quantity: 1,
      price: 100.0,
      iv: 0.15,
      expiry: result.legs[0]?.expiry || '2026-09-03',
      lot_size: selectedSymbol === 'SENSEX' ? 10 : selectedSymbol === 'BANKNIFTY' ? 30 : 75,
    };
    setSelectedTemplateId(null);
    handleRecalculatePayoff([...result.legs, newLeg]);
  };

  const handleRemoveLeg = (index: number) => {
    if (!result) return;
    const newLegs = result.legs.filter((_, idx) => idx !== index);
    setSelectedTemplateId(null);
    handleRecalculatePayoff(newLegs);
  };

  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];

  return (
    <div className="space-y-4">
      {/* Header Bar */}
      <div className="bg-card border border-border rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="bg-primary/10 p-2 rounded-lg">
            <Target className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-base font-bold text-foreground">Multi-Leg Strategy Builder & Payoff Simulator</h2>
            <p className="text-xs text-muted-foreground">
              Institutional derivatives modeling with dual-curve expiration & T+0 Greek analysis
            </p>
          </div>
        </div>

        {/* Symbol Selector */}
        <div className="flex items-center gap-2">
          {symbols.map((sym) => (
            <button
              key={sym}
              onClick={() => setSelectedSymbol(sym)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                selectedSymbol === sym
                  ? 'bg-primary text-primary-foreground shadow-xs'
                  : 'bg-secondary hover:bg-secondary/80 text-muted-foreground hover:text-foreground'
              }`}
            >
              {sym}
            </button>
          ))}
        </div>
      </div>

      {/* Pre-Built Template Selector */}
      <TemplateSelector
        templates={templates}
        selectedTemplateId={selectedTemplateId}
        onSelectTemplate={(tmplId) => setSelectedTemplateId(tmplId)}
      />

      {/* Main Content Area */}
      {error ? (
        <div className="p-8 text-center bg-card border border-destructive/20 rounded-xl text-destructive">
          <p className="font-semibold text-sm">Error evaluating strategy payoff</p>
          <p className="text-xs mt-1 opacity-80">{error}</p>
        </div>
      ) : loading && !result ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-muted-foreground animate-pulse">
          Simulating dual-curve payoff and aggregating portfolio Greeks...
        </div>
      ) : result ? (
        <div className="space-y-4">
          {/* Strategy Summary & Portfolio Greeks */}
          <StrategyMetrics result={result} />

          {/* Dual-Curve Payoff SVG Chart */}
          <DualPayoffChart
            payoffCurve={result.payoff_curve}
            spotPrice={result.spot_price}
            breakevens={result.breakevens}
            maxProfit={result.max_profit}
            maxLoss={result.max_loss}
          />

          {/* Interactive Legs Table */}
          <StrategyLegsTable
            legs={result.legs}
            onUpdateLeg={handleUpdateLeg}
            onAddLeg={handleAddLeg}
            onRemoveLeg={handleRemoveLeg}
            spotPrice={result.spot_price}
            expiry={result.legs[0]?.expiry || ''}
          />
        </div>
      ) : null}
    </div>
  );
}
