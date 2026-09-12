'use client';

import { useState } from 'react';
import { AIAnalysisCard, AIDeepInsightCard, AICopilotChat, AIStrategyPanel, AITradeValidator } from '@/components/ai';

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];

export default function AICopilotPage() {
  const [symbol, setSymbol] = useState('NIFTY');

  return (
    <div className="ds-page">
      <header className="page-hero">
        <div className="toolbar">
          <div>
            <div className="flex items-center gap-2.5">
              <h1>AI Copilot</h1>
              <span className="badge b-info" style={{ fontSize: 11 }}>{symbol}</span>
            </div>
            <p className="muted num">Streaming chat · analysis · deep signal · strategy · audit — all on your Settings → AI Engine keys</p>
          </div>
          <span className="spacer" />
          <div className="seg" role="group" aria-label="Symbol">
            {SYMBOLS.map((s) => (
              <button key={s} type="button" className="seg-btn" data-active={symbol === s} aria-pressed={symbol === s} onClick={() => setSymbol(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>
      </header>

      <AICopilotChat symbol={symbol} contextPage="ai-copilot" />
      <AIAnalysisCard symbol={symbol} contextPage="ai-copilot" />
      <AIDeepInsightCard symbol={symbol} />
      <AIStrategyPanel symbol={symbol} />
      <AITradeValidator symbol={symbol} />
    </div>
  );
}
