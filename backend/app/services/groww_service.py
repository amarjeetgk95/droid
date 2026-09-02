"""Groww Open API Service Layer.

Mirrors :mod:`app.services.binance_service` architecture: a thin async client
that talks directly to the licensed Groww REST endpoints and normalizes
responses. Used by :class:`app.providers.groww.GrowwProvider` for all market
data calls (quotes, OHLC, indices) so the provider code stays focused on
caching, streaming, and provider-singleton lifecycle instead of HTTP plumbing.

Groww endpoints used (all licensed, require Bearer access token):

  - POST /v1/token/api/access        — exchange API key + secret checksum for token
  - GET  /v1/live-data/quote         — full quote snapshot (last_price, ohlc, vol, oi)
  - GET  /v1/live-data/ltp           — lightweight LTP for up to 50 symbols
  - GET  /v1/live-data/ohlc          — OHLC snapshot for up to 50 symbols
  - GET  /v1/historical/candles      — historical OHLCV candles
  - GET  /v1/option-chain/exchange/{exchange}/underlying/{symbol}  — option chain
  - GET  /v1/portfolio/positions     — signed (account info)

Auth flow:
  1. User provides API Key + API Secret in Settings UI.
  2. Backend exchanges them for a short-lived access token (~1 day) via
     ``POST /v1/token/api/access`` with checksum = SHA256(secret + timestamp).
  3. Token is cached in :class:`TokenManager` and used for all subsequent
     licensed REST calls.
  4. After market close, /v1/live-data/quote still returns the last traded
     price + OHLC — Groww does NOT gate live-data on market hours.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
import structlog

logger = structlog.get_logger()


# Index exchange_symbols for the LTP bulk endpoint (per Groww docs):
# GET /v1/live-data/ltp?segment=CASH&exchange_symbols=NSE_NIFTY,BSE_SENSEX
INDEX_EXCHANGE_SYMBOLS: dict[str, str] = {
    "NIFTY 50":  "NSE_NIFTY",
    "BANKNIFTY": "NSE_BANKNIFTY",
    "FINNIFTY":  "NSE_FINNIFTY",
    "SENSEX":    "BSE_SENSEX",
    "INDIA VIX": "NSE_INDIAVIX",
}


class GrowwServiceError(RuntimeError):
    """Raised when the Groww licensed API returns an unrecoverable error."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class GrowwService:
    """Async client for the licensed Groww Open API (growwapi).

    Responsibilities:
      - Hold API base URL + per-call headers (Bearer token, x-client-id).
      - Exchange API key/secret for short-lived access token (checksum auth).
      - Call /v1/live-data/quote, /v1/live-data/ltp, /v1/live-data/ohlc.
      - Parse the actual Groww response shapes (including their ohlc-string quirk).
      - Surface structured errors via :class:`GrowwServiceError`.

    This service is stateless aside from the configured api_key/api_secret
    (which are passed in by the provider). The short-lived access token is
    managed by the provider's TokenManager.
    """

    API_BASE = "https://api.groww.in/v1"
    AUTH_ENDPOINT = "/token/api/access"
    QUOTE_ENDPOINT = "/live-data/quote"
    LTP_ENDPOINT = "/live-data/ltp"
    OHLC_ENDPOINT = "/live-data/ohlc"
    HISTORICAL_CANDLES_ENDPOINT = "/historical/candles"

    DEFAULT_TIMEOUT_SECONDS = 3.0
    AUTH_TIMEOUT_SECONDS = 15.0

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        auth_mode: Literal["checksum", "totp"] = "checksum",
    ):
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.auth_mode = auth_mode

    # ---------- Auth ----------

    def _generate_checksum(self, timestamp: str) -> str:
        """SHA256(secret + timestamp) per Groww spec."""
        return hashlib.sha256((self.api_secret + timestamp).encode("utf-8")).hexdigest()

    async def fetch_access_token(self) -> str:
        """Exchange API key + secret for a short-lived access token, or use direct token.

        If api_key is already a JWT access token (starts with eyJ), returns it directly.
        Otherwise performs the official Groww approval checksum exchange.
        """
        # If API key is directly a JWT access token
        if self.api_key and (self.api_key.startswith("eyJ") or (len(self.api_key) > 40 and not self.api_secret)):
            logger.info("groww_direct_token_used", key_prefix=self.api_key[:8] + "...")
            return self.api_key

        if not self.api_key or not self.api_secret:
            raise GrowwServiceError(
                "missing API key or API secret — set both in Settings → Broker"
            )
        if self.auth_mode != "checksum":
            raise GrowwServiceError(
                f"auth_mode={self.auth_mode} not supported via this service "
                "(checksum flow only — TOTP requires runtime code from authenticator)"
            )

        timestamp = str(int(time.time()))
        checksum = self._generate_checksum(timestamp)
        url = f"{self.API_BASE}{self.AUTH_ENDPOINT}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-VERSION": "1.0",
        }
        payload = {"key_type": "approval", "checksum": checksum, "timestamp": timestamp}

        async with httpx.AsyncClient(timeout=self.AUTH_TIMEOUT_SECONDS) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
            except Exception as e:
                raise GrowwServiceError(f"connection error: {e}") from e

        body = (resp.text or "")[:500]
        if resp.status_code != 200:
            raise GrowwServiceError(
                f"HTTP {resp.status_code} from Groww auth: {body}",
                status_code=resp.status_code,
                body=body,
            )
        try:
            data = resp.json()
        except Exception as e:
            raise GrowwServiceError(f"non-JSON auth response: {body}") from e

        token = (
            data.get("token")
            or data.get("access_token")
            or (data.get("data") and isinstance(data["data"], dict) and data["data"].get("token"))
            or (data.get("payload") and isinstance(data["payload"], dict) and data["payload"].get("token"))
        )
        if not token:
            raise GrowwServiceError(
                f"HTTP 200 but no token in response: {body}",
                status_code=200,
                body=body,
            )
        logger.info("groww_token_fetched", expires_at=None, key_prefix=token[:8] + "...")
        return token

    # ---------- Headers ----------

    def _build_headers(self, access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "X-API-VERSION": "1.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-request-id": _gen_request_id(),
            "x-client-id": "growwapi",
            "x-client-platform": "growwapi-python-client",
            "x-client-platform-version": "1.5.0",
        }

    # ---------- Live Data: Quote (full snapshot) ----------

    async def get_quote(
        self,
        access_token: str,
        exchange: str,
        segment: str,
        trading_symbol: str,
    ) -> dict | None:
        """GET /v1/live-data/quote?exchange=…&segment=…&trading_symbol=…

        Returns a normalized dict {ltp, open, high, low, prev, volume, oi} or
        None if Groww returns an error / empty payload.
        """
        result, _, _ = await self._get_quote_with_raw(access_token, exchange, segment, trading_symbol)
        return result

    async def _get_quote_with_raw(
        self, access_token, exchange, segment, trading_symbol
    ) -> tuple[dict | None, dict | None, int | None]:
        """Like :meth:`get_quote` but also returns raw body and HTTP status code."""
        url = f"{self.API_BASE}{self.QUOTE_ENDPOINT}"
        params = {
            "exchange": exchange,
            "segment": segment,
            "trading_symbol": trading_symbol,
        }
        raw_body = None
        status = None
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT_SECONDS) as client:
            try:
                resp = await client.get(url, params=params, headers=self._build_headers(access_token))
            except Exception as e:
                logger.debug("groww_quote_request_failed", symbol=trading_symbol, error=str(e)[:200])
                return None, {"error": str(e)}, None
            status = resp.status_code
            raw_body = (resp.text or "")[:500]
        if status != 200:
            logger.debug(
                "groww_quote_http_non200",
                symbol=trading_symbol,
                status=status,
                body=raw_body,
            )
            return None, raw_body, status
        try:
            data = resp.json()
        except Exception as e:
            logger.debug("groww_quote_json_failed", symbol=trading_symbol, error=str(e)[:200])
            return None, {"error": f"json parse: {e}", "raw": raw_body}, status

        # Handle flexible status check (SUCCESS, success, OK, 200, True, or missing if payload exists)
        st = data.get("status")
        if st is not None and str(st).upper() not in ("SUCCESS", "OK", "200", "TRUE"):
            logger.debug(
                "groww_quote_status_not_success",
                symbol=trading_symbol,
                status=data.get("status"),
                payload=data,
            )
            return None, data, status
        payload = data.get("payload") or data.get("data") or data
        # Some responses wrap the quote dict under payload.quote
        if isinstance(payload, dict) and "last_price" not in payload and "ltp" not in payload:
            inner = payload.get("quote")
            if isinstance(inner, dict):
                payload = inner
        return _normalize_quote_payload(payload), data, status

    # ---------- Live Data: LTP bulk ----------

    async def get_ltp_bulk(
        self,
        access_token: str,
        segment: str,
        exchange_symbols: list[str],
    ) -> dict[str, float]:
        """GET /v1/live-data/ltp?segment=…&exchange_symbols=A,B,C

        Returns {exchange_symbol: ltp_value} for all symbols that returned a
        price. Symbols with no data are simply absent from the returned dict.
        """
        if not exchange_symbols:
            return {}
        url = f"{self.API_BASE}{self.LTP_ENDPOINT}"
        params = {
            "segment": segment,
            "exchange_symbols": ",".join(exchange_symbols) if isinstance(exchange_symbols, list) else str(exchange_symbols),
        }
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT_SECONDS) as client:
            try:
                resp = await client.get(url, params=params, headers=self._build_headers(access_token))
            except Exception as e:
                logger.debug("groww_ltp_request_failed", error=str(e)[:200])
                return {}
        if resp.status_code != 200:
            logger.debug(
                "groww_ltp_http_non200",
                status=resp.status_code,
                body=(resp.text or "")[:200],
            )
            return {}
        try:
            data = resp.json()
        except Exception as e:
            logger.debug("groww_ltp_json_failed", error=str(e)[:200])
            return {}
        st = data.get("status")
        if st is not None and str(st).upper() not in ("SUCCESS", "OK", "200", "TRUE"):
            return {}
        payload = data.get("payload") or data.get("data") or data or {}
        result: dict[str, float] = {}
        if not isinstance(payload, dict):
            return result
        for sym in exchange_symbols:
            val = payload.get(sym)
            if isinstance(val, dict):
                val = val.get("ltp") or val.get("last_price")
            if val is None:
                continue
            try:
                f = float(val)
                if f > 0:
                    result[sym] = f
            except (ValueError, TypeError):
                continue
        return result

    # ---------- Live Data: OHLC bulk ----------

    async def get_ohlc_bulk(
        self,
        access_token: str,
        segment: str,
        exchange_symbols: list[str],
    ) -> dict[str, dict]:
        """GET /v1/live-data/ohlc?segment=…&exchange_symbols=A,B,C

        Returns {exchange_symbol: {open, high, low, close}} per symbol.
        """
        if not exchange_symbols:
            return {}
        url = f"{self.API_BASE}{self.OHLC_ENDPOINT}"
        params = {
            "segment": segment,
            "exchange_symbols": ",".join(exchange_symbols) if isinstance(exchange_symbols, list) else str(exchange_symbols),
        }
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT_SECONDS) as client:
            try:
                resp = await client.get(url, params=params, headers=self._build_headers(access_token))
            except Exception as e:
                logger.debug("groww_ohlc_request_failed", error=str(e)[:200])
                return {}
        if resp.status_code != 200:
            return {}
        try:
            data = resp.json()
        except Exception as e:
            logger.debug("groww_ohlc_json_failed", error=str(e)[:200])
            return {}
        st = data.get("status")
        if st is not None and str(st).upper() not in ("SUCCESS", "OK", "200", "TRUE"):
            return {}
        payload = data.get("payload") or data.get("data") or data or {}
        result: dict[str, dict] = {}
        if not isinstance(payload, dict):
            return result
        for sym in exchange_symbols:
            raw = payload.get(sym)
            if not raw:
                continue
            parsed = _parse_ohlc_string(raw) if isinstance(raw, str) else (
                raw if isinstance(raw, dict) else None
            )
            if parsed:
                result[sym] = parsed
        return result


# ---------- Helpers (module-level so they're importable & testable) ----------

def _gen_request_id() -> str:
    """Generate a UUID4 request id for the x-request-id header."""
    import uuid
    return str(uuid.uuid4())


def _parse_ohlc_string(ohlc_val: Any) -> dict | None:
    """Groww returns ``ohlc`` as a string like
    ``'{open: 149.50,high: 150.50,low: 148.50,close: 149.50}'`` or dict.
    """
    if isinstance(ohlc_val, dict):
        return ohlc_val
    if not isinstance(ohlc_val, str):
        return None
    inner = ohlc_val.strip().strip("{}").strip()
    if not inner:
        return None
    result: dict[str, float] = {}
    for part in inner.split(","):
        if ":" not in part:
            continue
        k, _, v = part.partition(":")
        k = k.strip().strip("'\"")
        v = v.strip().strip("'\"")
        try:
            result[k] = float(v)
        except (ValueError, TypeError):
            continue
    return result if result else None


def _normalize_quote_payload(payload: dict) -> dict | None:
    """Normalize a Groww /live-data/quote payload to our internal shape.

    Returns ``{ltp, open, high, low, prev, volume, oi}`` or ``None`` if the
    payload has no usable last_price.
    """
    if not isinstance(payload, dict):
        return None

    # last_price is the LTP — source of truth
    ltp = (
        payload.get("last_price")
        or payload.get("ltp")
        or payload.get("price")
        or payload.get("close")
    )
    if ltp is None:
        return None
    try:
        ltp_f = float(ltp)
    except (ValueError, TypeError):
        return None
    if ltp_f <= 0:
        return None

    # OHLC: parse the string form, then layer in high_trade_range/low_trade_range
    ohlc = _parse_ohlc_string(payload.get("ohlc")) or {}
    open_p = ohlc.get("open") or payload.get("open")
    high_p = ohlc.get("high") or payload.get("high")
    low_p = ohlc.get("low") or payload.get("low")
    prev_p = ohlc.get("close") or payload.get("previous_close") or payload.get("prev_close")

    htr = payload.get("high_trade_range")
    ltr = payload.get("low_trade_range")
    if htr is not None:
        try:
            high_p = float(htr)
        except (ValueError, TypeError):
            pass
    if ltr is not None:
        try:
            low_p = float(ltr)
        except (ValueError, TypeError):
            pass

    vol = payload.get("volume") or payload.get("vol")
    try:
        vol = int(vol) if vol is not None else 0
    except (ValueError, TypeError):
        vol = 0

    oi_val = payload.get("open_interest") or payload.get("oi")
    try:
        oi = int(oi_val) if oi_val is not None else None
    except (ValueError, TypeError):
        oi = None

    return {
        "ltp": ltp_f,
        "open": float(open_p) if open_p is not None else ltp_f,
        "high": float(high_p) if high_p is not None else ltp_f,
        "low": float(low_p) if low_p is not None else ltp_f,
        "prev": float(prev_p) if prev_p is not None else None,
        "volume": vol,
        "oi": oi,
    }
