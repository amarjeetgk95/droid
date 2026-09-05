import time
import httpx
from datetime import datetime, timezone
from typing import Optional
import structlog
from app.models.crypto import (
    CryptoTicker,
    CryptoOrderBook,
    CryptoDerivatives,
    CryptoPairComparison,
    CryptoMarketOverview,
    ALLOWED_CRYPTO_SYMBOLS,
)
from app.models.market import NormalizedCandle, DataStatus
from app.services.orderbook_engine import orderbook_engine
from app.services.derivatives_engine import derivatives_engine
from app.services.comparison_engine import comparison_engine
from app.services.market_data_health import market_health_tracker

logger = structlog.get_logger()

# Strictly Bitcoin (BTC) and Ethereum (ETH) pairs
PAIR_DISPLAY_NAMES: dict[str, tuple[str, str, str]] = {
    "BTCUSDT": ("Bitcoin", "BTC", "USDT"),
    "ETHUSDT": ("Ethereum", "ETH", "USDT"),
    "ETHBTC": ("Ethereum / Bitcoin", "ETH", "BTC"),
}



class BinanceService:
    """Production institutional service for Bitcoin (BTC) and Ethereum (ETH) market data."""

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
        self.timeout = 5.0

    async def _fetch_spot_json(self, path: str) -> dict | list | None:
        """Fetch JSON trying all available Binance spot mirrors in order."""
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
        """Fetch JSON trying all available Binance futures mirrors in order."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for base in self.futures_base_urls:
                try:
                    resp = await client.get(f"{base}{path}")
                    if resp.status_code == 200:
                        return resp.json()
                except Exception as err:
                    logger.debug("binance_futures_mirror_failed", base=base, error=str(err))
        return None

    def validate_symbol(self, symbol: str) -> str:
        """Validate that symbol is strictly in the allowed BTC & ETH whitelist."""
        clean = symbol.upper().replace("/", "").replace("-", "")
        if not clean.endswith("USDT") and not clean.endswith("BTC"):
            clean = f"{clean}USDT"
        if clean not in ALLOWED_CRYPTO_SYMBOLS:
            raise ValueError(f"Symbol '{symbol}' is not supported. Allowed symbols: {list(ALLOWED_CRYPTO_SYMBOLS)}")
        return clean

    async def get_top_tickers(self) -> list[CryptoTicker]:
        """Fetch 24h ticker statistics strictly for BTC and ETH pairs."""
        symbols = ["BTCUSDT", "ETHUSDT", "ETHBTC"]
        tickers: list[CryptoTicker] = []

        try:
            data = await self._fetch_spot_json("/api/v3/ticker/24hr")
            if data and isinstance(data, list):
                by_symbol = {item["symbol"]: item for item in data if isinstance(item, dict) and "symbol" in item}

                for sym in symbols:
                    if sym in by_symbol:
                        raw = by_symbol[sym]
                        name, base, quote = PAIR_DISPLAY_NAMES[sym]
                        price = float(raw.get("lastPrice", 0.0))
                        change = float(raw.get("priceChange", 0.0))
                        change_pct = float(raw.get("priceChangePercent", 0.0))
                        high = float(raw.get("highPrice", price * 1.02))
                        low = float(raw.get("lowPrice", price * 0.98))
                        vol_base = float(raw.get("volume", 0.0))
                        vol_quote = float(raw.get("quoteVolume", 0.0))
                        wavg = float(raw.get("weightedAvgPrice", price))
                        bid_p = float(raw.get("bidPrice", price * 0.9999))
                        ask_p = float(raw.get("askPrice", price * 1.0001))
                        count = int(raw.get("count", 0))

                        spread = max(0.0, round(ask_p - bid_p, 4))
                        spread_pct = round((spread / ask_p * 100), 4) if ask_p > 0 else 0.0
                        range_spread_pct = round(((high - low) / low * 100), 2) if low > 0 else 0.0

                        sparkline = self._generate_sparkline(low, high, price, change_pct)
                        now = datetime.now(timezone.utc)

                        asset_key = "btc_ticker" if "BTC" in sym and quote == "USDT" else ("eth_ticker" if "ETH" in sym and quote == "USDT" else "btc_ticker")
                        market_health_tracker.record_event(asset_key)

                        tickers.append(
                            CryptoTicker(
                                symbol=sym,
                                asset=base,
                                display_name=name,
                                market_type="spot",
                                price=price,
                                bid_price=bid_p,
                                ask_price=ask_p,
                                change_24h=change,
                                change_percent_24h=change_pct,
                                high_24h=high,
                                low_24h=low,
                                volume_24h_base=vol_base,
                                volume_24h_quote=vol_quote,
                                vwap=wavg,
                                trade_count=count,
                                spread=spread,
                                spread_percent=spread_pct,
                                high_low_spread_pct=range_spread_pct,
                                sparkline=sparkline,
                                status=DataStatus.LIVE,
                                provider="binance_spot",
                                last_updated=now,
                            )
                        )
                if len(tickers) >= 2:
                    return tickers
        except Exception as e:
            logger.warning("binance_tickers_fetch_failed", error=str(e))

        return []

    async def get_ticker(self, symbol: str) -> CryptoTicker:
        """Fetch single 24hr quote for a symbol in the whitelist."""
        sym = self.validate_symbol(symbol)

        try:
            raw = await self._fetch_spot_json(f"/api/v3/ticker/24hr?symbol={sym}")
            if raw and isinstance(raw, dict):
                name, base, quote = PAIR_DISPLAY_NAMES[sym]
                price = float(raw.get("lastPrice", 0.0))
                change = float(raw.get("priceChange", 0.0))
                change_pct = float(raw.get("priceChangePercent", 0.0))
                high = float(raw.get("highPrice", price * 1.02))
                low = float(raw.get("lowPrice", price * 0.98))
                vol_base = float(raw.get("volume", 0.0))
                vol_quote = float(raw.get("quoteVolume", 0.0))
                wavg = float(raw.get("weightedAvgPrice", price))
                bid_p = float(raw.get("bidPrice", price * 0.9999))
                ask_p = float(raw.get("askPrice", price * 1.0001))
                count = int(raw.get("count", 0))

                spread = max(0.0, round(ask_p - bid_p, 4))
                spread_pct = round((spread / ask_p * 100), 4) if ask_p > 0 else 0.0
                range_spread_pct = round(((high - low) / low * 100), 2) if low > 0 else 0.0

                sparkline = self._generate_sparkline(low, high, price, change_pct)
                now = datetime.now(timezone.utc)

                asset_key = "btc_ticker" if base == "BTC" else "eth_ticker"
                market_health_tracker.record_event(asset_key)

                return CryptoTicker(
                    symbol=sym,
                    asset=base,
                    display_name=name,
                    market_type="spot",
                    price=price,
                    bid_price=bid_p,
                    ask_price=ask_p,
                    change_24h=change,
                    change_percent_24h=change_pct,
                    high_24h=high,
                    low_24h=low,
                    volume_24h_base=vol_base,
                    volume_24h_quote=vol_quote,
                    vwap=wavg,
                    trade_count=count,
                    spread=spread,
                    spread_percent=spread_pct,
                    high_low_spread_pct=range_spread_pct,
                    sparkline=sparkline,
                    status=DataStatus.LIVE,
                    provider="binance_spot",
                    last_updated=now,
                )
        except Exception as e:
            logger.warning("binance_single_ticker_fetch_failed", symbol=sym, error=str(e))
            raise RuntimeError(f"Live ticker unavailable for {sym}: {e}")

        raise RuntimeError(f"Live ticker unavailable for {sym}")

    async def get_candles(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list[NormalizedCandle]:
        """Fetch historical candlestick bars from Binance Spot."""
        sym = self.validate_symbol(symbol)
        interval = timeframe.lower()
        if interval not in ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"):
            interval = "1h"

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

        return []

    async def get_order_book(self, symbol: str, limit: int = 20, market_type: str = "spot") -> CryptoOrderBook:
        """Fetch live L2 depth snapshot and synchronize with OrderBookEngine."""
        sym = self.validate_symbol(symbol)
        depth_limit = 20 if limit <= 20 else 50

        try:
            path = f"/api/v3/depth?symbol={sym}&limit={depth_limit}" if market_type == "spot" else f"/fapi/v1/depth?symbol={sym}&limit={depth_limit}"
            data = await self._fetch_spot_json(path) if market_type == "spot" else await self._fetch_futures_json(path)

            if data and isinstance(data, dict):
                last_u = int(data.get("lastUpdateId", 0))
                raw_bids = data.get("bids", [])
                raw_asks = data.get("asks", [])

                book_state = orderbook_engine.get_or_create(sym, market_type)
                book_state.set_snapshot(last_u, raw_bids, raw_asks)
                book_state.replay_buffer()

                asset_key = "btc_orderbook" if "BTC" in sym else "eth_orderbook"
                market_health_tracker.record_event(asset_key)

                return book_state.to_model(limit=limit)
        except Exception as e:
            logger.warning("binance_depth_fetch_failed", symbol=sym, error=str(e))

        book_state = orderbook_engine.get_or_create(sym, market_type)
        if not book_state.is_initialized:
            book_state.data_status = DataStatus.OFFLINE
        return book_state.to_model(limit=limit)

    async def get_derivatives_data(self, symbol: str) -> CryptoDerivatives:
        """Fetch funding rate, Open Interest, long/short ratio, and compute Basis."""
        sym = self.validate_symbol(symbol)
        if sym == "ETHBTC":
            # Derivatives are USD-M settled; fallback to ETHUSDT
            sym = "ETHUSDT"

        try:
            # 1. Fetch spot price for Basis
            spot_ticker = await self._fetch_spot_json(f"/api/v3/ticker/price?symbol={sym}")
            spot_price = float(spot_ticker.get("price", 0.0)) if spot_ticker and isinstance(spot_ticker, dict) else None

            # 2. Premium Index & Funding Rate
            prem_data = await self._fetch_futures_json(f"/fapi/v1/premiumIndex?symbol={sym}")
            if not prem_data or not isinstance(prem_data, dict):
                raise RuntimeError(f"Failed to fetch premiumIndex for {sym}")
            mark_price = float(prem_data["markPrice"])
            index_price = float(prem_data["indexPrice"])
            funding_rate = float(prem_data["lastFundingRate"])
            next_funding_ms = int(prem_data["nextFundingTime"])

            # 3. Open Interest
            oi_data = await self._fetch_futures_json(f"/fapi/v1/openInterest?symbol={sym}")
            if not oi_data or not isinstance(oi_data, dict):
                raise RuntimeError(f"Failed to fetch openInterest for {sym}")
            oi_coins = float(oi_data["openInterest"])

            # 4. Long/Short Account Ratio
            long_short_ratio = 1.0
            long_pct = 50.0
            short_pct = 50.0
            ls_data = await self._fetch_futures_json(
                f"/futures/data/globalLongShortAccountRatio?symbol={sym}&period=5m&limit=1"
            )
            if ls_data and isinstance(ls_data, list) and len(ls_data) > 0:
                ls_item = ls_data[0]
                long_short_ratio = float(ls_item.get("longShortRatio", 1.0))
                long_pct = float(ls_item.get("longAccount", 0.5)) * 100
                short_pct = float(ls_item.get("shortAccount", 0.5)) * 100

            # 5. Top Trader Ratio
            top_trader_ratio = None
            top_data = await self._fetch_futures_json(
                f"/futures/data/topLongShortAccountRatio?symbol={sym}&period=5m&limit=1"
            )
            if top_data and isinstance(top_data, list) and len(top_data) > 0:
                top_trader_ratio = float(top_data[0].get("longShortRatio", 1.0))

            asset_key = "btc_derivatives" if "BTC" in sym else "eth_derivatives"
            market_health_tracker.record_event(asset_key)

            return derivatives_engine.build_model(
                symbol=sym,
                mark_price=mark_price,
                index_price=index_price,
                spot_price=spot_price or mark_price,
                funding_rate=funding_rate,
                next_funding_time_ms=next_funding_ms,
                open_interest_coins=oi_coins,
                long_short_ratio=long_short_ratio,
                long_pct=long_pct,
                short_pct=short_pct,
                top_trader_ratio=top_trader_ratio,
                data_status=DataStatus.LIVE,
            )
        except Exception as e:
            logger.warning("binance_derivatives_fetch_failed", symbol=sym, error=str(e))
            raise RuntimeError(f"Derivatives data unavailable for {sym}: {e}")

    async def get_pair_comparison(self) -> CryptoPairComparison:
        """Compute relative strength, ETH/BTC ratio, and performance spread."""
        tickers = await self.get_top_tickers()
        btc = next((t for t in tickers if t.symbol == "BTCUSDT"), None)
        eth = next((t for t in tickers if t.symbol == "ETHUSDT"), None)
        eth_btc = next((t for t in tickers if t.symbol == "ETHBTC"), None)

        if not btc or not eth:
            return comparison_engine.calculate_comparison(
                btc_price=0.0,
                btc_change_pct=0.0,
                btc_volume_quote=0.0,
                eth_price=0.0,
                eth_change_pct=0.0,
                eth_volume_quote=0.0,
                eth_btc_direct_price=0.0,
                eth_btc_direct_change_pct=0.0,
                data_status=DataStatus.OFFLINE,
            )

        btc_p = btc.price
        btc_c = btc.change_percent_24h
        btc_v = btc.volume_24h_quote

        eth_p = eth.price
        eth_c = eth.change_percent_24h
        eth_v = eth.volume_24h_quote

        eth_btc_p = eth_btc.price if eth_btc else (eth_p / btc_p if btc_p > 0 else 0.0)
        eth_btc_c = eth_btc.change_percent_24h if eth_btc else (eth_c - btc_c)

        return comparison_engine.calculate_comparison(
            btc_price=btc_p,
            btc_change_pct=btc_c,
            btc_volume_quote=btc_v,
            eth_price=eth_p,
            eth_change_pct=eth_c,
            eth_volume_quote=eth_v,
            eth_btc_direct_price=eth_btc_p,
            eth_btc_direct_change_pct=eth_btc_c,
            data_status=btc.status,
        )

    async def get_market_overview(self) -> CryptoMarketOverview:
        """Aggregate macro crypto market health strictly for BTC & ETH."""
        tickers = await self.get_top_tickers()
        btc = next((t for t in tickers if t.symbol == "BTCUSDT"), None)
        eth = next((t for t in tickers if t.symbol == "ETHUSDT"), None)
        eth_btc = next((t for t in tickers if t.symbol == "ETHBTC"), None)

        if not btc and not eth:
            return CryptoMarketOverview(
                fear_greed_score=50,
                fear_greed_label="Neutral",
                btc_dominance_pct=0.0,
                eth_dominance_pct=0.0,
                total_market_cap_usd=0.0,
                combined_volume_24h_usd=0.0,
                eth_btc_ratio=0.0,
                tracked_pairs_count=0,
                top_assets=[],
                top_gainers=[],
                top_losers=[],
                status=DataStatus.OFFLINE,
                timestamp=datetime.now(timezone.utc),
                provider="binance",
            )

        total_vol = sum(t.volume_24h_quote for t in (btc, eth) if t is not None)
        eth_btc_ratio = eth_btc.price if eth_btc else ((eth.price / btc.price) if (btc and eth and btc.price > 0) else 0.0)

        active_tickers = [t for t in (btc, eth) if t is not None]
        avg_change = sum(t.change_percent_24h for t in active_tickers) / len(active_tickers) if active_tickers else 0.0
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

        tracked_volume = (btc.volume_24h_quote if btc else 0.0) + (eth.volume_24h_quote if eth else 0.0)
        btc_vol_share = round((btc.volume_24h_quote / tracked_volume * 100), 1) if (btc and tracked_volume > 0) else 0.0
        eth_vol_share = round((eth.volume_24h_quote / tracked_volume * 100), 1) if (eth and tracked_volume > 0) else 0.0

        return CryptoMarketOverview(
            fear_greed_score=score,
            fear_greed_label=label,
            btc_dominance_pct=btc_vol_share,
            eth_dominance_pct=eth_vol_share,
            total_market_cap_usd=0.0,
            combined_volume_24h_usd=round(total_vol, 2),
            eth_btc_ratio=round(eth_btc_ratio, 6),
            tracked_pairs_count=len(active_tickers),
            top_assets=active_tickers,
            top_gainers=[t for t in active_tickers if t.change_percent_24h >= 0],
            top_losers=[t for t in active_tickers if t.change_percent_24h < 0],
            status=btc.status if btc else DataStatus.OFFLINE,
            timestamp=datetime.now(timezone.utc),
            provider="binance",
        )

    def _generate_sparkline(self, low: float, high: float, current: float, change_pct: float) -> list[float]:
        points = []
        base = current / (1.0 + (change_pct / 100.0)) if (1.0 + (change_pct / 100.0)) != 0 else current
        for i in range(10):
            ratio = i / 9.0
            interpolated = base + (current - base) * ratio
            noise = ((i % 3) - 1) * ((high - low) * 0.05)
            val = max(low, min(high, interpolated + noise))
            points.append(round(val, 2))
        points[-1] = round(current, 2)
        return points


binance_service = BinanceService()
