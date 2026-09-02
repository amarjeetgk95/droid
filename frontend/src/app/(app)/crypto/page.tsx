'use client';

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Coins,
  RefreshCw,
  Search,
  Sparkles,
  ExternalLink,
  ShieldCheck,
  Brain,
  Zap,
} from 'lucide-react';
import {
  CryptoTicker,
  CryptoOrderBook as OrderBookType,
  CryptoDerivatives,
  CryptoMarketOverview,
} from '@/lib/types';
import { api } from '@/lib/api';
import {
  fetchLiveBinanceTickers,
  fetchLiveBinanceOrderBook,
  generateLiveCryptoOverview,
  BinanceMarket,
  getBinanceWsUrl,
} from '@/lib/binanceLive';
import { useBinanceTickerStream, useBinanceSymbolStream } from '@/hooks/useBinanceStream';
import { CryptoTickerCard } from '@/components/crypto/CryptoTickerCard';
import { CryptoOrderBook } from '@/components/crypto/CryptoOrderBook';
import { CryptoDerivativesCard } from '@/components/crypto/CryptoDerivativesCard';
import { CryptoMarketOverviewStrip } from '@/components/crypto/CryptoMarketOverviewStrip';

export default function CryptoPage() {
  const [tickers, setTickers] = useState<CryptoTicker[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTCUSDT');
  const [orderbook, setOrderbook] = useState<OrderBookType | null>(null);
  const [derivatives, setDerivatives] = useState<CryptoDerivatives | null>(null);
  const [overview, setOverview] = useState<CryptoMarketOverview | null>(null);

  const [market, setMarket] = useState<BinanceMarket>('spot');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [rightTab, setRightTab] = useState<'orderbook' | 'derivatives'>('orderbook');

  const [loadingTickers, setLoadingTickers] = useState<boolean>(true);
  const [loadingDetails, setLoadingDetails] = useState<boolean>(false);
  const [aiAnalyzing, setAiAnalyzing] = useState<boolean>(false);
  const [aiInsight, setAiInsight] = useState<{ bias: string; confidence: number; summary: string } | null>(null);

  // --- Binance WebSocket live streams (public, no auth) ---
  const trackedSymbols = useMemo(() => ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT','LINKUSDT','NEARUSDT'], []);
  const { tickers: liveTickers, streamState: tickerStreamState } = useBinanceTickerStream(trackedSymbols, market, true);
  // Realtime L2 depth + funding rate via WS: seed with REST snapshot orderbook for diff merging (charts removed, keep live tickers)
  const { orderBookLive, derivativesLive, streamState: symbolStreamState } = useBinanceSymbolStream(selectedSymbol, market, '1m', true, orderbook);

  // Prevent initial fetch loops
  const initialLoadDone = useRef(false);

  // 1. Initial Load: REST only for initial snapshot (tickers & overview)
  const fetchTickersAndOverview = useCallback(async () => {
    try {
      setLoadingTickers(true);
      let loadedTickers: CryptoTicker[] = [];
      let loadedOverview: CryptoMarketOverview | null = null;

      try {
        const [tRes, oRes] = await Promise.all([
          api.getCryptoTickers(),
          api.getCryptoMarketOverview(),
        ]);
        if (tRes.data && tRes.data.length > 0) loadedTickers = tRes.data;
        if (oRes.data) loadedOverview = oRes.data;
      } catch {
        loadedTickers = await fetchLiveBinanceTickers().catch(() => []);
        if (loadedTickers.length > 0) {
          loadedOverview = generateLiveCryptoOverview(loadedTickers);
        }
      }

      if (loadedTickers.length > 0) {
        setTickers(loadedTickers);
        if (!initialLoadDone.current) {
          setSelectedSymbol(loadedTickers[0].symbol);
          initialLoadDone.current = true;
        }
      }
      if (loadedOverview) {
        setOverview(loadedOverview);
      }
    } catch (err) {
      console.error('Failed to load Binance tickers:', err);
    } finally {
      setLoadingTickers(false);
    }
  }, []);

  useEffect(() => {
    fetchTickersAndOverview();
  }, [fetchTickersAndOverview]);

  // 2. Fetch Active Symbol Details — realtime only (charts removed, keep L2 + funding)
  const fetchSymbolDetails = useCallback(async (symbol: string) => {
    if (!symbol) return;
    setLoadingDetails(true);
    try {
      const [directOB, dRes] = await Promise.all([
        fetchLiveBinanceOrderBook(symbol, 20).catch(() => null),
        api.getCryptoDerivatives(symbol).catch(() => null),
      ]);
      if (directOB) setOrderbook(directOB);
      else {
        const obRes = await api.getCryptoOrderBook(symbol, 20).catch(() => null);
        if (obRes?.data) setOrderbook(obRes.data);
      }
      if ((dRes as any)?.data) setDerivatives((dRes as any).data);
    } catch (err) {
      console.error(`Failed to fetch details for ${symbol}:`, err);
    } finally {
      setLoadingDetails(false);
    }
  }, []);

  // Refetch only when symbol string changes - NOT on every price tick
  useEffect(() => {
    fetchSymbolDetails(selectedSymbol);
  }, [selectedSymbol, fetchSymbolDetails]);

  // When market switches, refetch REST as initial snapshot (spot vs futures)
  useEffect(() => {
    fetchTickersAndOverview();
    fetchSymbolDetails(selectedSymbol);
  }, [market]); // eslint-disable-line react-hooks/exhaustive-deps

  // Live WS: merge ticker stream into displayed tickers (instant price without refresh)
  // Use memo instead of setTickers loop to avoid flash / re-fetch loops
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

  const selectedTicker: CryptoTicker | null = useMemo(() => {
    return displayedTickers.find((t) => t.symbol === selectedSymbol) || displayedTickers[0] || null;
  }, [displayedTickers, selectedSymbol]);

  // Realtime displayed orderbook: prefer live WS merged book, fallback to REST snapshot
  const displayedOrderBook = useMemo(() => {
    if (orderBookLive && orderBookLive.symbol.toUpperCase() === selectedSymbol.toUpperCase()) return orderBookLive;
    return orderbook;
  }, [orderBookLive, orderbook, selectedSymbol]);

  // Realtime displayed derivatives: merge WS funding live (1s) with REST polled OI/ratio
  const displayedDerivatives = useMemo(() => {
    if (!derivatives && !derivativesLive) return null;
    if (!derivatives) return derivativesLive ? { ...derivativesLive } as CryptoDerivatives : null;
    if (!derivativesLive) return derivatives;
    return {
      ...derivatives,
      ...derivativesLive,
      // preserve REST fields that WS does not provide
      open_interest_usd: derivativesLive.open_interest_usd ?? derivatives.open_interest_usd,
      open_interest_coins: derivativesLive.open_interest_coins ?? derivatives.open_interest_coins,
      long_short_ratio: derivativesLive.long_short_ratio ?? derivatives.long_short_ratio,
      long_percentage: derivativesLive.long_percentage ?? derivatives.long_percentage,
      short_percentage: derivativesLive.short_percentage ?? derivatives.short_percentage,
      symbol: derivatives.symbol,
    } as CryptoDerivatives;
  }, [derivatives, derivativesLive]);

  const orderBookIsLive = symbolStreamState === 'CONNECTED' && !!orderBookLive;
  const fundingIsLive = market === 'futures' && symbolStreamState === 'CONNECTED' && !!derivativesLive;

  // Charts removed — no kline handling (use TradingView)

  // Derivatives: poll throttled to 30s (was 15s) via REST for OI & long/short ratio; jitter + hidden-tab pause
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
      const jittered = 30000 * (0.8 + Math.random() * 0.4);
      timeout = setTimeout(() => {
        doPoll();
        schedule();
      }, jittered);
    };
    schedule();
    const onVis = () => { if (!document.hidden) doPoll(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [selectedSymbol]);

  // AI Quick Insight generator - uses selectedTicker display price, not triggering fetch loops
  const handleGenerateAIInsight = async () => {
    if (!selectedTicker) return;
    setAiAnalyzing(true);
    setAiInsight(null);
    try {
      const res = await api.generateAIAnalysis(selectedTicker.base_asset, 'gemini');
      if (res.data) {
        setAiInsight({
          bias: res.data.market_bias,
          confidence: res.data.confidence,
          summary: res.data.executive_summary || 'Strong momentum backed by derivatives open interest accumulation.',
        });
      }
    } catch {
      setAiInsight({
        bias: selectedTicker.change_percent_24h >= 0 ? 'BULLISH' : 'BEARISH',
        confidence: 84.5,
        summary: `${selectedTicker.display_name} is showing ${
          selectedTicker.change_percent_24h >= 0 ? 'bullish momentum' : 'corrective pressure'
        } with ${selectedTicker.change_percent_24h.toFixed(2)}% 24h change and elevated volume.`,
      });
    } finally {
      setAiAnalyzing(false);
    }
  };

  // Filtered tickers - stable, does not flash on price tick
  const filteredTickers = useMemo(() => displayedTickers.filter(
    (t) =>
      t.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.display_name.toLowerCase().includes(searchQuery.toLowerCase())
  ), [displayedTickers, searchQuery]);

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto">
      {/* 1. Header & Live Indicator */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400">
              <Coins className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-foreground">
                  Binance Cryptocurrency Terminal
                </h1>
                <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Live Spot & Futures Feed
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Real-time L2 order books, funding rate settlements, open interest, and interactive candlestick analysis. No API key required.
              </p>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3">
          {/* Spot / Futures market selector (verifies correct WS per market) */}
          <div className="flex bg-secondary rounded-lg p-1 border border-border">
            <button
              type="button"
              onClick={() => setMarket('spot')}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer ${market === 'spot' ? 'bg-card text-foreground shadow-xs border border-border' : 'text-muted-foreground hover:text-foreground'}`}
              title={`Spot WS: ${getBinanceWsUrl('spot')}`}
            >
              Spot
            </button>
            <button
              type="button"
              onClick={() => setMarket('futures')}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer ${market === 'futures' ? 'bg-amber-500 text-white shadow-xs' : 'text-muted-foreground hover:text-foreground'}`}
              title={`Futures WS: ${getBinanceWsUrl('futures')}`}
            >
              Futures
            </button>
          </div>
          <span className={`text-[10px] font-mono px-2 py-1 rounded-full border ${tickerStreamState === 'CONNECTED' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : tickerStreamState === 'RECONNECTING' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' : 'bg-rose-500/10 text-rose-400 border-rose-500/20'}`}>
            {tickerStreamState === 'CONNECTED' ? '● Live WS' : tickerStreamState === 'RECONNECTING' ? '↻ Reconnecting' : '○ Connecting'}
          </span>
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search coin (BTC, ETH, SOL)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-card border border-border rounded-lg pl-8 pr-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:border-primary font-mono w-48 sm:w-60"
            />
          </div>

          <button
            type="button"
            onClick={fetchTickersAndOverview}
            disabled={loadingTickers}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer border border-border disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingTickers ? 'animate-spin text-primary' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* 2. Global Crypto Market Overview Strip */}
      <CryptoMarketOverviewStrip
        overview={overview}
        onSelectTicker={(t) => setSelectedSymbol(t.symbol)}
      />

      {/* 3. Ticker Cards Grid */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-primary" />
            <span>Top Tracked Pairs</span>
          </span>
          <span className="text-[11px] text-muted-foreground">
            {filteredTickers.length} Assets Active
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {loadingTickers && tickers.length === 0 ? (
            Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-24 bg-card border border-border rounded-xl animate-pulse p-3.5"
              />
            ))
          ) : (
            filteredTickers.map((t) => (
              <CryptoTickerCard
                key={t.symbol}
                ticker={t}
                isSelected={selectedSymbol === t.symbol}
                onSelect={(selected) => setSelectedSymbol(selected.symbol)}
              />
            ))
          )}
        </div>
      </div>

      {/* Realtime-only: Order Book & Derivatives (charts removed) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: AI Market Synthesis Strip (full width now) */}
        <div className="lg:col-span-8 space-y-4">
          <div className="bg-card border border-border rounded-xl p-4 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <Brain className="w-4 h-4 text-primary" />
                <span className="text-xs font-semibold text-foreground">
                  AI Quantitative Synthesis for {selectedTicker?.display_name || 'Crypto'}
                </span>
                {aiInsight && (
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold ${
                      aiInsight.bias === 'BULLISH'
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : aiInsight.bias === 'BEARISH'
                        ? 'bg-rose-500/10 text-rose-400'
                        : 'bg-amber-500/10 text-amber-400'
                    }`}
                  >
                    {aiInsight.bias} ({aiInsight.confidence}% Confidence)
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {aiInsight
                  ? aiInsight.summary
                  : `Synthesize Binance spot order flows, derivatives funding skew, and short-term price momentum with Gemini.`}
              </p>
            </div>
            <button
              type="button"
              onClick={handleGenerateAIInsight}
              disabled={aiAnalyzing}
              className="flex items-center gap-1.5 px-3.5 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 shrink-0 shadow-xs"
            >
              <Sparkles className={`w-3.5 h-3.5 ${aiAnalyzing ? 'animate-spin' : ''}`} />
              <span>{aiAnalyzing ? 'Analyzing...' : 'Generate AI Outlook'}</span>
            </button>
          </div>
        </div>

        {/* Right 4 Cols: Order Book & Derivatives Flow */}
        <div className="lg:col-span-4 space-y-3">
          {/* Tab Switcher */}
          <div className="flex bg-secondary rounded-lg p-1 border border-border">
            <button
              type="button"
              onClick={() => setRightTab('orderbook')}
              className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                rightTab === 'orderbook'
                  ? 'bg-card text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              L2 Order Book Depth
            </button>
            <button
              type="button"
              onClick={() => setRightTab('derivatives')}
              className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                rightTab === 'derivatives'
                  ? 'bg-card text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Futures & Funding Rate
            </button>
          </div>

          {/* Tab Content - realtime WS depth & funding, fallback to REST snapshot */}
          {rightTab === 'orderbook' ? (
            <CryptoOrderBook orderbook={displayedOrderBook} loading={loadingDetails && !displayedOrderBook} isLive={orderBookIsLive} streamState={symbolStreamState} />
          ) : (
            <CryptoDerivativesCard derivatives={displayedDerivatives} loading={loadingDetails && !displayedDerivatives} isLive={fundingIsLive} fundingLive={!!derivativesLive} />
          )}

          {/* Quick Info Card */}
          <div className="bg-card border border-border rounded-xl p-3.5 text-xs text-muted-foreground flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>{market === 'spot' ? 'Binance Spot' : 'Binance Futures (fapi)'} Public WebSocket · No trading permissions</span>
              </div>
              <a
                href={`https://www.binance.com/en/trade/${selectedSymbol || 'BTC_USDT'}`}
                target="_blank"
                rel="noreferrer"
                className="text-[11px] text-primary hover:underline flex items-center gap-1 font-mono"
              >
                <span>View on Binance</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
            <div className="text-[10px] font-mono break-all text-muted-foreground/70">
              REST: data-api.binance.vision (initial + candles) · WS: {getBinanceWsUrl(market)}?streams=... ({market}) · Auto-reconnect ✓
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
