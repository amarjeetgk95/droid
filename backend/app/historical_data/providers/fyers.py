"""FYERS API v3 Historical Data Provider.

Implements automated 100-day chunking, exponential backoff, rate limiting,
symbol resolution (e.g. SENSEX -> BSE:SENSEX-INDEX), and canonical normalization.
"""

from __future__ import annotations
import asyncio
import random
from datetime import date, datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
import httpx
import polars as pl
import structlog

from app.historical_data.providers.base import HistoricalDataProvider
from app.historical_data.models.candle import CANDLE_POLARS_SCHEMA
from app.core.config import settings
from app.core.broker_runtime import is_usable_access_token

logger = structlog.get_logger(__name__)

FYERS_HISTORY_URL = "https://api-t1.fyers.in/data/history"
MAX_CHUNK_DAYS_1M = 95  # Safe boundary below FYERS 100-day limit


def split_date_range(start_date: date, end_date: date, max_days: int = MAX_CHUNK_DAYS_1M) -> List[Tuple[date, date]]:
    """Partition a date range into sequential chunks conforming to broker limits."""
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

    chunks: List[Tuple[date, date]] = []
    curr_start = start_date
    while curr_start <= end_date:
        curr_end = min(curr_start + timedelta(days=max_days - 1), end_date)
        chunks.append((curr_start, curr_end))
        curr_start = curr_end + timedelta(days=1)
    return chunks


class FYERSHistoricalProvider(HistoricalDataProvider):
    """Historical data provider for FYERS API v3."""

    SYMBOL_MAP = {
        "SENSEX": "BSE:SENSEX-INDEX",
        "BSE:SENSEX": "BSE:SENSEX-INDEX",
        "BSE:SENSEX-INDEX": "BSE:SENSEX-INDEX",
        "NIFTY": "NSE:NIFTY50-INDEX",
        "NIFTY 50": "NSE:NIFTY50-INDEX",
        "NSE:NIFTY": "NSE:NIFTY50-INDEX",
        "NSE:NIFTY50-INDEX": "NSE:NIFTY50-INDEX",
        "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
        "NSE:BANKNIFTY": "NSE:NIFTYBANK-INDEX",
        "NSE:NIFTYBANK-INDEX": "NSE:NIFTYBANK-INDEX",
        "FINNIFTY": "NSE:FINNIFTY-INDEX",
        "NSE:FINNIFTY": "NSE:FINNIFTY-INDEX",
        "NSE:FINNIFTY-INDEX": "NSE:FINNIFTY-INDEX",
        "INDIA VIX": "NSE:INDIAVIX-INDEX",
        "INDIAVIX": "NSE:INDIAVIX-INDEX",
        "NSE:INDIAVIX-INDEX": "NSE:INDIAVIX-INDEX",
    }

    TIMEFRAME_MAP = {
        "1m": "1",
        "1": "1",
        "1min": "1",
        "2m": "2",
        "3m": "3",
        "5m": "5",
        "5": "5",
        "10m": "10",
        "15m": "15",
        "15": "15",
        "30m": "30",
        "30": "30",
        "60m": "60",
        "1h": "60",
        "60": "60",
        "1d": "D",
        "d": "D",
        "daily": "D",
    }

    def __init__(
        self,
        app_id: Optional[str] = None,
        access_token: Optional[str] = None,
        max_retries: int = 3,
        request_timeout: float = 15.0,
    ):
        self._app_id = (app_id or settings.fyers_app_id or "").strip()
        self._access_token = (access_token or settings.fyers_access_token or "").strip()
        self.max_retries = max_retries
        self.request_timeout = request_timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider_id(self) -> str:
        return "fyers"

    def _get_auth_header(self) -> str:
        """Construct the FYERS v3 Authorization header."""
        app_id = self._app_id
        token = self._access_token
        if not token:
            # Check broker_runtime dynamically
            try:
                from app.core.broker_runtime import get_config
                cfg = get_config()
                if cfg.provider == "fyers":
                    token = cfg.credentials.get("access_token") or ""
                    app_id = app_id or cfg.credentials.get("app_id") or ""
            except Exception:
                pass

        if not token:
            return ""
        if app_id and ":" not in token:
            return f"{app_id}:{token}"
        return token

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.request_timeout,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._client

    def resolve_provider_symbol(self, canonical_symbol: str) -> str:
        sym_clean = canonical_symbol.strip().upper()
        if sym_clean in self.SYMBOL_MAP:
            return self.SYMBOL_MAP[sym_clean]
        # Default pass-through if already in FYERS exchange:symbol format
        return sym_clean

    def resolve_timeframe(self, timeframe: str) -> str:
        tf_clean = timeframe.strip().lower()
        if tf_clean in self.TIMEFRAME_MAP:
            return self.TIMEFRAME_MAP[tf_clean]
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    async def fetch_chunk(
        self,
        symbol: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> List[List[Any]]:
        """Fetch a single API chunk with exponential backoff."""
        auth_header = self._get_auth_header()
        if not auth_header or not is_usable_access_token(self._access_token or auth_header):
            logger.warning("fyers_missing_auth", hint="Valid FYERS credentials required for live historical API")

        fyers_symbol = self.resolve_provider_symbol(symbol)
        fyers_resolution = self.resolve_timeframe(timeframe)
        client = self._get_http_client()

        params = {
            "symbol": fyers_symbol,
            "resolution": fyers_resolution,
            "date_format": "1",
            "range_from": start_date.strftime("%Y-%m-%d"),
            "range_to": end_date.strftime("%Y-%m-%d"),
            "cont_flag": "1",
        }
        headers = {"Authorization": auth_header}

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.get(FYERS_HISTORY_URL, params=params, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("s")
                    if status == "ok":
                        return data.get("candles", [])
                    elif status == "no_data":
                        return []
                    else:
                        msg = data.get("message", "Unknown error")
                        logger.warning("fyers_api_error_response", status=status, msg=msg, params=params)
                        if "limit" in msg.lower() or response.status_code == 429:
                            await asyncio.sleep(1.5 * attempt)
                            continue
                        return []

                elif response.status_code in (429, 500, 502, 503, 504):
                    backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                    logger.warning("fyers_retryable_status", code=response.status_code, backoff=backoff, attempt=attempt)
                    await asyncio.sleep(backoff)
                else:
                    logger.error("fyers_non_retryable_error", code=response.status_code, body=response.text[:200])
                    break

            except (httpx.TimeoutException, httpx.NetworkError) as err:
                backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                logger.warning("fyers_network_error", error=str(err), attempt=attempt, backoff=backoff)
                await asyncio.sleep(backoff)

        return []

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start_date: date,
        end_date: date,
        job_id: str = "",
        version_tag: str = "v1",
    ) -> pl.DataFrame:
        """Fetch full range by automatically chunking and concatenating into a Polars DataFrame."""
        chunks = split_date_range(start_date, end_date)
        all_raw_candles: List[List[Any]] = []

        for chunk_start, chunk_end in chunks:
            chunk_candles = await self.fetch_chunk(symbol, timeframe, chunk_start, chunk_end)
            all_raw_candles.extend(chunk_candles)
            # Small rate-limiting throttle between chunk requests
            if len(chunks) > 1:
                await asyncio.sleep(0.2)

        if not all_raw_candles:
            # Return empty DataFrame matching canonical schema
            return pl.DataFrame(schema=CANDLE_POLARS_SCHEMA)

        # Raw candle structure: [epoch_seconds, open, high, low, close, volume]
        exchange = "BSE" if "BSE" in self.resolve_provider_symbol(symbol) else "NSE"
        asset_type = "INDEX" if ("INDEX" in self.resolve_provider_symbol(symbol) or symbol in ("SENSEX", "NIFTY", "BANKNIFTY")) else "EQUITY"

        timestamps = [datetime.fromtimestamp(c[0], tz=timezone.utc) for c in all_raw_candles]
        opens = [float(c[1]) for c in all_raw_candles]
        highs = [float(c[2]) for c in all_raw_candles]
        lows = [float(c[3]) for c in all_raw_candles]
        closes = [float(c[4]) for c in all_raw_candles]
        volumes = [float(c[5]) if len(c) > 5 else 0.0 for c in all_raw_candles]
        n_rows = len(all_raw_candles)

        df = pl.DataFrame({
            "timestamp": pl.Series("timestamp", timestamps, dtype=pl.Datetime("ms", "UTC")),
            "symbol": pl.Series("symbol", [symbol] * n_rows, dtype=pl.Utf8),
            "exchange": pl.Series("exchange", [exchange] * n_rows, dtype=pl.Utf8),
            "asset_type": pl.Series("asset_type", [asset_type] * n_rows, dtype=pl.Utf8),
            "timeframe": pl.Series("timeframe", [timeframe] * n_rows, dtype=pl.Utf8),
            "open": pl.Series("open", opens, dtype=pl.Float64),
            "high": pl.Series("high", highs, dtype=pl.Float64),
            "low": pl.Series("low", lows, dtype=pl.Float64),
            "close": pl.Series("close", closes, dtype=pl.Float64),
            "volume": pl.Series("volume", volumes, dtype=pl.Float64),
            "provider": pl.Series("provider", [self.provider_id] * n_rows, dtype=pl.Utf8),
            "ingestion_job_id": pl.Series("ingestion_job_id", [job_id] * n_rows, dtype=pl.Utf8),
            "data_version": pl.Series("data_version", [version_tag] * n_rows, dtype=pl.Utf8),
        })

        # Deduplicate and sort chronologically
        df = df.unique(subset=["symbol", "timeframe", "timestamp"]).sort("timestamp")
        return df

    async def get_available_range(
        self,
        symbol: str,
        timeframe: str,
    ) -> Tuple[Optional[date], Optional[date]]:
        """Probe the broker's retention limits by checking past milestones."""
        today = datetime.now(timezone.utc).date()
        # Probe test windows: 30 days, 100 days, 180 days, 365 days back
        for days_back in [365, 180, 100, 30]:
            probe_start = today - timedelta(days=days_back)
            probe_end = probe_start + timedelta(days=5)
            candles = await self.fetch_chunk(symbol, timeframe, probe_start, probe_end)
            if candles:
                earliest_ts = min(c[0] for c in candles)
                return datetime.fromtimestamp(earliest_ts, tz=timezone.utc).date(), today
        return None, today
