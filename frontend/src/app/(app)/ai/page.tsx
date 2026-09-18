'use client';

import { useEffect } from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { findInstrumentCard } from '@/lib/symbols';
import { syncAISecretsFromBackend } from '@/lib/aiKeySync';
import {
  AICopilotChat,
  AIAnalysisCard,
  AIDeepInsightCard,
  AITradeValidator,
  AIStrategyPanel,
} from '@/components/ai';

export default function AICopilotPage() {
  const { instrument } = useInstrument();
  const live = useOptionalLiveMarketContext();
  const market = useOptionalMarketDataContext();

  // Pull provider keys saved on another device before the AI cards resolve
  // settings. Throttled inside the module; `useAISettings` refreshes on the
  // emitted sync event.
  useEffect(() => {
    void syncAISecretsFromBackend();
  }, []);

  const cards = live?.cards && live.cards.length > 0 ? live.cards : market?.cards ?? [];
  const currentCard = findInstrumentCard(cards, instrument);
  const spotPrice = currentCard?.ltp ?? null;

  return (
    <div className="space-y-5">
      {/* Primary surface: tool-calling copilot tied to the selected index */}
      <AICopilotChat symbol={instrument} contextPage="ai-copilot" />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <AIAnalysisCard symbol={instrument} contextPage="ai-copilot" />
        <AIDeepInsightCard symbol={instrument} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <AIStrategyPanel symbol={instrument} />
        <AITradeValidator symbol={instrument} spotPrice={spotPrice} />
      </div>
    </div>
  );
}
