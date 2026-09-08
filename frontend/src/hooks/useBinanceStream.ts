'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import {
  BinanceMarket,
  buildTickerStreams,
  buildDepthStreams,
  buildKlineStreams,
  buildMarkPriceStreams,
  buildBinanceCombinedUrl,
} from '@/lib/binanceLive';
import type { CryptoTicker, CryptoOrderBook, CryptoDerivatives, NormalizedCandle } from '@/lib/types';

const PAIR_DISPLAY_NAMES: Record<string, [string, string, string]> = {
  BTCUSDT: ['Bitcoin', 'BTC', 'USDT'],
  ETHUSDT: ['Ethereum', 'ETH', 'USDT'],
  ETHBTC: ['Ethereum / Bitcoin', 'ETH', 'BTC'],
};

type BinanceTickerPayload = Record<string, unknown>;

function numField(data: BinanceTickerPayload, ...keys: string[]): number {
  for (const k of keys) {
    const v = data[k];
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    if (typeof v === 'string' && v !== '') {
      const n = parseFloat(v);
      if (Number.isFinite(n)) return n;
    }
  }
  return 0;
}

function strField(data: BinanceTickerPayload, ...keys: string[]): string {
  for (const k of keys) {
    const v = data[k];
    if (typeof v === 'string' && v !== '') return v;
  }
  return '';
}

function asPairArray(v: unknown): Array<[string, string]> {
  if (!Array.isArray(v)) return [];
  const out: Array<[string, string]> = [];
  for (const item of v) {
    if (Array.isArray(item) && item.length >= 2) out.push([String(item[0]), String(item[1])]);
  }
  return out;
}

function normalizeTickerData(data: BinanceTickerPayload): Partial<CryptoTicker> & { symbol: string } {
  const symbol = strField(data, 's', 'symbol').toUpperCase();
  const price = numField(data, 'c', 'lastPrice');
  // Binance ticker: c=lastPrice, P=priceChangePercent, p=priceChange, h=high, l=low, v=volume, q=quoteVolume, w=weightedAvg
  const priceChange = numField(data, 'p', 'priceChange');
  const priceChangePercent = numField(data, 'P', 'priceChangePercent');
  // Never fabricate: missing high/low/wavg stay 0 (unavailable) so the UI
  // renders an explicit unavailable state instead of a plausible ±2% band.
  const high = numField(data, 'h', 'highPrice');
  const low = numField(data, 'l', 'lowPrice');
  const volQuote = numField(data, 'q', 'quoteVolume');
  const volBase = numField(data, 'v', 'volume');
  const wavg = numField(data, 'w', 'weightedAvgPrice');

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

  const connect = useCallback(function connectFn() {
    if (!enabledRef.current || typeof window === 'undefined') return;
    if (symbolsRef.current.length === 0) return;

    const m = marketRef.current;
    const syms = symbolsRef.current;

    const streams = buildTickerStreams(syms);
    const url = buildBinanceCombinedUrl(m, streams);

    let isUnmounted = false;

    const scheduleReconnect = () => {
      if (isUnmounted || !enabledRef.current) return;
      setStreamState('RECONNECTING');
      setReconnectCount((c) => c + 1);
      const delay = Math.min(30000, backoffRef.current * 1.5 + Math.random() * 500);
      backoffRef.current = delay;
      reconnectTimeoutRef.current = setTimeout(() => connectFn(), delay);
    };

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
          const payload = JSON.parse(event.data) as {
            stream?: string;
            data?: BinanceTickerPayload;
            e?: string;
            s?: string;
          } & BinanceTickerPayload;
          // Combined stream envelope: {stream:"btcusdt@ticker", data:{...}}
          let data: BinanceTickerPayload | null = null;
          if (payload.stream && payload.data) {
            data = payload.data;
          } else if (payload.e === '24hrTicker' || payload.s) {
            data = payload;
          } else if (Array.isArray(payload)) {
            // !ticker@arr batch
            (payload as BinanceTickerPayload[]).forEach((item) => {
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

          if (!data || !strField(data, 's')) return;
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
        scheduleReconnect();
      };
    } catch {
      scheduleReconnect();
    }

    return () => {
      isUnmounted = true;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        try { wsRef.current.close(); } catch {}
      }
    };
  }, []);

  const symbolsKey = [...symbols].sort().join(',');

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connect, market, enabled, symbolsKey]);

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

  // Seed live orderbook from REST snapshot so diffs can be merged realtime.
  // External REST → WS state sync — intentional, not derived render state.
  useEffect(() => {
    if (initialOrderBook && symbol && initialOrderBook.symbol.toUpperCase() === symbol.toUpperCase()) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setOrderBook(initialOrderBook);
    }
  }, [initialOrderBook, symbol]);

  // Reset derivatives overlay when symbol/market changes to avoid stale funding display.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDerivativesLive(null);
  }, [symbol, market]);

  useEffect(() => {
    if (!enabled || !symbol || typeof window === 'undefined') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
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
            const payload = JSON.parse(event.data) as {
              stream?: string;
              data?: BinanceTickerPayload;
              e?: string;
            } & BinanceTickerPayload;
            let stream: string = typeof payload.stream === 'string' ? payload.stream : '';
            let data: BinanceTickerPayload | null = null;
            if (payload.stream && payload.data) {
              stream = payload.stream;
              data = payload.data;
            } else {
              data = payload;
            }
            if (!data) return;

            const evt = typeof data.e === 'string' ? data.e : '';
            if (evt === 'depthUpdate' || stream.includes('@depth')) {
              const bidsRaw = asPairArray(data.b ?? data.bids ?? data.B);
              const asksRaw = asPairArray(data.a ?? data.asks ?? data.A);
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

                // Recompute cumulative totals and notional for depth bars
                let runNotional = 0;
                let runQty = 0;
                const bids = sortedBids.map((lvl) => {
                  const notional = lvl.price * lvl.quantity;
                  runNotional += notional;
                  runQty += lvl.quantity;
                  return {
                    price: lvl.price,
                    quantity: lvl.quantity,
                    total: parseFloat(runNotional.toFixed(2)),
                    notional: parseFloat(notional.toFixed(2)),
                    cumulative_quantity: parseFloat(runQty.toFixed(4)),
                    cumulative_notional: parseFloat(runNotional.toFixed(2)),
                  };
                });
                const totalBidNotional = runNotional;

                runNotional = 0;
                runQty = 0;
                const asks = sortedAsks.map((lvl) => {
                  const notional = lvl.price * lvl.quantity;
                  runNotional += notional;
                  runQty += lvl.quantity;
                  return {
                    price: lvl.price,
                    quantity: lvl.quantity,
                    total: parseFloat(runNotional.toFixed(2)),
                    notional: parseFloat(notional.toFixed(2)),
                    cumulative_quantity: parseFloat(runQty.toFixed(4)),
                    cumulative_notional: parseFloat(runNotional.toFixed(2)),
                  };
                });
                const totalAskNotional = runNotional;

                const bestBid = bids[0]?.price ?? 0;
                const bestAsk = asks[0]?.price ?? 0;
                const mid = bestBid > 0 && bestAsk > 0 ? (bestBid + bestAsk) / 2.0 : bestBid;
                const spread = Math.max(0, bestAsk - bestBid);
                const spreadPercent = bestAsk > 0 ? (spread / bestAsk) * 100 : 0;
                const imbalance = totalBidNotional - totalAskNotional;
                const totalDepth = totalBidNotional + totalAskNotional;
                const imbalancePct = totalDepth > 0 ? (imbalance / totalDepth) * 100 : 0;

                return {
                  ...prev,
                  bids,
                  asks,
                  best_bid: bestBid,
                  best_ask: bestAsk,
                  mid_price: parseFloat(mid.toFixed(2)),
                  spread: parseFloat(spread.toFixed(4)),
                  spread_percent: parseFloat(spreadPercent.toFixed(4)),
                  bid_depth_total: parseFloat(totalBidNotional.toFixed(2)),
                  ask_depth_total: parseFloat(totalAskNotional.toFixed(2)),
                  depth_imbalance: parseFloat(imbalance.toFixed(2)),
                  depth_imbalance_pct: parseFloat(imbalancePct.toFixed(2)),
                  sequence_status: 'ACTIVE' as const,
                  status: 'LIVE' as const,
                  timestamp: new Date().toISOString(),
                  provider: `binance_${market}_ws`,
                };
              });
            } else if (evt === 'kline' || stream.includes('@kline')) {
              const kRaw = data.k;
              const k: BinanceTickerPayload = typeof kRaw === 'object' && kRaw !== null ? (kRaw as BinanceTickerPayload) : data;
              const tsRaw = numField(k, 't', 'T');
              const candle: NormalizedCandle = {
                timestamp: new Date(tsRaw > 0 ? tsRaw : Date.now()).toISOString(),
                open: numField(k, 'o', 'open'),
                high: numField(k, 'h', 'high'),
                low: numField(k, 'l', 'low'),
                close: numField(k, 'c', 'close'),
                volume: numField(k, 'v', 'volume'),
                vwap: null,
              };
              setLatestCandle(candle);
            } else if (evt === 'markPriceUpdate' || stream.includes('@markPrice')) {
              const markPrice = numField(data, 'p', 'markPrice');
              const indexPrice = numField(data, 'i', 'indexPrice', 'P');
              const fundingRate = numField(data, 'r', 'lastFundingRate');
              const nextFundingMs: number = numField(data, 'T', 'nextFundingTime');
              if (!Number.isFinite(fundingRate)) return;
              const nowMs = Date.now();
              const countdown = nextFundingMs > 0 ? Math.max(0, Math.floor((nextFundingMs - nowMs) / 1000)) : 0;
              const nextFundingIso = nextFundingMs > 0 ? new Date(nextFundingMs).toISOString() : new Date(nowMs + 8 * 3600 * 1000).toISOString();
              setDerivativesLive({
                symbol: (strField(data, 's') || symbol || '').toUpperCase(),
                mark_price: markPrice || undefined,
                index_price: indexPrice || undefined,
                funding_rate: fundingRate,
                funding_rate_percent: parseFloat((fundingRate * 100).toFixed(4)),
                annualized_funding_rate: parseFloat((fundingRate * 3 * 365 * 100).toFixed(4)),
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
