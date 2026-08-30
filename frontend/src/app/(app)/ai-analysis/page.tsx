'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { AIInsightResponse, AIHistoryItem } from '@/lib/types';
import { AIBiasBanner } from '@/components/ai/AIBiasBanner';
import { AIInsightSections } from '@/components/ai/AIInsightSections';
import { AIRiskDisclaimer } from '@/components/ai/AIRiskDisclaimer';
import { History, Brain } from 'lucide-react';

export default function AIAnalysisPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [selectedProvider, setSelectedProvider] = useState<string>('mock_ai');
  const [insight, setInsight] = useState<AIInsightResponse | null>(null);
  const [history, setHistory] = useState<AIHistoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Initial load
  useEffect(() => {
    let isMounted = true;

    const fetchAnalysis = async () => {
      try {
        const [res, histRes] = await Promise.all([
          api.generateAIAnalysis(selectedSymbol, selectedProvider),
          api.getAIHistory(selectedSymbol),
        ]);
        if (isMounted) {
          setInsight(res.data);
          setHistory(histRes.data);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to generate AI analysis');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchAnalysis();
    return () => {
      isMounted = false;
    };
  }, [selectedSymbol, selectedProvider]);

  const handleGenerate = () => {
    setLoading(true);
    api
      .generateAIAnalysis(selectedSymbol, selectedProvider)
      .then((res) => {
        setInsight(res.data);
        setError(null);
        // Refresh history
        api.getAIHistory(selectedSymbol).then((h) => setHistory(h.data));
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to generate AI analysis'))
      .finally(() => setLoading(false));
  };

  return (
    <div className="space-y-4">
      {/* Header & Bias Banner */}
      <AIBiasBanner
        insight={insight}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={(sym) => setSelectedSymbol(sym)}
        selectedProvider={selectedProvider}
        onSelectProvider={(prov) => setSelectedProvider(prov)}
        onGenerate={handleGenerate}
        loading={loading}
      />

      {/* Main Content Area */}
      {error ? (
        <div className="p-8 text-center bg-card border border-destructive/20 rounded-xl text-destructive">
          <p className="font-semibold text-sm">Error generating market intelligence</p>
          <p className="text-xs mt-1 opacity-80">{error}</p>
        </div>
      ) : loading && !insight ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-muted-foreground animate-pulse space-y-2">
          <Brain className="w-8 h-8 text-primary mx-auto animate-bounce" />
          <p className="font-semibold text-sm">Synthesizing quantitative derivatives dossier...</p>
          <p className="text-xs text-muted-foreground">
            Analyzing PCR, Max Pain, Futures Basis, Buildup, S/R Pivots, and India VIX.
          </p>
        </div>
      ) : insight ? (
        <div className="space-y-4">
          {/* Structured Quantitative Analysis Cards */}
          <AIInsightSections insight={insight} />

          {/* Risk Management & Compliance Disclaimer */}
          <AIRiskDisclaimer
            riskNotes={insight.risk_management_notes}
            disclaimer={insight.disclaimer}
          />

          {/* Analysis History */}
          {history.length > 1 && (
            <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-primary" />
                <h3 className="font-bold text-xs text-foreground uppercase tracking-wider">
                  Recent Intelligence Reports ({history.length})
                </h3>
              </div>
              <div className="space-y-2">
                {history.slice(1, 5).map((h) => (
                  <div
                    key={h.id}
                    className="bg-secondary/30 p-2.5 rounded-lg border border-border flex items-center justify-between gap-3 text-xs"
                  >
                    <div className="space-y-0.5">
                      <span className="font-mono font-semibold text-muted-foreground text-[10px]">
                        {new Date(h.timestamp).toLocaleTimeString('en-IN')}
                      </span>
                      <p className="text-foreground text-xs line-clamp-1">{h.executive_summary}</p>
                    </div>
                    <span className="shrink-0 text-[10px] px-2 py-0.5 rounded font-bold bg-secondary text-primary border border-border">
                      {h.market_bias} ({h.confidence}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
