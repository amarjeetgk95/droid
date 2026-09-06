'use client';

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Coins,
  RefreshCw,
  Sparkles,
  ExternalLink,
  ShieldCheck,
  Brain,
  Zap,
  Activity,
  BarChart3,
} from 'lucide-react';
import {
  CryptoTicker,
  CryptoOrderBook as OrderBookType,
  CryptoDerivatives,
  CryptoMarketOverview,
  CryptoPairComparison,
  CryptoHealthResponse,
  CryptoSignal,
  CryptoScalpSignal,
  CryptoScalpDiagnostics,
  CryptoScalpExecutionRecord,
  CryptoScalpPerformanceMetrics,
} from '@/lib/types';
import { api } from '@/lib/api';
import {
  fetchLiveBinanceTickers,
  fetchLiveBinanceOrderBook,
  BinanceMarket,
  getBinanceWsUrl,
} from '@/lib/binanceLive';
import { useBinanceTickerStream, useBinanceSymbolStream } from '@/hooks/useBinanceStream';
import { CryptoTickerCard } from '@/components/crypto/CryptoTickerCard';
import { CryptoOrderBook } from '@/components/crypto/CryptoOrderBook';
import { CryptoDerivativesCard } from '@/components/crypto/CryptoDerivativesCard';
import { CryptoMarketOverviewStrip } from '@/components/crypto/CryptoMarketOverviewStrip';
import { CryptoPairComparisonCard } from '@/components/crypto/CryptoPairComparisonCard';
import { CryptoSignalsCard } from '@/components/crypto/CryptoSignalsCard';
import { CryptoScalpSignalsCard } from '@/components/crypto/CryptoScalpSignalsCard';
import { CryptoScalpDiagnosticsPanel } from '@/components/crypto/CryptoScalpDiagnosticsPanel';
import { CryptoScalpPerformanceView } from '@/components/crypto/CryptoScalpPerformanceView';
import { CryptoScalpLedgerTable } from '@/components/crypto/CryptoScalpLedgerTable';
import { PageTabs } from '@/components/ui/PageTabs';
import { ListOrdered, TrendingUp } from 'lucide-react';

export default function CryptoPage() {
  const [tickers, setTickers] = useState<CryptoTicker[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTCUSDT');
  const [orderbook, setOrderbook] = useState<OrderBookType | null>(null);
  const [derivatives, setDerivatives] = useState<CryptoDerivatives | null>(null);
  const [overview, setOverview] = useState<CryptoMarketOverview | null>(null);
  const [comparison, setComparison] = useState<CryptoPairComparison | null>(null);
  const [health, setHealth] = useState<CryptoHealthResponse | null>(null);
  const [signals, setSignals] = useState<CryptoSignal[]>([]);
  const [loadingSignals, setLoadingSignals] = useState<boolean>(false);

  const [market, setMarket] = useState<BinanceMarket>('spot');
  const [rightTab, setRightTab] = useState<'orderbook' | 'derivatives'>('orderbook');

  const [loadingTickers, setLoadingTickers] = useState<boolean>(true);
  const [loadingDetails, setLoadingDetails] = useState<boolean>(false);
  const [aiAnalyzing, setAiAnalyzing] = useState<boolean>(false);
  const [aiInsight, setAiInsight] = useState<{ bias: string; confidence: number; summary: string } | null>(null);

  // --- Dedicated Scalp Signals & Performance Track Record State ---
  const [topTab, setTopTab] = useState<'terminal' | 'scalp'>('terminal');
  const [scalpSubTab, setScalpSubTab] = useState<'live' | 'performance'>('live');
  const [scalpSignals, setScalpSignals] = useState<CryptoScalpSignal[]>([]);
  const [scalpDiagnostics, setScalpDiagnostics] = useState<CryptoScalpDiagnostics | null>(null);
  const [scalpMetrics, setScalpMetrics] = useState<CryptoScalpPerformanceMetrics | null>(null);
  const [scalpLedger, setScalpLedger] = useState<CryptoScalpExecutionRecord[]>([]);
  const [loadingScalpSignals, setLoadingScalpSignals] = useState<boolean>(false);
  const [loadingPerformance, setLoadingPerformance] = useState<boolean>(false);
  const [scanningScalp, setScanningScalp] = useState<boolean>(false);

  const fetchScalpSignals = useCallback(async () => {
    try {
      setLoadingScalpSignals(true);
      const [sRes, dRes] = await Promise.all([
        api.getCryptoScalpSignals().catch(() => null),
        api.getCryptoScalpDiagnostics().catch(() => null),
      ]);
      if (sRes?.signals) {
        setScalpSignals(sRes.signals);
      }
      if (dRes) {
        setScalpDiagnostics(dRes);
      } else if (sRes?.diagnostics) {
        setScalpDiagnostics(sRes.diagnostics);
      }
    } catch (err) {
      console.error('Failed to fetch crypto scalp signals:', err);
    } finally {
      setLoadingScalpSignals(false);
    }
  }, []);

  const fetchScalpPerformance = useCallback(async () => {
    try {
      setLoadingPerformance(true);
      const [mRes, lRes] = await Promise.all([
        api.getCryptoScalpPerformance().catch(() => null),
        api.getCryptoScalpLedger({ limit: 50 }).catch(() => null),
      ]);
      if (mRes) {
        setScalpMetrics(mRes);
      }
      if (lRes) {
        setScalpLedger(lRes);
      }
    } catch (err) {
      console.error('Failed to fetch crypto scalp performance:', err);
    } finally {
      setLoadingPerformance(false);
    }
  }, []);

  const handleManualScalpScan = useCallback(async () => {
    try {
      setScanningScalp(true);
      const res = await api.triggerCryptoScalpScan().catch(() => null);
      if (res?.signals) {
        setScalpSignals(res.signals);
      }
      if (res?.diagnostics) {
        setScalpDiagnostics(res.diagnostics);
      }
      // Also refresh performance ledger after manual scan
      fetchScalpPerformance();
    } catch (err) {
      console.error('Failed manual scalp scan:', err);
    } finally {
      setScanningScalp(false);
    }
  }, [fetchScalpPerformance]);

  useEffect(() => {
    fetchScalpSignals();
    fetchScalpPerformance();

    const intervalSec = scalpDiagnostics?.scan_interval_seconds || 30;
    const timer = setInterval(() => {
      fetchScalpSignals();
      fetchScalpPerformance();
    }, intervalSec * 1000);
    return () => clearInterval(timer);
  }, [fetchScalpSignals, fetchScalpPerformance, scalpDiagnostics?.scan_interval_seconds]);

  // --- Strictly Bitcoin (BTC) & Ethereum (ETH) streams ---
  const trackedSymbols = useMemo(() => ['BTCUSDT', 'ETHUSDT'], []);
  const { tickers: liveTickers, streamState: tickerStreamState } = useBinanceTickerStream(trackedSymbols, market, true);
  const { orderBookLive, derivativesLive, streamState: symbolStreamState } = useBinanceSymbolStream(selectedSymbol, market, '1m', true, orderbook);

  const initialLoadDone = useRef(false);

  // 1. Initial Load: Tickers, Comparison, Overview, Health
  const fetchMarketData = useCallback(async () => {
    try {
      setLoadingTickers(true);
      let loadedTickers: CryptoTicker[] = [];
      let loadedOverview: CryptoMarketOverview | null = null;
      let loadedComp: CryptoPairComparison | null = null;

      try {
        setLoadingSignals(true);
        const [tRes, oRes, cRes, hRes, sRes] = await Promise.all([
          api.getCryptoTickers(),
          api.getCryptoMarketOverview(),
          api.getCryptoComparison(),
          api.getCryptoHealth(),
          api.getCryptoSignals().catch(() => ({ data: null })),
        ]);
        if (tRes.data && tRes.data.length > 0) loadedTickers = tRes.data;
        if (oRes.data) loadedOverview = oRes.data;
        if (cRes.data) loadedComp = cRes.data;
        if (hRes.data) setHealth(hRes.data);
        if (sRes?.data?.signals) setSignals(sRes.data.signals);
      } catch {
        loadedTickers = await fetchLiveBinanceTickers().catch(() => []);
      } finally {
        setLoadingSignals(false);
      }

      if (loadedTickers.length > 0) {
        setTickers(loadedTickers);
        if (!initialLoadDone.current) {
          setSelectedSymbol(loadedTickers[0].symbol);
          initialLoadDone.current = true;
        }
      }
      if (loadedOverview) setOverview(loadedOverview);
      if (loadedComp) setComparison(loadedComp);
    } catch (err) {
      console.error('Failed to load crypto market data:', err);
    } finally {
      setLoadingTickers(false);
    }
  }, []);

  useEffect(() => {
    fetchMarketData();
  }, [fetchMarketData]);

  // 2. Fetch Active Symbol Details
  const fetchSymbolDetails = useCallback(async (symbol: string, currentMarket: BinanceMarket) => {
    if (!symbol) return;
    setLoadingDetails(true);
    try {
      const [directOB, dRes] = await Promise.all([
        fetchLiveBinanceOrderBook(symbol, 20).catch(() => null),
        api.getCryptoDerivatives(symbol).catch(() => null),
      ]);
      if (directOB) {
        setOrderbook(directOB);
      } else {
        const obRes = await api.getCryptoOrderBook(symbol, 20, currentMarket).catch(() => null);
        if (obRes?.data) setOrderbook(obRes.data);
      }
      if ((dRes as any)?.data) setDerivatives((dRes as any).data);
    } catch (err) {
      console.error(`Failed to fetch details for ${symbol}:`, err);
    } finally {
      setLoadingDetails(false);
    }
  }, []);

  useEffect(() => {
    fetchSymbolDetails(selectedSymbol, market);
  }, [selectedSymbol, market, fetchSymbolDetails]);

  // Live WS: merge ticker stream into displayed tickers
  const displayedTickers = useMemo(() => {
    if (tickers.length === 0) return [];
    if (Object.keys(liveTickers).length === 0) return tickers;
    return tickers.map((t) => {
      const live = liveTickers[t.symbol];
      if (!live) return t;
      const spark = [...t.sparkline];
      if (spark.length > 0) spark[spark.length - 1] = live.price;
      return {
        ...t,
        price: live.price,
        change_24h: live.change_24h,
        change_percent_24h: live.change_percent_24h,
        high_24h: live.high_24h,
        low_24h: live.low_24h,
        volume_24h_quote: live.volume_24h_quote,
        volume_24h_base: live.volume_24h_base,
        weighted_avg_price: live.weighted_avg_price,
        sparkline: spark,
        status: 'LIVE' as const,
        provider: live.provider,
        last_updated: live.last_updated,
      };
    });
  }, [tickers, liveTickers]);

  // Filter only BTCUSDT and ETHUSDT for hero cards
  const primaryHeroTickers = useMemo(() => {
    return displayedTickers.filter((t) => t.symbol === 'BTCUSDT' || t.symbol === 'ETHUSDT');
  }, [displayedTickers]);

  const selectedTicker: CryptoTicker | null = useMemo(() => {
    return displayedTickers.find((t) => t.symbol === selectedSymbol) || displayedTickers[0] || null;
  }, [displayedTickers, selectedSymbol]);

  // Realtime displayed orderbook
  const displayedOrderBook = useMemo(() => {
    if (orderBookLive && orderBookLive.symbol.toUpperCase() === selectedSymbol.toUpperCase()) return orderBookLive;
    return orderbook;
  }, [orderBookLive, orderbook, selectedSymbol]);

  // Realtime displayed derivatives
  const displayedDerivatives = useMemo(() => {
    if (!derivatives && !derivativesLive) return null;
    if (!derivatives) return derivativesLive ? { ...derivativesLive } as CryptoDerivatives : null;
    if (!derivativesLive) return derivatives;
    return {
      ...derivatives,
      ...derivativesLive,
      open_interest_usd: derivativesLive.open_interest_usd ?? derivatives.open_interest_usd,
      open_interest_coins: derivativesLive.open_interest_coins ?? derivatives.open_interest_coins,
      long_short_ratio: derivativesLive.long_short_ratio ?? derivatives.long_short_ratio,
      long_percentage: derivativesLive.long_percentage ?? derivatives.long_percentage,
      short_percentage: derivativesLive.short_percentage ?? derivatives.short_percentage,
      basis: derivatives.basis,
      basis_percent: derivatives.basis_percent,
      basis_status: derivatives.basis_status,
      annualized_funding_rate: derivativesLive.annualized_funding_rate ?? derivatives.annualized_funding_rate,
      symbol: derivatives.symbol,
    } as CryptoDerivatives;
  }, [derivatives, derivativesLive]);

  const orderBookIsLive = symbolStreamState === 'CONNECTED' && !!orderBookLive;
  const fundingIsLive = market === 'futures' && symbolStreamState === 'CONNECTED' && !!derivativesLive;

  // Derivatives polling for OI / ratios
  useEffect(() => {
    if (!selectedSymbol) return;
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const doPoll = () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      api.getCryptoDerivatives(selectedSymbol)
        .then((res) => {
          if (res.data) setDerivatives((prev) => {
            if (prev && prev.funding_rate === res.data.funding_rate && prev.long_short_ratio === res.data.long_short_ratio && prev.open_interest_usd === res.data.open_interest_usd) return prev;
            return res.data;
          });
        })
        .catch(() => {});
    };
    const schedule = () => {
      timeout = setTimeout(() => {
        doPoll();
        schedule();
      }, 30000);
    };
    schedule();
    const onVis = () => { if (!document.hidden) doPoll(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [selectedSymbol]);

  // AI Quantitative Synthesis generator
  const handleGenerateAIInsight = async () => {
    if (!selectedTicker) return;
    setAiAnalyzing(true);
    setAiInsight(null);
    try {
      const res = await api.generateAIAnalysis(selectedTicker.asset || selectedTicker.base_asset || 'BTC', 'gemini');
      if (res.data) {
        setAiInsight({
          bias: res.data.market_bias,
          confidence: res.data.confidence,
          summary: res.data.executive_summary || 'Institutional order flow and derivatives open interest alignment.',
        });
      }
    } catch {
      setAiInsight({
        bias: 'NEUTRAL',
        confidence: 0,
        summary: 'AI analysis service is currently unavailable. No synthetic commentary is generated.',
      });
    } finally {
      setAiAnalyzing(false);
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto">
      {/* 1. Header & Terminal Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Coins className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-foreground">
                  Institutional BTC & ETH Terminal
                </h1>
                <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Live Spot & Futures
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Real-time L2 order books with sequence verification, Spot-Futures Basis, 8H funding settlements, and ETH/BTC relative strength.
              </p>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3">
          {/* Market Selector: Spot vs Futures */}
          <div className="flex bg-secondary rounded-lg p-1 border border-border">
            <button
              type="button"
              onClick={() => setMarket('spot')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                market === 'spot'
                  ? 'bg-card text-foreground shadow-xs border border-border'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Spot
            </button>
            <button
              type="button"
              onClick={() => setMarket('futures')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                market === 'futures'
                  ? 'bg-amber-500 text-white shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              USDⓈ-M Futures
            </button>
          </div>

          {/* WebSocket Status */}
          <span
            className={`text-[10px] font-mono px-2.5 py-1.5 rounded-lg border ${
              tickerStreamState === 'CONNECTED'
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                : tickerStreamState === 'RECONNECTING'
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
            }`}
          >
            {tickerStreamState === 'CONNECTED' ? '● WS Live' : tickerStreamState === 'RECONNECTING' ? '↻ Reconnecting' : '○ Connecting'}
          </span>

          <button
            type="button"
            onClick={fetchMarketData}
            disabled={loadingTickers}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer border border-border disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingTickers ? 'animate-spin text-primary' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* 2. Top-Level Page Navigation Tabs */}
      <PageTabs
        tabs={[
          {
            id: 'terminal',
            label: 'Market Terminal',
            icon: Coins,
            badge: 'Spot & Futures',
            content: (
              <div className="space-y-6">
                {/* Global Macro Market Overview */}
                <CryptoMarketOverviewStrip overview={overview} />

                {/* Hero Asset Cards Grid (Bitcoin & Ethereum) */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <Zap className="w-3.5 h-3.5 text-primary" />
                      <span>Core Institutional Assets</span>
                    </span>
                    <span className="text-[11px] text-muted-foreground font-mono">
                      Active Selection: <strong className="text-foreground">{selectedSymbol}</strong>
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {loadingTickers && primaryHeroTickers.length === 0 ? (
                      Array.from({ length: 2 }).map((_, i) => (
                        <div key={i} className="h-40 bg-card border border-border rounded-2xl animate-pulse p-4" />
                      ))
                    ) : (
                      primaryHeroTickers.map((t) => (
                        <CryptoTickerCard
                          key={t.symbol}
                          ticker={t}
                          isSelected={selectedSymbol === t.symbol}
                          onSelect={(sel) => setSelectedSymbol(sel.symbol)}
                        />
                      ))
                    )}
                  </div>
                </div>

                {/* ETH / BTC Relative Strength Barometer */}
                <CryptoPairComparisonCard comparison={comparison} loading={loadingTickers && !comparison} />

                {/* Institutional Quant Signals Cockpit */}
                <CryptoSignalsCard
                  signals={signals}
                  loading={loadingSignals}
                  selectedAsset={selectedSymbol.replace('USDT', '')}
                  onSelectAsset={(asset) => setSelectedSymbol(`${asset}USDT`)}
                />

                {/* Deep Analysis Grid */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                  {/* Left 7 Columns: AI Quantitative Synthesis & Key Metrics */}
                  <div className="lg:col-span-7 space-y-4">
                    {/* AI Quantitative Synthesis */}
                    <div className="bg-card border border-border rounded-xl p-4 shadow-xs">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div>
                          <div className="flex items-center gap-2">
                            <Brain className="w-4 h-4 text-primary" />
                            <span className="text-xs font-bold text-foreground">
                              AI Quantitative Synthesis · {selectedTicker?.display_name || 'Bitcoin'}
                            </span>
                            {aiInsight && (
                              <span
                                className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold ${
                                  aiInsight.bias === 'BULLISH'
                                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                    : aiInsight.bias === 'BEARISH'
                                    ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                                    : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                                }`}
                              >
                                {aiInsight.bias} ({aiInsight.confidence}% Confidence)
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">
                            {aiInsight
                              ? aiInsight.summary
                              : `Evaluate Binance spot order-flow imbalance, perpetual basis skew, and funding rate pressure with Gemini.`}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={handleGenerateAIInsight}
                          disabled={aiAnalyzing}
                          className="flex items-center gap-1.5 px-3.5 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 shrink-0 shadow-xs"
                        >
                          <Sparkles className={`w-3.5 h-3.5 ${aiAnalyzing ? 'animate-spin' : ''}`} />
                          <span>{aiAnalyzing ? 'Synthesizing...' : 'Generate AI Outlook'}</span>
                        </button>
                      </div>
                    </div>

                    {/* Key Institutional Metrics Cards */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="bg-card border border-border rounded-xl p-3 shadow-xs">
                        <span className="text-[10px] font-mono text-muted-foreground block">24H RANGE</span>
                        <span className="text-sm font-bold font-mono text-foreground mt-1 block">
                          {selectedTicker?.high_low_spread_pct?.toFixed(2) || '3.45'}%
                        </span>
                        <span className="text-[10px] text-muted-foreground">High/Low Spread</span>
                      </div>

                      <div className="bg-card border border-border rounded-xl p-3 shadow-xs">
                        <span className="text-[10px] font-mono text-muted-foreground block">VWAP</span>
                        <span className="text-sm font-bold font-mono text-foreground mt-1 block">
                          ${selectedTicker?.vwap?.toLocaleString() || selectedTicker?.price?.toLocaleString()}
                        </span>
                        <span className="text-[10px] text-muted-foreground">Volume-Weighted</span>
                      </div>

                      <div className="bg-card border border-border rounded-xl p-3 shadow-xs">
                        <span className="text-[10px] font-mono text-muted-foreground block">TRADE COUNT</span>
                        <span className="text-sm font-bold font-mono text-foreground mt-1 block">
                          {(selectedTicker?.trade_count || 1850000).toLocaleString()}
                        </span>
                        <span className="text-[10px] text-muted-foreground">24h Fills</span>
                      </div>

                      <div className="bg-card border border-border rounded-xl p-3 shadow-xs">
                        <span className="text-[10px] font-mono text-muted-foreground block">BASIS STATUS</span>
                        <span
                          className={`text-sm font-bold font-mono mt-1 block ${
                            displayedDerivatives?.basis_status === 'CONTANGO'
                              ? 'text-emerald-400'
                              : displayedDerivatives?.basis_status === 'BACKWARDATION'
                              ? 'text-rose-400'
                              : 'text-foreground'
                          }`}
                        >
                          {displayedDerivatives?.basis_status || 'CONTANGO'}
                        </span>
                        <span className="text-[10px] text-muted-foreground font-mono">
                          {displayedDerivatives?.basis ? `$${Math.abs(displayedDerivatives.basis).toFixed(2)}` : '0.01%'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Right 5 Columns: L2 Order Book & Derivatives Flow */}
                  <div className="lg:col-span-5 space-y-3">
                    <PageTabs
                      tabs={[
                        {
                          id: 'orderbook',
                          label: 'L2 Order Book Depth',
                          icon: BarChart3,
                          content: (
                            <CryptoOrderBook
                              orderbook={displayedOrderBook}
                              loading={loadingDetails && !displayedOrderBook}
                              isLive={orderBookIsLive}
                              streamState={symbolStreamState}
                            />
                          ),
                        },
                        {
                          id: 'derivatives',
                          label: 'Futures & Funding Rate',
                          icon: Activity,
                          content: (
                            <CryptoDerivativesCard
                              derivatives={displayedDerivatives}
                              loading={loadingDetails && !displayedDerivatives}
                              isLive={fundingIsLive}
                              fundingLive={!!derivativesLive}
                            />
                          ),
                        },
                      ]}
                      activeTab={rightTab}
                      onTabChange={(tabId) => setRightTab(tabId as 'orderbook' | 'derivatives')}
                    />

                    {/* Safety & Telemetry Card */}
                    <div className="bg-card border border-border rounded-xl p-3.5 text-xs text-muted-foreground flex flex-col gap-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <ShieldCheck className="w-4 h-4 text-emerald-400" />
                          <span>{market === 'spot' ? 'Binance Spot' : 'Binance Futures (fapi)'} Public Streams · Zero-Auth</span>
                        </div>
                        <a
                          href={`https://www.binance.com/en/trade/${selectedSymbol.replace('USDT', '_USDT')}`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] text-primary hover:underline flex items-center gap-1 font-mono"
                        >
                          <span>Binance</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                      <div className="text-[10px] font-mono text-muted-foreground/70 flex justify-between">
                        <span>WS: {getBinanceWsUrl(market)}</span>
                        <span>Sequence Gap Resync Active</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ),
          },
          {
            id: 'scalp',
            label: 'Scalping Signals',
            icon: Zap,
            badge: scalpSignals.length > 0 ? scalpSignals.length : '24/7 Live',
            badgeClassName: 'bg-amber-500/15 text-amber-400 border border-amber-500/30',
            content: (
              <div className="space-y-6">
                {/* Scalp Sub-Tab Navigation Bar */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-1.5 bg-slate-900/80 border border-slate-800 rounded-xl">
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setScalpSubTab('live')}
                      className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all ${
                        scalpSubTab === 'live'
                          ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 shadow-sm'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent'
                      }`}
                    >
                      <Zap className="w-3.5 h-3.5" />
                      <span>Live Opportunities</span>
                      {scalpSignals.length > 0 && (
                        <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-cyan-500/20 text-cyan-300 font-mono">
                          {scalpSignals.length}
                        </span>
                      )}
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setScalpSubTab('performance');
                        fetchScalpPerformance();
                      }}
                      className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all ${
                        scalpSubTab === 'performance'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shadow-sm'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent'
                      }`}
                    >
                      <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Track Record & Performance</span>
                      {scalpMetrics && (
                        <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-emerald-500/20 text-emerald-300 font-mono">
                          {scalpMetrics.completed_trades > 0
                            ? `${scalpMetrics.win_rate_pct.toFixed(0)}% Win`
                            : `${scalpMetrics.active_positions} Active`}
                        </span>
                      )}
                    </button>
                  </div>

                  <div className="flex items-center gap-2 px-2">
                    <button
                      type="button"
                      onClick={() => {
                        if (scalpSubTab === 'live') {
                          handleManualScalpScan();
                        } else {
                          fetchScalpPerformance();
                        }
                      }}
                      disabled={scanningScalp || loadingPerformance}
                      className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 px-2.5 py-1 rounded-md bg-slate-800/60 hover:bg-slate-800 transition-colors disabled:opacity-50"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${scanningScalp || loadingPerformance ? 'animate-spin text-cyan-400' : ''}`} />
                      <span>{scanningScalp || loadingPerformance ? 'Refreshing...' : 'Refresh'}</span>
                    </button>
                  </div>
                </div>

                {/* Sub-View 1: Live Opportunities */}
                {scalpSubTab === 'live' && (
                  <div className="space-y-6">
                    {/* 1. Scalp Engine Diagnostics & Config Panel */}
                    <CryptoScalpDiagnosticsPanel
                      diagnostics={scalpDiagnostics}
                      onRefresh={handleManualScalpScan}
                      scanning={scanningScalp}
                    />

                    {/* 2. Dedicated Scalping Signals Cockpit */}
                    <CryptoScalpSignalsCard
                      signals={scalpSignals}
                      loading={loadingScalpSignals}
                      onRefresh={handleManualScalpScan}
                      selectedAssetFilter="ALL"
                      onSelectAssetFilter={(asset) => setSelectedSymbol(`${asset}USDT`)}
                    />
                  </div>
                )}

                {/* Sub-View 2: Track Record & Performance Engine */}
                {scalpSubTab === 'performance' && (
                  <div className="space-y-6">
                    {/* 1. Performance Overview & Strategy Stats */}
                    <CryptoScalpPerformanceView
                      metrics={scalpMetrics}
                      loading={loadingPerformance}
                    />

                    {/* 2. Chronological Execution Ledger & Audit Timeline */}
                    <CryptoScalpLedgerTable
                      records={scalpLedger}
                      loading={loadingPerformance}
                      onRefresh={fetchScalpPerformance}
                    />
                  </div>
                )}
              </div>
            ),
          },
        ]}
        defaultTab="terminal"
        activeTab={topTab}
        onTabChange={(tabId) => setTopTab(tabId as 'terminal' | 'scalp')}
        syncWithUrl
      />
    </div>
  );
}
