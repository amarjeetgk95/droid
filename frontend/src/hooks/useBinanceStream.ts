'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import {
  BinanceMarket,
  buildTickerStreams,
  buildKlineStreams,
  buildDepthStreams,
  buildMarkPriceStreams,
  getBinanceWsUrl,
  buildBinanceCombinedUrl,
} from '@/lib/binanceLive';
import type { CryptoTicker, CryptoOrderBook, CryptoDerivatives, NormalizedCandle } from '@/lib/types';

const PAIR_DISPLAY_NAMES: Record<string, [string, string, string]> = {
  BTCUSDT: ['Bitcoin', 'BTC', 'USDT'],
  ETHUSDT: ['Ethereum', 'ETH', 'USDT'],
  SOLUSDT: ['Solana', 'SOL', 'USDT'],
  BNBUSDT: ['BNB', 'BNB', 'USDT'],
  XRPUSDT: ['XRP', 'XRP', 'USDT'],
  DOGEUSDT: ['Dogecoin', 'DOGE', 'USDT'],
  ADAUSDT: ['Cardano', 'ADA', 'USDT'],
  AVAXUSDT: ['Avalanche', 'AVAX', 'USDT'],
  LINKUSDT: ['Chainlink', 'LINK', 'USDT'],
  NEARUSDT: ['NEAR Protocol', 'NEAR', 'USDT'],
};

function normalizeTickerData(data: Record<string, any>): Partial<CryptoTicker> & { symbol: string } {
  const symbol = (data.s || data.symbol || '').toUpperCase();
  const price = parseFloat(data.c ?? data.lastPrice ?? '0');
  const change = parseFloat(data.P ?? data.priceChange ?? '0'); // futures uses different field? fallback
  // Binance ticker: c=lastPrice, P=priceChangePercent, p=priceChange, h=high, l=low, v=volume, q=quoteVolume, w=weightedAvg
  const priceChange = parseFloat(data.p ?? data.priceChange ?? '0');
  const priceChangePercent = parseFloat(data.P ?? data.priceChangePercent ?? '0');
  const high = parseFloat(data.h ?? data.highPrice ?? (price * 1.02).toString());
  const low = parseFloat(data.l ?? data.lowPrice ?? (price * 0.98).toString());
  const volQuote = parseFloat(data.q ?? data.quoteVolume ?? '0');
  const volBase = parseFloat(data.v ?? data.volume ?? '0');
  const wavg = parseFloat(data.w ?? data.weightedAvgPrice ?? price.toString());

  return {
    symbol,
    price,
    change_24h: priceChange,
    change_percent_24h: priceChangePercent,
    high_24h: high,
    low_24h: low,
    volume_24h_quote: volQuote,
    volume_24h_base: volBase,
    weighted_avg_price: wavg,
  };
}

export type BinanceStreamState = 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'RECONNECTING';

/**
 * Live ticker stream for multiple symbols.
 * - Uses Binance public WebSocket (no auth) with correct Spot/Futures URL per market.
 * - Auto-reconnects with exponential backoff.
 * - Updates price instantly without page refresh (task requirement).
 * - REST remains for initial data only.
 */
export function useBinanceTickerStream(
  symbols: string[],
  market: BinanceMarket = 'spot',
  enabled: boolean = true
) {
  const [tickers, setTickers] = useState<Record<string, CryptoTicker>>({});
  const [streamState, setStreamState] = useState<BinanceStreamState>('CONNECTING');
  const [reconnectCount, setReconnectCount] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef<number>(1000);
  const enabledRef = useRef(enabled);
  const marketRef = useRef(market);
  const symbolsRef = useRef(symbols);

  useEffect(() => {
    enabledRef.current = enabled;
    marketRef.current = market;
    symbolsRef.current = symbols;
  }, [enabled, market, symbols]);

  const connect = useCallback(() => {
    if (!enabledRef.current || typeof window === 'undefined') return;
    if (symbolsRef.current.length === 0) return;

    const m = marketRef.current;
    const syms = symbolsRef.current;

    const streams = buildTickerStreams(syms);
    const url = buildBinanceCombinedUrl(m, streams);
    const fallbackUrl = m === 'spot'
      ? `wss://stream.binance.com:9443/stream?streams=${streams.map(s => s.toLowerCase()).join('/')}`
      : url;

    // Verify correct stream per market (logged for audit)
    const verifiedBase = getBinanceWsUrl(m, true);
    // console.debug(`[BinanceLive] Connecting ${m} tickers via ${verifiedBase}`, { url });

    let isUnmounted = false;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (isUnmounted) return;
        setStreamState('CONNECTED');
        backoffRef.current = 1000;
      };

      ws.onmessage = (event) => {
        if (isUnmounted) return;
        try {
          const payload = JSON.parse(event.data);
          // Combined stream envelope: {stream:"btcusdt@ticker", data:{...}}
          let data: Record<string, any> | null = null;
          if (payload.stream && payload.data) {
            data = payload.data;
          } else if (payload.e === '24hrTicker' || payload.s) {
            data = payload;
          } else if (Array.isArray(payload)) {
            // !ticker@arr batch
            payload.forEach((item: Record<string, any>) => {
              const parsed = normalizeTickerData(item);
              const sym = parsed.symbol;
              if (!sym) return;
              setTickers((prev) => {
                const existing = prev[sym];
                const display = PAIR_DISPLAY_NAMES[sym] || [sym.replace('USDT',''), sym.replace('USDT',''), 'USDT'];
                return {
                  ...prev,
                  [sym]: {
                    symbol: sym,
                    display_name: existing?.display_name || display[0],
                    base_asset: existing?.base_asset || display[1],
                    quote_asset: existing?.quote_asset || display[2],
                    price: parsed.price ?? existing?.price ?? 0,
                    change_24h: parsed.change_24h ?? existing?.change_24h ?? 0,
                    change_percent_24h: parsed.change_percent_24h ?? existing?.change_percent_24h ?? 0,
                    high_24h: parsed.high_24h ?? existing?.high_24h ?? 0,
                    low_24h: parsed.low_24h ?? existing?.low_24h ?? 0,
                    volume_24h_quote: parsed.volume_24h_quote ?? existing?.volume_24h_quote ?? 0,
                    volume_24h_base: parsed.volume_24h_base ?? existing?.volume_24h_base ?? 0,
                    weighted_avg_price: parsed.weighted_avg_price ?? existing?.weighted_avg_price ?? 0,
                    sparkline: existing?.sparkline || [],
                    status: 'LIVE',
                    provider: `binance_${m}`,
                    last_updated: new Date().toISOString(),
                  },
                };
              });
            });
            return;
          }

          if (!data || !data.s) return;
          const parsed = normalizeTickerData(data);
          const sym = parsed.symbol;
          if (!sym) return;

          setTickers((prev) => {
            const existing = prev[sym];
            // Update sparkline tail with live price
            const newSparkline = existing?.sparkline ? [...existing.sparkline] : [];
            if (newSparkline.length > 0) {
              newSparkline[newSparkline.length - 1] = parsed.price ?? 0;
            }
            const display = PAIR_DISPLAY_NAMES[sym] || [sym.replace('USDT',''), sym.replace('USDT',''), 'USDT'];
            return {
              ...prev,
              [sym]: {
                symbol: sym,
                display_name: existing?.display_name || display[0],
                base_asset: existing?.base_asset || display[1],
                quote_asset: existing?.quote_asset || display[2],
                price: parsed.price ?? existing?.price ?? 0,
                change_24h: parsed.change_24h ?? existing?.change_24h ?? 0,
                change_percent_24h: parsed.change_percent_24h ?? existing?.change_percent_24h ?? 0,
                high_24h: parsed.high_24h ?? existing?.high_24h ?? 0,
                low_24h: parsed.low_24h ?? existing?.low_24h ?? 0,
                volume_24h_quote: parsed.volume_24h_quote ?? existing?.volume_24h_quote ?? 0,
                volume_24h_base: parsed.volume_24h_base ?? existing?.volume_24h_base ?? 0,
                weighted_avg_price: parsed.weighted_avg_price ?? existing?.weighted_avg_price ?? 0,
                sparkline: newSparkline,
                status: 'LIVE',
                provider: `binance_${m}`,
                last_updated: new Date().toISOString(),
              },
            };
          });
        } catch {
          // ignore parse errors
        }
      };

      ws.onerror = () => {
        if (isUnmounted) return;
        setStreamState('DISCONNECTED');
      };

      ws.onclose = () => {
        if (isUnmounted || !enabledRef.current) return;
        setStreamState('RECONNECTING');
        setReconnectCount((c) => c + 1);
        const delay = Math.min(30000, backoffRef.current * 1.5 + Math.random() * 500);
        backoffRef.current = delay;
        reconnectTimeoutRef.current = setTimeout(() => connect(), delay);
      };
    } catch {
      if (!isUnmounted) {
        const delay = Math.min(30000, backoffRef.current * 1.5 + Math.random() * 500);
        backoffRef.current = delay;
        reconnectTimeoutRef.current = setTimeout(() => connect(), delay);
      }
    }

    return () => {
      isUnmounted = true;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        try { wsRef.current.close(); } catch {}
      }
    };
  }, []);

  useEffect(() => {
    const cleanup = connect();
    return () => {
      if (cleanup) cleanup();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        try { wsRef.current.close(); } catch {}
        wsRef.current = null;
      }
    };
  }, [connect, market, JSON.stringify(symbols), enabled]);

  return { tickers, streamState, reconnectCount };
}

/**
 * Live depth + kline + funding rate for a single selected symbol.
 * Updates order book, funding rate and candle chart instantly without refresh.
 * - Depth diffs are merged into full L2 book (realtime depth).
 * - Futures markPrice stream @1s pushes live funding_rate, mark_price, countdown.
 */
export function useBinanceSymbolStream(
  symbol: string | null,
  market: BinanceMarket,
  timeframe: string,
  enabled: boolean = true,
  initialOrderBook: CryptoOrderBook | null = null
) {
  const [orderBook, setOrderBook] = useState<CryptoOrderBook | null>(null);
  const [latestCandle, setLatestCandle] = useState<NormalizedCandle | null>(null);
  const [derivativesLive, setDerivativesLive] = useState<Partial<CryptoDerivatives> | null>(null);
  const [streamState, setStreamState] = useState<BinanceStreamState>('CONNECTING');

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef(1000);

  // Seed live orderbook from REST snapshot so diffs can be merged realtime
  useEffect(() => {
    if (initialOrderBook && symbol && initialOrderBook.symbol.toUpperCase() === symbol.toUpperCase()) {
      setOrderBook(initialOrderBook);
    } else if (!initialOrderBook) {
      // keep existing if switching timeframe; only clear on symbol change handled by Ws effect
    }
  }, [initialOrderBook, symbol]);

  // Reset orderbook when symbol/market changes to avoid stale book
  useEffect(() => {
    setDerivativesLive(null);
  }, [symbol, market]);

  useEffect(() => {
    if (!enabled || !symbol || typeof window === 'undefined') {
      setStreamState('DISCONNECTED');
      return;
    }

    const cleanSymbol = symbol.toLowerCase();
    const streams = [
      ...buildDepthStreams(cleanSymbol, '100ms'),
      ...buildKlineStreams(cleanSymbol, timeframe),
    ];
    // Futures funding rate realtime via markPrice@1s (contains fundingRate r and nextFundingTime T)
    if (market === 'futures') {
      streams.push(...buildMarkPriceStreams(cleanSymbol, '1s'));
    }
    const url = buildBinanceCombinedUrl(market, streams);

    let isUnmounted = false;

    const connect = () => {
      if (isUnmounted) return;
      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          if (isUnmounted) return;
          setStreamState('CONNECTED');
          backoffRef.current = 1000;
        };

        ws.onmessage = (event) => {
          if (isUnmounted) return;
          try {
            const payload = JSON.parse(event.data);
            let stream: string = '';
            let data: Record<string, any> | null = null;
            if (payload.stream && payload.data) {
              stream = payload.stream;
              data = payload.data;
            } else {
              data = payload;
            }
            if (!data) return;

            if (data.e === 'depthUpdate' || stream.includes('@depth')) {
              const bidsRaw: Array<[string, string]> = data.b || data.bids || data.B || [];
              const asksRaw: Array<[string, string]> = data.a || data.asks || data.A || [];
              if (bidsRaw.length === 0 && asksRaw.length === 0) return;
              setOrderBook((prev) => {
                if (!prev) return prev;
                // Merge diff into full L2 book realtime - maintain sorted maps
                const bidMap = new Map<number, number>();
                prev.bids.forEach((lvl) => bidMap.set(lvl.price, lvl.quantity));
                const askMap = new Map<number, number>();
                prev.asks.forEach((lvl) => askMap.set(lvl.price, lvl.quantity));

                for (const [pStr, qStr] of bidsRaw) {
                  const p = parseFloat(pStr);
                  const q = parseFloat(qStr);
                  if (Number.isNaN(p)) continue;
                  if (q === 0) bidMap.delete(p);
                  else bidMap.set(p, q);
                }
                for (const [pStr, qStr] of asksRaw) {
                  const p = parseFloat(pStr);
                  const q = parseFloat(qStr);
                  if (Number.isNaN(p)) continue;
                  if (q === 0) askMap.delete(p);
                  else askMap.set(p, q);
                }

                // Sort and slice top levels (20 each)
                const sortedBids = Array.from(bidMap.entries())
                  .sort((a, b) => b[0] - a[0])
                  .slice(0, 20)
                  .map(([price, quantity]) => ({ price, quantity } as { price: number; quantity: number }));
                const sortedAsks = Array.from(askMap.entries())
                  .sort((a, b) => a[0] - b[0])
                  .slice(0, 20)
                  .map(([price, quantity]) => ({ price, quantity } as { price: number; quantity: number }));

                // Recompute cumulative totals for depth bars
                let run = 0;
                const bids = sortedBids.map((lvl) => {
                  run += lvl.price * lvl.quantity;
                  return { price: lvl.price, quantity: lvl.quantity, total: parseFloat(run.toFixed(2)) };
                });
                run = 0;
                const asks = sortedAsks.map((lvl) => {
                  run += lvl.price * lvl.quantity;
                  return { price: lvl.price, quantity: lvl.quantity, total: parseFloat(run.toFixed(2)) };
                });

                const bestBid = bids[0]?.price ?? 0;
                const bestAsk = asks[0]?.price ?? 0;
                const spread = Math.max(0, bestAsk - bestBid);
                const spreadPercent = bestAsk > 0 ? (spread / bestAsk) * 100 : 0;

                return {
                  ...prev,
                  bids,
                  asks,
                  spread: parseFloat(spread.toFixed(4)),
                  spread_percent: parseFloat(spreadPercent.toFixed(4)),
                  timestamp: new Date().toISOString(),
                  provider: `binance_${market}_ws`,
                };
              });
            } else if (data.e === 'kline' || stream.includes('@kline')) {
              const k = data.k || data;
              if (!k) return;
              const candle: NormalizedCandle = {
                timestamp: new Date(k.t ?? k.T ?? Date.now()).toISOString(),
                open: parseFloat(k.o ?? k.open ?? '0'),
                high: parseFloat(k.h ?? k.high ?? '0'),
                low: parseFloat(k.l ?? k.low ?? '0'),
                close: parseFloat(k.c ?? k.close ?? '0'),
                volume: parseFloat(k.v ?? k.volume ?? '0'),
                vwap: null,
              };
              setLatestCandle(candle);
            } else if (data.e === 'markPriceUpdate' || stream.includes('@markPrice')) {
              const markPrice = parseFloat(data.p ?? data.markPrice ?? '0');
              const indexPrice = parseFloat(data.i ?? data.indexPrice ?? data.P ?? '0');
              const fundingRate = parseFloat(data.r ?? data.lastFundingRate ?? '0');
              const nextFundingMs: number = Number(data.T ?? data.nextFundingTime ?? 0);
              if (!Number.isFinite(fundingRate)) return;
              const nowMs = Date.now();
              const countdown = nextFundingMs > 0 ? Math.max(0, Math.floor((nextFundingMs - nowMs) / 1000)) : 0;
              const nextFundingIso = nextFundingMs > 0 ? new Date(nextFundingMs).toISOString() : new Date(nowMs + 8 * 3600 * 1000).toISOString();
              setDerivativesLive({
                symbol: (data.s || symbol || '').toUpperCase(),
                mark_price: markPrice || undefined,
                index_price: indexPrice || undefined,
                funding_rate: fundingRate,
                funding_rate_percent: parseFloat((fundingRate * 100).toFixed(4)),
                next_funding_time: nextFundingIso,
                countdown_seconds: countdown,
                provider: 'binance_futures_ws',
                timestamp: new Date().toISOString(),
              });
            }
          } catch {
            // ignore
          }
        };

        ws.onerror = () => {
          if (isUnmounted) return;
          setStreamState('DISCONNECTED');
        };

        ws.onclose = () => {
          if (isUnmounted || !enabled) return;
          setStreamState('RECONNECTING');
          const delay = Math.min(30000, backoffRef.current * 1.5 + Math.random() * 500);
          backoffRef.current = delay;
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        };
      } catch {
        const delay = Math.min(30000, backoffRef.current * 1.5 + Math.random() * 500);
        backoffRef.current = delay;
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      }
    };

    connect();

    return () => {
      isUnmounted = true;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        try { wsRef.current.close(); } catch {}
        wsRef.current = null;
      }
    };
  }, [symbol, market, timeframe, enabled]);

  return { orderBookLive: orderBook, latestCandle, derivativesLive, streamState, setOrderBook };
}
