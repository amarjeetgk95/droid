'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { PageTabs } from '@/components/ui/PageTabs';
import { AlertTriangle } from 'lucide-react';

import {
  UnderlyingSymbol,
  TradingHorizon,
  DirectionalBias,
  FinancialResearchReport,
  ExpectedMoveProjection,
  ContractSelectionReport,
  PortfolioGreeksSummary,
} from '@/components/options-intelligence/options-types';

import { OptionsCommandBar } from '@/components/options-intelligence/OptionsCommandBar';
import { AiResearchTab } from '@/components/options-intelligence/AiResearchTab';
import { ExpectedMoveTab } from '@/components/options-intelligence/ExpectedMoveTab';
import { ContractSelectorTab } from '@/components/options-intelligence/ContractSelectorTab';
import { PortfolioGreeksTab } from '@/components/options-intelligence/PortfolioGreeksTab';
import { Brain, Gauge, Layers, Scale } from 'lucide-react';

const SPOT_BASELINES: Record<UnderlyingSymbol, number> = {
  NIFTY: 24920.0,
  BANKNIFTY: 51850.0,
  SENSEX: 81850.0,
};

const INSTRUMENT_IV: Record<UnderlyingSymbol, number> = {
  NIFTY: 0.142,
  BANKNIFTY: 0.198,
  SENSEX: 0.138,
};

const STOP_LOSS_POINTS: Record<UnderlyingSymbol, Record<TradingHorizon, number>> = {
  NIFTY: { SCALP: 18, INTRADAY: 35, SWING: 80, POSITIONAL: 160 },
  BANKNIFTY: { SCALP: 60, INTRADAY: 110, SWING: 240, POSITIONAL: 500 },
  SENSEX: { SCALP: 80, INTRADAY: 150, SWING: 340, POSITIONAL: 700 },
};

export default function OptionsIntelligencePage() {
  const [underlying, setUnderlying] = useState<UnderlyingSymbol>('NIFTY');
  const [horizon, setHorizon] = useState<TradingHorizon>('INTRADAY');
  const [direction, setDirection] = useState<DirectionalBias>('BULLISH');
  const [loading, setLoading] = useState<boolean>(true);
  const [synthesizing, setSynthesizing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Intelligence Data States
  const [researchData, setResearchData] = useState<FinancialResearchReport | null>(null);
  const [expectedMoveData, setExpectedMoveData] = useState<ExpectedMoveProjection | null>(null);
  const [contractSelection, setContractSelection] = useState<ContractSelectionReport | null>(null);
  const [portfolioGreeks, setPortfolioGreeks] = useState<PortfolioGreeksSummary | null>(null);

  const spot = SPOT_BASELINES[underlying] || 25000.0;
  const currentIv = INSTRUMENT_IV[underlying] || 0.155;
  const stopLoss = STOP_LOSS_POINTS[underlying]?.[horizon] || 35;

  const loadAllIntelligence = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const optDirection = direction === 'BULLISH' ? 'LONG_CALL' : 'LONG_PUT';

      const [researchRes, moveRes, selectRes, greeksRes] = await Promise.all([
        api.getFinancialResearch(underlying, horizon, direction),
        api.projectExpectedMove({
          underlying,
          spot,
          direction,
          horizon,
          current_iv: currentIv,
        }),
        api.selectOptimalContract({
          underlying,
          spot_price: spot,
          direction: optDirection,
          stop_loss_points: stopLoss,
          current_iv: currentIv,
        }),
        api.getPortfolioGreeksSummary(),
      ]);

      setResearchData(researchRes);
      setExpectedMoveData(moveRes);
      setContractSelection(selectRes);
      setPortfolioGreeks(greeksRes);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch options intelligence data');
    } finally {
      setLoading(false);
    }
  }, [underlying, horizon, direction, spot, currentIv, stopLoss]);

  useEffect(() => {
    loadAllIntelligence();
  }, [loadAllIntelligence]);

  const handleSynthesizeAI = async () => {
    setSynthesizing(true);
    try {
      const res = await api.synthesizeFinancialResearch({ underlying, horizon, direction });
      setResearchData(res);
    } catch (err: any) {
      setError(err?.message || 'Failed to synthesize AI financial research');
    } finally {
      setSynthesizing(false);
    }
  };

  const tabs = [
    {
      id: 'ai_research',
      label: 'AI Research & Contradictions (§42)',
      icon: Brain,
      content: (
        <AiResearchTab
          researchData={researchData}
          onSynthesizeAI={handleSynthesizeAI}
          synthesizing={synthesizing}
        />
      ),
    },
    {
      id: 'expected_move',
      label: 'Expected Move & Velocity (§8)',
      icon: Gauge,
      content: <ExpectedMoveTab expectedMoveData={expectedMoveData} />,
    },
    {
      id: 'contract_selection',
      label: 'Strike Selector & Simulation (§31)',
      icon: Layers,
      content: <ContractSelectorTab contractSelection={contractSelection} underlying={underlying} />,
    },
    {
      id: 'portfolio_greeks',
      label: 'Portfolio Greeks Ledger (§36, §51)',
      icon: Scale,
      content: <PortfolioGreeksTab portfolioGreeks={portfolioGreeks} />,
    },
  ];

  return (
    <div className="space-y-5">
      {/* Sleek 2-Tier Institutional Command Bar */}
      <OptionsCommandBar
        underlying={underlying}
        setUnderlying={setUnderlying}
        horizon={horizon}
        setHorizon={setHorizon}
        direction={direction}
        setDirection={setDirection}
        spotPrice={spot}
        currentIv={currentIv}
        lotSize={contractSelection?.selected_contract?.lot_size}
        loading={loading}
        synthesizing={synthesizing}
        onRefresh={loadAllIntelligence}
        onSynthesizeAI={handleSynthesizeAI}
      />

      {error && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-400 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={loadAllIntelligence}
            className="underline font-semibold hover:text-rose-300"
          >
            Retry
          </button>
        </div>
      )}

      {/* Main Tabbed Interface */}
      <PageTabs tabs={tabs} defaultTab="ai_research" />
    </div>
  );
}
