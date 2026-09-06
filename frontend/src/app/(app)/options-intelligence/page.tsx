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

  // Spot override state for interactive price testing (The Truth of Wall: explicit simulation)
  const [customSpots, setCustomSpots] = useState<Partial<Record<UnderlyingSymbol, number>>>({});
  // Authentic broker quote state
  const [brokerQuote, setBrokerQuote] = useState<{ ltp: number; status: string } | null>(null);

  // Intelligence Data States
  const [researchData, setResearchData] = useState<FinancialResearchReport | null>(null);
  const [expectedMoveData, setExpectedMoveData] = useState<ExpectedMoveProjection | null>(null);
  const [contractSelection, setContractSelection] = useState<ContractSelectionReport | null>(null);
  const [portfolioGreeks, setPortfolioGreeks] = useState<PortfolioGreeksSummary | null>(null);

  // THE TRUTH OF WALL: Spot price comes ONLY from broker API unless user explicitly enters a manual simulation
  const customSpot = customSpots[underlying];
  const hasLiveBrokerQuote = Boolean(brokerQuote && brokerQuote.status !== 'OFFLINE' && brokerQuote.ltp > 0);
  const spot = customSpot !== undefined ? customSpot : (hasLiveBrokerQuote ? brokerQuote!.ltp : 0);
  const isCustomSpot = customSpot !== undefined;
  const hasMarketData = spot > 0;

  const currentIv = INSTRUMENT_IV[underlying] || 0.155;
  const stopLoss = STOP_LOSS_POINTS[underlying]?.[horizon] || 35;

  const handleUpdateSpot = (newVal: number) => {
    setCustomSpots((prev) => ({ ...prev, [underlying]: newVal }));
  };

  const handleResetSpot = () => {
    setCustomSpots((prev) => {
      const copy = { ...prev };
      delete copy[underlying];
      return copy;
    });
  };

  const loadAllIntelligence = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const optDirection = direction === 'BULLISH' ? 'LONG_CALL' : 'LONG_PUT';

      // 1. Fetch authentic broker quote first (The Truth of Wall)
      let liveSpot = 0;
      try {
        const quoteRes = await api.getQuote(underlying);
        const q = quoteRes?.data;
        if (q && q.ltp > 0 && q.status !== 'OFFLINE') {
          liveSpot = q.ltp;
          setBrokerQuote({ ltp: q.ltp, status: q.status });
        } else {
          setBrokerQuote(null);
        }
      } catch {
        setBrokerQuote(null);
      }

      const activeCalcSpot = customSpots[underlying] !== undefined ? customSpots[underlying]! : liveSpot;

      // 2. Only calculate expected move and contract selection if authentic spot or manual simulation is present
      const promises: [Promise<any>, Promise<any>, Promise<any>, Promise<any>] = [
        api.getFinancialResearch(underlying, horizon, direction),
        activeCalcSpot > 0
          ? api.projectExpectedMove({
              underlying,
              spot: activeCalcSpot,
              direction,
              horizon,
              current_iv: currentIv,
            })
          : Promise.resolve(null),
        activeCalcSpot > 0
          ? api.selectOptimalContract({
              underlying,
              spot_price: activeCalcSpot,
              direction: optDirection,
              stop_loss_points: stopLoss,
              current_iv: currentIv,
            })
          : Promise.resolve(null),
        api.getPortfolioGreeksSummary(),
      ];

      const [researchRes, moveRes, selectRes, greeksRes] = await Promise.all(promises);

      setResearchData(researchRes);
      setExpectedMoveData(moveRes);
      setContractSelection(selectRes);
      setPortfolioGreeks(greeksRes);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch options intelligence data');
    } finally {
      setLoading(false);
    }
  }, [underlying, horizon, direction, customSpots, currentIv, stopLoss]);

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
        isCustomSpot={isCustomSpot}
        onUpdateSpot={handleUpdateSpot}
        onResetSpot={handleResetSpot}
        loading={loading}
        synthesizing={synthesizing}
        onRefresh={loadAllIntelligence}
        onSynthesizeAI={handleSynthesizeAI}
      />

      {/* The Truth of Wall Status Alerts */}
      {!hasMarketData && !isCustomSpot && (
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-4 flex items-start gap-3.5 text-xs text-rose-200">
          <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-bold text-sm text-rose-300">
              The Truth of Wall: Authentic Broker Market Data Offline
            </div>
            <div className="leading-relaxed text-rose-200/90">
              All index spot prices, option strikes, and path models are strictly sourced from the broker API. When the broker connection is inactive or token is expired, <strong>no false or simulated data is fabricated</strong>. Connect your broker in <a href="/settings" className="underline font-bold text-rose-300 hover:text-white">Settings</a> to stream live quotes, or click <strong>Simulate</strong> on the command bar to test custom what-if scenario prices.
            </div>
          </div>
        </div>
      )}

      {isCustomSpot && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-3.5 flex items-start gap-3 text-xs text-amber-200">
          <Scale className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <div className="font-bold text-amber-300">
              Manual Simulation Mode (Not Live Broker Feed)
            </div>
            <div className="leading-relaxed text-amber-200/90">
              Calculating options metrics for hypothetical spot price <strong>₹{spot.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong>. Click <strong>Reset</strong> to return to authentic broker market data.
            </div>
          </div>
        </div>
      )}

      {/* Main Tabbed Interface */}
      <PageTabs tabs={tabs} defaultTab="ai_research" />
    </div>
  );
}
