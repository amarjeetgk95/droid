import httpx
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger()

# NSE allIndices cache (short-lived) - 1.0s for near-realtime parity with TradingView
# Legal note: this is NSE public website scrape (not licensed feed). When Groww API
# token is configured, GrowwProvider bypasses this and uses Groww's licensed REST/Feed.
_cache: dict = {"data": None, "ts": 0.0}
CACHE_TTL_SECONDS = 1.0

async def fetch_nse_quote(symbol: str) -> dict | None:
    """Fetch real NSE/BSE quote via public APIs (no broker auth). Returns TradingView-aligned dict or None.

    Uses NSE allIndices for NIFTY/BANKNIFTY/FINNIFTY/VIX and Yahoo for SENSEX.
    This is *real* market data, not synthetic. When market is closed it returns
    the last close (NSE's `last` is previous close).
    """
    import time
    now = time.time()
    # Try NSE
    try:
        async with httpx.AsyncClient(timeout=5.0, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}) as client:
            # Check cache
            if _cache["data"] and now - _cache["ts"] < CACHE_TTL_SECONDS:
                j = _cache["data"]
            else:
                resp = await client.get("https://www.nseindia.com/api/allIndices", headers={"User-Agent": "Mozilla/5.0"}, timeout=5.0)
                if resp.status_code == 200:
                    j = resp.json()
                    _cache["data"] = j
                    _cache["ts"] = now
                else:
                    j = None
            if j:
                nse_map = {"NIFTY 50": "NIFTY 50", "BANKNIFTY": "NIFTY BANK", "FINNIFTY": "NIFTY FIN SERVICE", "INDIA VIX": "INDIA VIX"}
                nse_key = nse_map.get(symbol)
                if nse_key:
                    for idx in j.get("data", []):
                        if idx.get("indexSymbol") == nse_key or idx.get("index") == nse_key:
                            return {
                                "ltp": float(idx.get("last") or 0),
                                "open": float(idx.get("open") or 0),
                                "high": float(idx.get("high") or 0),
                                "low": float(idx.get("low") or 0),
                                "prev": float(idx.get("previousClose") or 0),
                            }
            # SENSEX via Yahoo BSE
            if symbol == "SENSEX":
                try:
                    yahoo_resp = await client.get("https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN?interval=1d&range=1d", headers={"User-Agent": "Mozilla/5.0"}, timeout=5.0)
                    if yahoo_resp.status_code == 200:
                        yj = yahoo_resp.json()
                        meta = yj.get("chart", {}).get("result", [{}])[0].get("meta", {})
                        quote = yj.get("chart", {}).get("result", [{}])[0].get("indicators", {}).get("quote", [{}])[0]
                        if meta.get("regularMarketPrice"):
                            return {
                                "ltp": float(meta.get("regularMarketPrice") or 0),
                                "open": float((quote.get("open", [0])[0] if quote.get("open") else meta.get("chartPreviousClose") or 0)),
                                "high": float((quote.get("high", [0])[0] if quote.get("high") else meta.get("regularMarketDayHigh") or 0)),
                                "low": float((quote.get("low", [0])[0] if quote.get("low") else meta.get("regularMarketDayLow") or 0)),
                                "prev": float(meta.get("chartPreviousClose") or 0),
                            }
                except Exception as e:
                    logger.debug("nse_yahoo_sensex_failed", error=str(e)[:150])
    except Exception as e:
        logger.debug("nse_fetch_failed", symbol=symbol, error=str(e)[:150])
    return None


async def fetch_nse_candles(symbol: str, timeframe: str = "5m", count: int = 75) -> list[dict] | None:
    """Fetch real historical candles via Yahoo Finance (no broker auth). Returns list or None.

    Maps symbols to Yahoo tickers: ^NSEI (NIFTY), ^NSEBANK, ^CNXFIN, ^BSESN, ^INDIAVIX
    """
    yahoo_map = {
        "NIFTY 50": "^NSEI",
        "BANKNIFTY": "^NSEBANK",
        "FINNIFTY": "^CNXFIN",
        "SENSEX": "^BSESN",
        "INDIA VIX": "^INDIAVIX",
    }
    yahoo_symbol = yahoo_map.get(symbol)
    if not yahoo_symbol:
        return None
    # timeframe -> Yahoo interval/range
    interval_map = {"1m": ("1m", "1d"), "5m": ("5m", "5d"), "15m": ("15m", "5d"), "1h": ("60m", "5d"), "1D": ("1d", "3mo")}
    interval, rng = interval_map.get(timeframe, ("5m", "5d"))
    try:
        async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval={interval}&range={rng}"
            resp = await client.get(url, timeout=8.0)
            if resp.status_code != 200:
                return None
            j = resp.json()
            result = j.get("chart", {}).get("result", [{}])[0]
            timestamps = result.get("timestamp") or []
            quote = result.get("indicators", {}).get("quote", [{}])[0]
            opens = quote.get("open") or []
            highs = quote.get("high") or []
            lows = quote.get("low") or []
            closes = quote.get("close") or []
            volumes = quote.get("volume") or []
            candles = []
            # Yahoo returns oldest first; take last `count`
            n = len(timestamps)
            start_idx = max(0, n - count)
            for i in range(start_idx, n):
                ts = timestamps[i]
                # Skip nulls
                if opens[i] is None or closes[i] is None:
                    continue
                candles.append({
                    "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
                    "open": float(opens[i] or 0),
                    "high": float(highs[i] or 0),
                    "low": float(lows[i] or 0),
                    "close": float(closes[i] or 0),
                    "volume": float(volumes[i] or 0) if volumes[i] is not None else 0,
                })
            if candles:
                return candles
    except Exception as e:
        logger.debug("yahoo_candles_failed", symbol=symbol, error=str(e)[:150])
    return None
