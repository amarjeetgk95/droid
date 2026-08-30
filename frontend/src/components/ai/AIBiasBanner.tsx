'use client';

import { AIInsightResponse } from '@/lib/types';
import { Bot, Sparkles, TrendingUp, TrendingDown, Layers, Zap, RefreshCw } from 'lucide-react';

export function AIBiasBanner({
  insight,
  selectedSymbol,
  onSelectSymbol,
  selectedProvider,
  onSelectProvider,
  onGenerate,
  loading,
}: {
  insight: AIInsightResponse | null;
  selectedSymbol: string;
  onSelectSymbol: (sym: string) => void;
  selectedProvider: string;
  onSelectProvider: (prov: string) => void;
  onGenerate: () => void;
  loading: boolean;
}) {
  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];
  const bias = insight?.market_bias;

  const getBiasConfig = (b?: string) => {
    switch (b) {
      case 'BULLISH':
        return {
          icon: <TrendingUp className="w-4 h-4 text-emerald-400" />,
          badge: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
        };
      case 'BEARISH':
        return {
          icon: <TrendingDown className="w-4 h-4 text-rose-400" />,
          badge: 'bg-rose-500/20 text-rose-400 border-rose-500/40',
        };
      case 'VOLATILE':
        return {
          icon: <Zap className="w-4 h-4 text-purple-400" />,
          badge: 'bg-purple-500/20 text-purple-400 border-purple-500/40',
        };
      default:
        return {
          icon: <Layers className="w-4 h-4 text-primary" />,
          badge: 'bg-primary/20 text-primary border-primary/40',
        };
    }
  };

  const config = getBiasConfig(bias);

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      {/* Top Controls Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Symbol Selector */}
        <div className="flex items-center gap-2">
          {symbols.map((sym) => (
            <button
              key={sym}
              onClick={() => onSelectSymbol(sym)}
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

        {/* Model Provider & Trigger Button */}
        <div className="flex items-center gap-2">
          <select
            value={selectedProvider}
            onChange={(e) => onSelectProvider(e.target.value)}
            className="bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
          >
            <option value="mock_ai">DROID Quant Engine (Mock LLM)</option>
            <option value="gemini">Google Gemini 2.0 Flash</option>
            <option value="ollama">Local Ollama (DeepSeek-R1 / Llama-3)</option>
          </select>

          <button
            onClick={onGenerate}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold transition-all cursor-pointer shadow-xs disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Generate Real-Time Analysis</span>
          </button>
        </div>
      </div>

      {/* Bias Badge & Executive Summary */}
      {insight && (
        <div className="bg-secondary/40 rounded-lg p-4 border border-border space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Bot className="w-5 h-5 text-primary" />
              <span className={`text-xs px-3 py-1 rounded-full font-bold border flex items-center gap-1.5 ${config.badge}`}>
                {config.icon}
                MARKET BIAS: {bias || 'NEUTRAL'}
              </span>
              <span className="text-xs bg-secondary text-foreground px-2.5 py-1 rounded-lg font-mono font-semibold border border-border">
                Confidence: {insight.confidence}%
              </span>
            </div>
            <span className="text-[11px] text-muted-foreground font-mono">
              Provider: <strong className="text-foreground">{insight.provider_used}</strong> • {new Date(insight.timestamp).toLocaleTimeString('en-IN')}
            </span>
          </div>

          <div className="space-y-1">
            <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-primary" /> Executive Market Summary
            </h4>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {insight.executive_summary}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
