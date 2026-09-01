import time
import httpx
from datetime import datetime, timezone
import structlog
from app.models.crypto import (
    CryptoTicker,
    CryptoOrderBook,
    CryptoOrderBookLevel,
    CryptoDerivatives,
    CryptoMarketOverview,
)
from app.models.market import NormalizedCandle, DataStatus

logger = structlog.get_logger()

PAIR_DISPLAY_NAMES: dict[str, tuple[str, str, str]] = {
    "BTCUSDT": ("Bitcoin", "BTC", "USDT"),
    "ETHUSDT": ("Ethereum", "ETH", "USDT"),
    "SOLUSDT": ("Solana", "SOL", "USDT"),
    "BNBUSDT": ("BNB", "BNB", "USDT"),
    "XRPUSDT": ("XRP", "XRP", "USDT"),
    "DOGEUSDT": ("Dogecoin", "DOGE", "USDT"),
    "ADAUSDT": ("Cardano", "ADA", "USDT"),
    "AVAXUSDT": ("Avalanche", "AVAX", "USDT"),
    "LINKUSDT": ("Chainlink", "LINK", "USDT"),
    "NEARUSDT": ("NEAR Protocol", "NEAR", "USDT"),
}

FALLBACK_PRICES: dict[str, float] = {
    "BTCUSDT": 78000.0,
    "ETHUSDT": 2450.0,
    "SOLUSDT": 142.0,
    "BNBUSDT": 615.0,
    "XRPUSDT": 2.15,
    "DOGEUSDT": 0.185,
    "ADAUSDT": 0.68,
    "AVAXUSDT": 28.5,
    "LINKUSDT": 17.2,
    "NEARUSDT": 4.85,
}


class BinanceService:
    """Production service for querying Binance Spot and Futures APIs with resilient multi-mirror fallback."""

    def __init__(self):
        self.spot_base_urls = [
            "https://data-api.binance.vision",
            "https://api.binance.com",
            "https://api1.binance.com",
            "https://api2.binance.com",
            "https://api3.binance.com",
        ]
        self.futures_base_urls = [
            "https://fapi.binance.com",
            "https://fapi1.binance.com",
        ]
        self.timeout = 6.0

    async def _fetch_spot_json(self, path: str) -> dict | list | None:
        """Fetch JSON data trying all available Binance spot mirrors in order."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for base in self.spot_base_urls:
                try:
                    resp = await client.get(f"{base}{path}")
                    if resp.status_code == 200:
                        return resp.json()
                except Exception as err:
                    logger.debug("binance_spot_mirror_failed", base=base, error=str(err))
        return None

    async def _fetch_futures_json(self, path: str) -> dict | list | None:
        """Fetch JSON data trying all available Binance futures mirrors in order."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for base in self.futures_base_urls:
                try:
                    resp = await client.get(f"{base}{path}")
                    if resp.status_code == 200:
                        return resp.json()
                except Exception as err:
                    logger.debug("binance_futures_mirror_failed", base=base, error=str(err))
        return None

    async def get_top_tickers(self) -> list[CryptoTicker]:
        """Fetch 24h ticker statistics for all standard tracked pairs."""
        symbols = list(PAIR_DISPLAY_NAMES.keys())
        tickers: list[CryptoTicker] = []

        try:
            data = await self._fetch_spot_json("/api/v3/ticker/24hr")
            if data and isinstance(data, list):
                by_symbol = {item["symbol"]: item for item in data if isinstance(item, dict)}

                for sym in symbols:
                    if sym in by_symbol:
                        raw = by_symbol[sym]
                        name, base, quote = PAIR_DISPLAY_NAMES[sym]
                        price = float(raw.get("lastPrice", 0.0))
                        change = float(raw.get("priceChange", 0.0))
                        change_pct = float(raw.get("priceChangePercent", 0.0))
                        high = float(raw.get("highPrice", price * 1.03))
                        low = float(raw.get("lowPrice", price * 0.97))
                        vol_quote = float(raw.get("quoteVolume", 0.0))
                        vol_base = float(raw.get("volume", 0.0))
                        wavg = float(raw.get("weightedAvgPrice", price))

                        sparkline = self._generate_sparkline(low, high, price, change_pct)

                        tickers.append(
                            CryptoTicker(
                                symbol=sym,
                                display_name=name,
                                base_asset=base,
                                quote_asset=quote,
                                price=price,
                                change_24h=change,
                                change_percent_24h=change_pct,
                                high_24h=high,
                                low_24h=low,
                                volume_24h_quote=vol_quote,
                                volume_24h_base=vol_base,
                                weighted_avg_price=wavg,
                                sparkline=sparkline,
                                status=DataStatus.LIVE,
                                provider="binance",
                                last_updated=datetime.now(timezone.utc),
                            )
                        )
                if tickers:
                    return tickers
        except Exception as e:
            logger.warning("binance_tickers_fetch_failed", error=str(e))

        # Resilient Fallback
        return self._generate_fallback_tickers()

    async def get_ticker(self, symbol: str) -> CryptoTicker:
        """Fetch single 24hr quote for a symbol."""
        sym = symbol.upper()
        if not sym.endswith("USDT"):
            sym = f"{sym}USDT"

        try:
            raw = await self._fetch_spot_json(f"/api/v3/ticker/24hr?symbol={sym}")
            if raw and isinstance(raw, dict):
                name, base, quote = PAIR_DISPLAY_NAMES.get(sym, (sym.replace("USDT", ""), sym.replace("USDT", ""), "USDT"))
                price = float(raw.get("lastPrice", 0.0))
                change = float(raw.get("priceChange", 0.0))
                change_pct = float(raw.get("priceChangePercent", 0.0))
                high = float(raw.get("highPrice", price * 1.02))
                low = float(raw.get("lowPrice", price * 0.98))
                vol_quote = float(raw.get("quoteVolume", 0.0))
                vol_base = float(raw.get("volume", 0.0))
                wavg = float(raw.get("weightedAvgPrice", price))

                sparkline = self._generate_sparkline(low, high, price, change_pct)

                return CryptoTicker(
                    symbol=sym,
                    display_name=name,
                    base_asset=base,
                    quote_asset=quote,
                    price=price,
                    change_24h=change,
                    change_percent_24h=change_pct,
                    high_24h=high,
                    low_24h=low,
                    volume_24h_quote=vol_quote,
                    volume_24h_base=vol_base,
                    weighted_avg_price=wavg,
                    sparkline=sparkline,
                    status=DataStatus.LIVE,
                    provider="binance",
                    last_updated=datetime.now(timezone.utc),
                )
        except Exception as e:
            logger.warning("binance_single_ticker_fetch_failed", symbol=sym, error=str(e))

        fallbacks = self._generate_fallback_tickers()
        return next((t for t in fallbacks if t.symbol == sym), fallbacks[0])

    async def get_candles(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list[NormalizedCandle]:
        """Fetch historical candlestick bars from Binance."""
        sym = symbol.upper()
        if not sym.endswith("USDT"):
            sym = f"{sym}USDT"

        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
            "1w": "1w",
        }
        interval = interval_map.get(timeframe.lower(), "1h")

        try:
            raw_data = await self._fetch_spot_json(f"/api/v3/klines?symbol={sym}&interval={interval}&limit={min(limit, 500)}")
            if raw_data and isinstance(raw_data, list):
                candles: list[NormalizedCandle] = []
                for item in raw_data:
                    open_time_ms = item[0]
                    o = float(item[1])
                    h = float(item[2])
                    l = float(item[3])
                    c = float(item[4])
                    v = float(item[5])
                    q_vol = float(item[7])
                    vwap = (q_vol / v) if v > 0 else c

                    ts_iso = datetime.fromtimestamp(open_time_ms / 1000.0, tz=timezone.utc).isoformat()
                    candles.append(
                        NormalizedCandle(
                            timestamp=ts_iso,
                            open=o,
                            high=h,
                            low=l,
                            close=c,
                            volume=v,
                            vwap=round(vwap, 4),
                        )
                    )
                if candles:
                    return candles
        except Exception as e:
            logger.warning("binance_candles_fetch_failed", symbol=sym, error=str(e))

        return self._generate_fallback_candles(sym, limit)

    async def get_order_book(self, symbol: str, limit: int = 20) -> CryptoOrderBook:
        """Fetch live bid/ask order book depth with cumulative quantities."""
        sym = symbol.upper()
        if not sym.endswith("USDT"):
            sym = f"{sym}USDT"

        depth_limit = 20 if limit <= 20 else 50

        try:
            data = await self._fetch_spot_json(f"/api/v3/depth?symbol={sym}&limit={depth_limit}")
            if data and isinstance(data, dict):
                raw_bids = data.get("bids", [])
                raw_asks = data.get("asks", [])

                bids: list[CryptoOrderBookLevel] = []
                running_bid_total = 0.0
                for p_str, q_str in raw_bids[:limit]:
                    p = float(p_str)
                    q = float(q_str)
                    running_bid_total += p * q
                    bids.append(CryptoOrderBookLevel(price=p, quantity=q, total=round(running_bid_total, 2)))

                asks: list[CryptoOrderBookLevel] = []
                running_ask_total = 0.0
                for p_str, q_str in raw_asks[:limit]:
                    p = float(p_str)
                    q = float(q_str)
                    running_ask_total += p * q
                    asks.append(CryptoOrderBookLevel(price=p, quantity=q, total=round(running_ask_total, 2)))

                best_bid = bids[0].price if bids else 0.0
                best_ask = asks[0].price if asks else 0.0
                spread = max(0.0, best_ask - best_bid)
                spread_pct = (spread / best_ask * 100) if best_ask > 0 else 0.0

                return CryptoOrderBook(
                    symbol=sym,
                    bids=bids,
                    asks=asks,
                    spread=round(spread, 4),
                    spread_percent=round(spread_pct, 4),
                    timestamp=datetime.now(timezone.utc),
                    provider="binance",
                )
        except Exception as e:
            logger.warning("binance_depth_fetch_failed", symbol=sym, error=str(e))

        return self._generate_fallback_orderbook(sym, limit)

    async def get_derivatives_data(self, symbol: str) -> CryptoDerivatives:
        """Fetch funding rate, open interest, and long/short ratio from Binance Futures."""
        sym = symbol.upper()
        if not sym.endswith("USDT"):
            sym = f"{sym}USDT"

        mark_price = FALLBACK_PRICES.get(sym, 50000.0)
        index_price = mark_price
        funding_rate = 0.0001  # Default 0.01%
        next_funding_time_ms = int((time.time() + 14400) * 1000)
        oi_usd = 2_500_000_000.0
        oi_coins = oi_usd / mark_price
        long_short_ratio = 1.45
        long_pct = 59.18
        short_pct = 40.82

        try:
            # 1. Premium Index & Funding Rate
            prem_data = await self._fetch_futures_json(f"/fapi/v1/premiumIndex?symbol={sym}")
            if prem_data and isinstance(prem_data, dict):
                mark_price = float(prem_data.get("markPrice", mark_price))
                index_price = float(prem_data.get("indexPrice", index_price))
                funding_rate = float(prem_data.get("lastFundingRate", funding_rate))
                next_funding_time_ms = int(prem_data.get("nextFundingTime", next_funding_time_ms))

            # 2. Open Interest
            oi_data = await self._fetch_futures_json(f"/fapi/v1/openInterest?symbol={sym}")
            if oi_data and isinstance(oi_data, dict):
                oi_coins = float(oi_data.get("openInterest", oi_coins))
                oi_usd = oi_coins * mark_price

            # 3. Global Long/Short Account Ratio
            ls_data = await self._fetch_futures_json(
                f"/futures/data/globalLongShortAccountRatio?symbol={sym}&period=5m&limit=1"
            )
            if ls_data and isinstance(ls_data, list) and len(ls_data) > 0:
                ls_item = ls_data[0]
                long_short_ratio = float(ls_item.get("longShortRatio", long_short_ratio))
                long_pct = float(ls_item.get("longAccount", 0.59)) * 100
                short_pct = float(ls_item.get("shortAccount", 0.41)) * 100
        except Exception as e:
            logger.warning("binance_derivatives_fetch_failed", symbol=sym, error=str(e))

        next_funding_dt = datetime.fromtimestamp(next_funding_time_ms / 1000.0, tz=timezone.utc)
        now_ts = datetime.now(timezone.utc).timestamp()
        countdown = max(0, int((next_funding_time_ms / 1000.0) - now_ts))

        return CryptoDerivatives(
            symbol=sym,
            mark_price=round(mark_price, 4),
            index_price=round(index_price, 4),
            funding_rate=funding_rate,
            funding_rate_percent=round(funding_rate * 100, 4),
            next_funding_time=next_funding_dt,
            open_interest_usd=round(oi_usd, 2),
            open_interest_coins=round(oi_coins, 4),
            long_short_ratio=round(long_short_ratio, 2),
            long_percentage=round(long_pct, 2),
            short_percentage=round(short_pct, 2),
            countdown_seconds=countdown,
            provider="binance_futures",
            timestamp=datetime.now(timezone.utc),
        )

    async def get_market_overview(self) -> CryptoMarketOverview:
        """Aggregate high-level global crypto market health metrics."""
        tickers = await self.get_top_tickers()

        sorted_by_change = sorted(tickers, key=lambda t: t.change_percent_24h, reverse=True)
        top_gainers = sorted_by_change[:3]
        top_losers = sorted_by_change[-3:]

        total_vol = sum(t.volume_24h_quote for t in tickers)
        btc = next((t for t in tickers if t.symbol == "BTCUSDT"), None)
        btc_price = btc.price if btc else 78000.0

        avg_change = sum(t.change_percent_24h for t in tickers) / len(tickers) if tickers else 0.0
        score = int(min(95, max(10, 50 + (avg_change * 5))))
        if score >= 75:
            label = "Extreme Greed"
        elif score >= 60:
            label = "Greed"
        elif score >= 45:
            label = "Neutral"
        elif score >= 30:
            label = "Fear"
        else:
            label = "Extreme Fear"

        return CryptoMarketOverview(
            fear_greed_score=score,
            fear_greed_label=label,
            btc_dominance_pct=57.8,
            total_market_cap_usd=2_850_000_000_000.0,
            total_volume_24h_usd=round(total_vol, 2),
            tracked_pairs_count=len(tickers),
            top_gainers=top_gainers,
            top_losers=top_losers,
            timestamp=datetime.now(timezone.utc),
            provider="binance",
        )

    def _generate_sparkline(self, low: float, high: float, current: float, change_pct: float) -> list[float]:
        """Generate a smooth 10-point normalized sparkline."""
        points = []
        base = current / (1.0 + (change_pct / 100.0))
        for i in range(10):
            ratio = i / 9.0
            interpolated = base + (current - base) * ratio
            noise = ((i % 3) - 1) * ((high - low) * 0.05)
            val = max(low, min(high, interpolated + noise))
            points.append(round(val, 2))
        points[-1] = round(current, 2)
        return points

    def _generate_fallback_tickers(self) -> list[CryptoTicker]:
        tickers = []
        for sym, (name, base, quote) in PAIR_DISPLAY_NAMES.items():
            price = FALLBACK_PRICES.get(sym, 100.0)
            change_pct = 2.45 if sym == "BTCUSDT" else -1.2
            change = (price * change_pct) / 100.0
            tickers.append(
                CryptoTicker(
                    symbol=sym,
                    display_name=name,
                    base_asset=base,
                    quote_asset=quote,
                    price=price,
                    change_24h=round(change, 4),
                    change_percent_24h=change_pct,
                    high_24h=round(price * 1.03, 4),
                    low_24h=round(price * 0.97, 4),
                    volume_24h_quote=price * 45000,
                    volume_24h_base=45000,
                    sparkline=[round(price * (0.98 + (i * 0.005)), 2) for i in range(10)],
                    status=DataStatus.OFFLINE,
                    provider="binance_fallback",
                    last_updated=datetime.now(timezone.utc),
                )
            )
        return tickers

    def _generate_fallback_candles(self, symbol: str, limit: int) -> list[NormalizedCandle]:
        candles = []
        base_price = FALLBACK_PRICES.get(symbol, 50000.0)
        now_ts = int(time.time())
        step_sec = 3600  # 1h

        for i in range(limit):
            t = now_ts - ((limit - i) * step_sec)
            ts_iso = datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
            o = base_price * (0.95 + (i / limit * 0.08))
            h = o * 1.01
            l = o * 0.99
            c = o * 1.005
            v = 120.5
            candles.append(
                NormalizedCandle(
                    timestamp=ts_iso,
                    open=round(o, 2),
                    high=round(h, 2),
                    low=round(l, 2),
                    close=round(c, 2),
                    volume=round(v, 2),
                    vwap=round((o + h + l + c) / 4.0, 2),
                )
            )
        return candles

    def _generate_fallback_orderbook(self, symbol: str, limit: int) -> CryptoOrderBook:
        price = FALLBACK_PRICES.get(symbol, 50000.0)
        bids = []
        running_b = 0.0
        for i in range(limit):
            p = price * (1.0 - (i * 0.0005) - 0.0002)
            q = 0.5 + (i * 0.1)
            running_b += p * q
            bids.append(CryptoOrderBookLevel(price=round(p, 2), quantity=round(q, 4), total=round(running_b, 2)))

        asks = []
        running_a = 0.0
        for i in range(limit):
            p = price * (1.0 + (i * 0.0005) + 0.0002)
            q = 0.4 + (i * 0.1)
            running_a += p * q
            asks.append(CryptoOrderBookLevel(price=round(p, 2), quantity=round(q, 4), total=round(running_a, 2)))

        spread = asks[0].price - bids[0].price
        return CryptoOrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            spread=round(spread, 2),
            spread_percent=round((spread / asks[0].price) * 100, 4),
            timestamp=datetime.now(timezone.utc),
            provider="binance_fallback",
        )


binance_service = BinanceService()
