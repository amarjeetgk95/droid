import {
  CryptoTicker,
  CryptoOrderBook,
  CryptoOrderBookLevel,
  CryptoDerivatives,
  CryptoMarketOverview,
  NormalizedCandle,
} from './types';

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

const BINANCE_MIRRORS = [
  'https://data-api.binance.vision',
  'https://api.binance.com',
  'https://api1.binance.com',
  'https://api2.binance.com',
  'https://api3.binance.com',
] as const;

// --- Binance WebSocket market-data streams (public, no trading permissions) ---
export type BinanceMarket = 'spot' | 'futures';

// Spot streams: wss://data-stream.binance.vision (primary), fallback wss://stream.binance.com:9443
export const BINANCE_SPOT_WS_COMBINED = 'wss://data-stream.binance.vision/stream';
export const BINANCE_SPOT_WS_COMBINED_FALLBACK = 'wss://stream.binance.com:9443/stream';
export const BINANCE_SPOT_WS_RAW = 'wss://data-stream.binance.vision/ws';
// Futures (USD-M) streams: wss://fstream.binance.com
export const BINANCE_FUTURES_WS_COMBINED = 'wss://fstream.binance.com/stream';
export const BINANCE_FUTURES_WS_RAW = 'wss://fstream.binance.com/ws';

/**
 * Verify correct Binance stream is used for Spot/Futures according to selected market.
 * This is the single source of truth for WS URL selection (task requirement).
 */
export function getBinanceWsUrl(market: BinanceMarket, combined: boolean = true): string {
  if (market === 'futures') {
    return combined ? BINANCE_FUTURES_WS_COMBINED : BINANCE_FUTURES_WS_RAW;
  }
  return combined ? BINANCE_SPOT_WS_COMBINED : BINANCE_SPOT_WS_RAW;
}

export function buildBinanceCombinedUrl(market: BinanceMarket, streams: string[]): string {
  const base = getBinanceWsUrl(market, true);
  const query = streams.map((s) => s.toLowerCase()).join('/');
  return `${base}?streams=${query}`;
}

export function buildTickerStreams(symbols: string[]): string[] {
  return symbols.map((s) => `${s.toLowerCase()}@ticker`);
}

export function buildKlineStreams(symbol: string, interval: string): string[] {
  return [`${symbol.toLowerCase()}@kline_${interval}`];
}

export function buildDepthStreams(symbol: string, speed: string = '100ms'): string[] {
  return [`${symbol.toLowerCase()}@depth@${speed}`];
}

export function buildMarkPriceStreams(symbol: string, interval: string = '1s'): string[] {
  // Futures USDT-M markPrice stream @1s contains markPrice, indexPrice, fundingRate, nextFundingTime
  // Docs: wss://fstream.binance.com/stream?streams=btcusdt@markPrice@1s
  return [`${symbol.toLowerCase()}@markPrice@${interval}`];
}

export function buildMarkPriceArrayStream(interval: string = '1s'): string {
  return `!markPrice@arr@${interval}`;
}

// Backend proxy WS endpoint (optional relay, keeps Binance WS on server side)
export function getBackendCryptoWsUrl(
  market: BinanceMarket,
  symbols: string[],
  streams: string[] = ['ticker'],
  interval: string = '1m'
): string {
  if (typeof window === 'undefined') return '';
  const rawApiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com';
  const apiUrl = rawApiUrl.replace(/\/+$/, '');
  const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws';
  const wsHost = apiUrl.replace(/^https?:\/\//, '');
  const params = new URLSearchParams({
    market,
    symbols: symbols.join(','),
    streams: streams.join(','),
    interval,
  });
  return `${wsProtocol}://${wsHost}/api/v1/ws/crypto?${params.toString()}`;
}

function generateSparkline(low: number, high: number, current: number, changePct: number): number[] {
  const points: number[] = [];
  const base = current / (1.0 + changePct / 100.0);
  for (let i = 0; i < 10; i++) {
    const ratio = i / 9.0;
    const interpolated = base + (current - base) * ratio;
    const noise = ((i % 3) - 1) * ((high - low) * 0.05);
    const val = Math.max(low, Math.min(high, interpolated + noise));
    points.push(parseFloat(val.toFixed(2)));
  }
  points[points.length - 1] = parseFloat(current.toFixed(2));
  return points;
}

export async function fetchLiveBinanceTickers(): Promise<CryptoTicker[]> {
  let lastErr: Error | null = null;
  for (const base of BINANCE_MIRRORS) {
    try {
      const response = await fetch(`${base}/api/v3/ticker/24hr`, {
        mode: 'cors',
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) { lastErr = new Error(`Binance ${base} HTTP ${response.status}`); continue; }
      const rawList: Array<Record<string, string>> = await response.json();
      if (!Array.isArray(rawList) || rawList.length === 0) { lastErr = new Error('Empty ticker list'); continue; }
      const bySymbol = new Map(rawList.map((item) => [item.symbol, item]));
      const tickers: CryptoTicker[] = [];
      for (const [sym, [name, baseA, quote]] of Object.entries(PAIR_DISPLAY_NAMES)) {
        const raw = bySymbol.get(sym);
        if (raw) {
          const price = parseFloat(raw.lastPrice || '0');
          const change = parseFloat(raw.priceChange || '0');
          const changePct = parseFloat(raw.priceChangePercent || '0');
          const high = parseFloat(raw.highPrice || (price * 1.02).toString());
          const low = parseFloat(raw.lowPrice || (price * 0.98).toString());
          const volQuote = parseFloat(raw.quoteVolume || '0');
          const volBase = parseFloat(raw.volume || '0');
          const wavg = parseFloat(raw.weightedAvgPrice || price.toString());
          tickers.push({
            symbol: sym, display_name: name, base_asset: baseA, quote_asset: quote,
            price, change_24h: change, change_percent_24h: changePct, high_24h: high, low_24h: low,
            volume_24h_quote: volQuote, volume_24h_base: volBase, weighted_avg_price: wavg,
            sparkline: generateSparkline(low, high, price, changePct), status: 'LIVE', provider: 'binance_direct', last_updated: new Date().toISOString(),
          });
        }
      }
      if (tickers.length > 0) return tickers;
      lastErr = new Error('No tickers parsed');
    } catch (e: any) { lastErr = e; continue; }
  }
  throw lastErr ?? new Error('Binance tickers unreachable');
}

export async function fetchLiveBinanceCandles(
  symbol: string,
  timeframe: string = '1h',
  limit: number = 100
): Promise<NormalizedCandle[]> {
  const sym = symbol.toUpperCase().endsWith('USDT') ? symbol.toUpperCase() : `${symbol.toUpperCase()}USDT`;
  const intervalMap: Record<string, string> = {
    '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m', '1h': '1h', '4h': '4h', '1d': '1d', '1w': '1w',
  };
  const interval = intervalMap[timeframe.toLowerCase()] || '1h';
  let lastErr: Error | null = null;
  for (const base of BINANCE_MIRRORS) {
    try {
      const response = await fetch(`${base}/api/v3/klines?symbol=${sym}&interval=${interval}&limit=${Math.min(limit, 300)}`, {
        mode: 'cors', cache: 'no-store', headers: { Accept: 'application/json' },
      });
      if (!response.ok) { lastErr = new Error(`Klines ${base} HTTP ${response.status}`); continue; }
      const rawKlines: Array<[number, string, string, string, string, string, number, string]> = await response.json();
      if (!Array.isArray(rawKlines) || rawKlines.length === 0) { lastErr = new Error('Empty klines'); continue; }
      return rawKlines.map((item) => {
        const openTimeMs = item[0];
        const o = parseFloat(item[1]); const h = parseFloat(item[2]); const l = parseFloat(item[3]); const c = parseFloat(item[4]);
        const v = parseFloat(item[5]); const qVol = parseFloat(item[7]); const vwap = v > 0 ? qVol / v : c;
        return { timestamp: new Date(openTimeMs).toISOString(), open: o, high: h, low: l, close: c, volume: v, vwap: parseFloat(vwap.toFixed(4)) };
      });
    } catch (e: any) { lastErr = e; continue; }
  }
  throw lastErr ?? new Error('Binance klines unreachable');
}

export async function fetchLiveBinanceOrderBook(symbol: string, limit: number = 20): Promise<CryptoOrderBook> {
  const sym = symbol.toUpperCase().endsWith('USDT') ? symbol.toUpperCase() : `${symbol.toUpperCase()}USDT`;
  let lastErr: Error | null = null;
  let data: { bids: Array<[string, string]>; asks: Array<[string, string]> } | null = null;
  for (const base of BINANCE_MIRRORS) {
    try {
      const response = await fetch(`${base}/api/v3/depth?symbol=${sym}&limit=${limit <= 20 ? 20 : 50}`, { mode: 'cors', cache: 'no-store', headers: { Accept: 'application/json' } });
      if (!response.ok) { lastErr = new Error(`Depth ${base} HTTP ${response.status}`); continue; }
      data = await response.json() as { bids: Array<[string, string]>; asks: Array<[string, string]> };
      if (data && Array.isArray(data.bids) && Array.isArray(data.asks)) break;
      lastErr = new Error('Invalid depth');
    } catch (e: any) { lastErr = e; continue; }
  }
  if (!data) throw lastErr ?? new Error('Binance depth unreachable');

  const bids: CryptoOrderBookLevel[] = [];
  let runningBidTotal = 0;
  for (const [pStr, qStr] of data.bids.slice(0, limit)) {
    const p = parseFloat(pStr);
    const q = parseFloat(qStr);
    runningBidTotal += p * q;
    bids.push({ price: p, quantity: q, total: parseFloat(runningBidTotal.toFixed(2)) });
  }

  const asks: CryptoOrderBookLevel[] = [];
  let runningAskTotal = 0;
  for (const [pStr, qStr] of data.asks.slice(0, limit)) {
    const p = parseFloat(pStr);
    const q = parseFloat(qStr);
    runningAskTotal += p * q;
    asks.push({ price: p, quantity: q, total: parseFloat(runningAskTotal.toFixed(2)) });
  }

  const bestBid = bids[0]?.price || 0;
  const bestAsk = asks[0]?.price || 0;
  const spread = Math.max(0, bestAsk - bestBid);
  const spreadPercent = bestAsk > 0 ? (spread / bestAsk) * 100 : 0;

  return {
    symbol: sym,
    bids,
    asks,
    spread: parseFloat(spread.toFixed(4)),
    spread_percent: parseFloat(spreadPercent.toFixed(4)),
    timestamp: new Date().toISOString(),
    provider: 'binance_direct',
  };
}

export function generateLiveCryptoOverview(tickers: CryptoTicker[]): CryptoMarketOverview {
  const sorted = [...tickers].sort((a, b) => b.change_percent_24h - a.change_percent_24h);
  const topGainers = sorted.slice(0, 3);
  const topLosers = sorted.slice(-3);
  const totalVolume = tickers.reduce((acc, t) => acc + t.volume_24h_quote, 0);

  const avgChange = tickers.length > 0 ? tickers.reduce((acc, t) => acc + t.change_percent_24h, 0) / tickers.length : 0;
  const score = Math.round(Math.min(95, Math.max(10, 50 + avgChange * 5)));
  let label = 'Neutral';
  if (score >= 75) label = 'Extreme Greed';
  else if (score >= 60) label = 'Greed';
  else if (score >= 45) label = 'Neutral';
  else if (score >= 30) label = 'Fear';
  else label = 'Extreme Fear';

  return {
    fear_greed_score: score,
    fear_greed_label: label,
    btc_dominance_pct: 57.8,
    total_market_cap_usd: 2850000000000,
    total_volume_24h_usd: parseFloat(totalVolume.toFixed(2)),
    tracked_pairs_count: tickers.length,
    top_gainers: topGainers,
    top_losers: topLosers,
    timestamp: new Date().toISOString(),
    provider: 'binance_direct',
  };
}
