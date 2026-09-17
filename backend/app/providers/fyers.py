import asyncio
import math
import httpx
from datetime import date, datetime, timezone
from app.providers.base import MarketDataProvider
from app.models.market import (
    NormalizedQuote, NormalizedCandle, NormalizedOptionQuote,
    IndexCard, MarketHealthStatus, MarketStatusResponse,
    MarketBreadthData, DataStatus, MarketSession
)
from app.models.contracts import TickEvent, EventPriority
from app.core.config import settings
from app.core.broker_runtime import is_usable_access_token
from app.core.token_manager import TokenManager, ConnectionState, TokenInfo
from app.core.rate_limiter import TokenBucketRateLimiter
from app.services.calendar_service import calendar_service
import structlog

logger = structlog.get_logger()


def _nearest_fyers_expiry(expiry_data: object) -> "date | None":
    """Nearest upcoming expiry date from FYERS options-chain-v3 `expiryData`.

    Entries look like ``{"date": "22-09-2026", "expiry": "1790071800"}``.
    The broker calendar (Tuesday NIFTY weeklies, ...) is truth; our local
    calendar bootstrap drifts (Thursday rule), so quotes must be labelled
    with this date — never with the requested date or today. Returns None
    when nothing parses; callers fall back to requested/now labelling.
    """
    from datetime import date as _date

    try:
        items = list(expiry_data or [])  # type: ignore[arg-type]
    except TypeError:
        return None
    if not items:
        return None
    try:
        from app.signals.safety.clocks import IST as _ist
    except Exception:
        _ist = timezone.utc  # type: ignore[assignment]
    today = datetime.now(_ist).date()
    parsed: list[_date] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        d: _date | None = None
        raw_date = it.get("date")
        if isinstance(raw_date, str) and raw_date.strip():
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    d = datetime.strptime(raw_date.strip(), fmt).date()
                    break
                except (ValueError, TypeError):
                    continue
        if d is None:
            try:
                ts = int(str(it.get("expiry") or "").strip())
                if ts > 0:
                    d = datetime.fromtimestamp(ts, tz=_ist).date()
            except (ValueError, TypeError, OverflowError, OSError):
                d = None
        if d is not None:
            parsed.append(d)
    if not parsed:
        return None
    upcoming = [d for d in parsed if d >= today]
    return min(upcoming) if upcoming else min(parsed)


class FyersProvider(MarketDataProvider):
    """FYERS API v3 Market Data Provider Adapter (REST poller, not websocket).

    Backend-owned 1s REST poller (`_poller_loop` -> `data/quotes` -> central_feed),
    started once at backend startup via app.core.service_lifecycle, never by
    frontend connections. Closing the browser/dashboard never stops this poller.
    Truth-of-Wall: FYERS-only; no websocket tick stream, no order-book.
    """

    PROVIDER_ID = "fyers"

    # ── Inbound tick sanity (Truth of Wall) ─────────────────────────────
    # Single-feed architecture means a corrupted broker response would flow
    # straight into sizing and triggers. The poller therefore validates each
    # quote BEFORE it reaches central_feed:
    #   jump limit : |ΔLTP| vs the last accepted tick > tick_sanity_jump_pct
    #                (default 2% per 1s poll) → rejected as implausible
    #   OHLC coherence: low <= {open, ltp} <= high (price-scaled tolerance).
    #   previous_close is yesterday's settlement — validated separately for
    #   plausibility (positive, within 20% of LTP), never confined to today's
    #   range (gap days would freeze the symbol all session).
    # A rejected tick is a GAP, never a repair: no corrected/interpolated
    # value is ever emitted. Sustained rejection raises the counter that
    # /health/subsystems exposes (tick_sanity_rejections).
    _OHLC_COHERENCE_EPS_FACTOR = 0.05  # tolerance, in units of the quote's tick size 0.05
    _SANITY_REJECT_WINDOW_S = 60.0
    _SANITY_REJECT_ALERT_THRESHOLD = 5  # rejections per symbol within window → warn once

    def __init__(
        self,
        app_id: str | None = None,
        secret_key: str | None = None,
        access_token: str | None = None,
    ):
        # Resolution order: explicit ctor arg -> localhost .env ONLY.
        # Settings UI secrets are ignored (hardcoded-only localhost setup).
        _rt_creds: dict = {}
        try:
            from app.core.broker_runtime import get_config as _get_cfg
            _cfg = _get_cfg()
            if _cfg.provider == "fyers" and isinstance(_cfg.credentials, dict):
                _rt_creds = _cfg.credentials
        except Exception:
            _rt_creds = {}
        self.app_id = (app_id or settings.fyers_app_id or "").strip().strip("\"'") or None
        self.secret_key = (secret_key or settings.fyers_secret_key or "").strip().strip("\"'") or None
        _rt_token = _rt_creds.get("access_token") or ""

        # Inbound tick-sanity state (see class docstring block above)
        self._last_accepted_ltp: dict[str, float] = {}
        self._sanity_reject_events: list[tuple[float, str]] = []  # (monotonic_ts, symbol)
        self._sanity_alerted: set[str] = set()

        self.token_manager = TokenManager(
            provider="fyers",
            initial_backoff=settings.ws_reconnect_initial_seconds,
            max_backoff=settings.ws_reconnect_max_seconds,
            enable_jitter=settings.ws_reconnect_jitter,
        )
        _eff_token = (access_token or _rt_token or settings.fyers_access_token or "").strip().strip("\"'")
        if is_usable_access_token(_eff_token):
            self.token_manager.set_token(
                TokenInfo(
                    access_token=_eff_token,
                    provider="fyers",
                )
            )
        elif _eff_token:
            # Placeholder/stub token (e.g. committed test fixture): do NOT seed
            # the TokenManager — every live call would 401. Park with a clear
            # re-auth hint instead.
            logger.warning(
                "fyers_token_placeholder_ignored",
                hint="FYERS token looks like a placeholder, not a real credential — re-auth via /api/v1/tokens/fyers/auth-url",
            )

        self.rate_limiter = TokenBucketRateLimiter(
            requests_per_second=settings.rate_limit_requests_per_second,
            requests_per_minute=settings.rate_limit_requests_per_minute,
            burst_limit=settings.rate_limit_burst_limit,
        )

        self._stream_running = False
        self._stream_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None
        self._start_lock: asyncio.Lock | None = None
        self._consecutive_failures = 0
        self._last_known_quotes: dict[str, NormalizedQuote] = {}
        self._http_client: httpx.AsyncClient | None = None

        self.symbol_map = {
            "NIFTY 50": "NSE:NIFTY50-INDEX",
            "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
            "FINNIFTY": "NSE:FINNIFTY-INDEX",
            "SENSEX": "BSE:SENSEX-INDEX",
            "INDIA VIX": "NSE:INDIAVIX-INDEX",
        }

    def _get_http_client(self, timeout: float = 6.0) -> httpx.AsyncClient:
        """Shared persistent HTTP client with connection pooling."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._http_client

    @property
    def provider_name(self) -> str:
        return "fyers"

    def get_token_manager(self) -> TokenManager:
        return self.token_manager

    def get_rate_limiter(self) -> TokenBucketRateLimiter:
        return self.rate_limiter

    async def _fetch_fyers_quotes(self, symbols: list[str]) -> dict[str, NormalizedQuote]:
        """Fetch quotes batch from official Fyers API v3."""
        try:
            token = await self.token_manager.get_valid_token()
        except Exception:
            token = ""
        if not token:
            from app.core.broker_runtime import get_config
            cfg_obj = get_config()
            if cfg_obj.provider == "fyers":
                token = cfg_obj.credentials.get("access_token") or ""

        if not is_usable_access_token(token):
            return {}

        app_id = self.app_id
        if not app_id:
            from app.core.broker_runtime import get_config
            cfg_obj = get_config()
            if cfg_obj.provider == "fyers":
                app_id = cfg_obj.credentials.get("app_id") or ""

        auth_header = f"{app_id}:{token}" if app_id and ":" not in token else token

        fyers_syms = [self.symbol_map.get(s, s) for s in symbols]
        syms_str = ",".join(fyers_syms)

        now = datetime.now(timezone.utc)
        is_open = calendar_service.is_market_open_now()
        status = DataStatus.LIVE if is_open else DataStatus.CLOSED

        try:
            client = self._get_http_client(timeout=4.0)
            resp = await client.get(
                f"https://api-t1.fyers.in/data/quotes?symbols={syms_str}",
                headers={"Authorization": auth_header},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("s") == "ok" and "d" in data and isinstance(data["d"], list):
                    self._consecutive_failures = 0
                    inv_map = {v: k for k, v in self.symbol_map.items()}
                    quotes_map = {}
                    for item in data["d"]:
                        f_sym = item.get("n", "")
                        v = item.get("v", {})
                        int_sym = inv_map.get(f_sym, f_sym)
                        ltp = float(v.get("lp", 0.0))
                        if ltp <= 0:
                            continue
                        open_p = float(v.get("open_price") or ltp)
                        high_p = float(v.get("high_price") or ltp)
                        low_p = float(v.get("low_price") or ltp)
                        prev_p = float(v.get("prev_close_price") or 0.0)
                        ch = float(v.get("ch") or (round(ltp - prev_p, 2) if prev_p else 0.0))
                        chp = float(v.get("chp") or (round((ch / prev_p * 100) if prev_p else 0.0, 2)))
                        vol = int(v.get("volume") or 0)
                        oi = int(v.get("oi")) if v.get("oi") is not None else None

                        nq = NormalizedQuote(
                            symbol=int_sym,
                            display_name=int_sym,
                            timestamp=now,
                            ltp=round(ltp, 2),
                            open=round(open_p, 2),
                            high=round(high_p, 2),
                            low=round(low_p, 2),
                            previous_close=round(prev_p, 2),
                            change=round(ch, 2),
                            change_percent=round(chp, 2),
                            volume=vol,
                            open_interest=oi,
                            status=status,
                            provider=self.provider_name,
                        )
                        quotes_map[int_sym] = nq
                        self._last_known_quotes[int_sym] = nq
                    return quotes_map
                else:
                    self._consecutive_failures += 1
                    logger.warning("fyers_quotes_api_error", response=data)
                    if "token" in str(data).lower() or "auth" in str(data).lower() or data.get("code") in (-100, 401, 403):
                        self.token_manager.mark_expired("FYERS token expired or invalid")
            elif resp.status_code in (401, 403):
                self._consecutive_failures += 1
                logger.warning("fyers_quotes_unauthorized", status_code=resp.status_code)
                self.token_manager.mark_expired(f"FYERS unauthorized (HTTP {resp.status_code})")
            else:
                self._consecutive_failures += 1
        except Exception as e:
            self._consecutive_failures += 1
            logger.debug("fyers_api_quotes_failed", error=str(e)[:150])
        return {}

    async def _fetch_fyers_history(
        self,
        symbol: str,
        resolution: str = "5",
        range_from: int | None = None,
        range_to: int | None = None,
    ) -> list[NormalizedCandle]:
        """Fetch historical candles directly from official FYERS History API v3."""
        try:
            token = await self.token_manager.get_valid_token()
        except Exception:
            token = ""
        if not token:
            from app.core.broker_runtime import get_config
            cfg_obj = get_config()
            if cfg_obj.provider == "fyers":
                token = cfg_obj.credentials.get("access_token") or ""

        if not is_usable_access_token(token):
            return []

        app_id = self.app_id
        if not app_id:
            from app.core.broker_runtime import get_config
            cfg_obj = get_config()
            if cfg_obj.provider == "fyers":
                app_id = cfg_obj.credentials.get("app_id") or ""

        auth_header = f"{app_id}:{token}" if app_id and ":" not in token else token
        fyers_sym = self.symbol_map.get(symbol, symbol)

        now_ts = int(datetime.now(timezone.utc).timestamp())
        from_ts = range_from or (now_ts - 86400 * 5)
        to_ts = range_to or now_ts

        res_map = {
            "1m": "1", "1": "1",
            "5m": "5", "5": "5",
            "15m": "15", "15": "15",
            "30m": "30", "30": "30",
            "1h": "60", "60m": "60", "60": "60",
            "4h": "240", "240m": "240", "240": "240",
            "1D": "D", "1d": "D", "D": "D",
            "1W": "W", "1w": "W", "W": "W",
        }
        res_str = res_map.get(resolution, "5")

        try:
            client = self._get_http_client(timeout=6.0)
            url = (
                f"https://api-t1.fyers.in/data/history"
                f"?symbol={fyers_sym}&resolution={res_str}&date_format=0"
                f"&range_from={from_ts}&range_to={to_ts}&cont_flag=1"
            )
            resp = await client.get(url, headers={"Authorization": auth_header})
            if resp.status_code in (401, 403):
                # Same honesty as the quotes path: a rejected history call
                # means the daily token is dead — park it so health/subsystems
                # and the poller say so instead of serving silent [] forever.
                # (A singleton holding a stale token after OAuth rotation used
                # to fail here on every timeframe while quotes stayed LIVE.)
                logger.warning("fyers_history_unauthorized", symbol=symbol, status_code=resp.status_code)
                self.token_manager.mark_expired(f"FYERS history unauthorized (HTTP {resp.status_code})")
                return []
            if resp.status_code == 200:
                    data = resp.json()
                    if data.get("s") == "ok" and "candles" in data and isinstance(data["candles"], list):
                        candles = []
                        for c in data["candles"]:
                            if len(c) >= 5:
                                ts = datetime.fromtimestamp(c[0], tz=timezone.utc)
                                candles.append(
                                    NormalizedCandle(
                                        timestamp=ts,
                                        open=float(c[1]),
                                        high=float(c[2]),
                                        low=float(c[3]),
                                        close=float(c[4]),
                                        volume=int(c[5]) if len(c) > 5 else 0,
                                        vwap=None,
                                    )
                                )
                        return candles
                    # FYERS answers some auth failures as HTTP 200 + s=error
                    # (mirrors the quotes path) — park the token so the outage
                    # is loud instead of an endless silent [].
                    if data.get("s") == "error" and (
                        "token" in str(data).lower()
                        or "auth" in str(data).lower()
                        or data.get("code") in (-100, 401, 403)
                    ):
                        logger.warning("fyers_history_auth_error", symbol=symbol, response=str(data)[:150])
                        self.token_manager.mark_expired("FYERS history token expired or invalid")
        except Exception as e:
            logger.debug("fyers_history_failed", symbol=symbol, error=str(e)[:150])
        return []

    async def get_quote(self, symbol: str) -> NormalizedQuote:
        """Fetch quote from FYERS API — returns OFFLINE if unauthenticated or unavailable."""
        await self.rate_limiter.acquire()
        now = datetime.now(timezone.utc)
        self.token_manager.record_message()

        # 1. Try official Fyers API batch/single quote
        fyers_res = await self._fetch_fyers_quotes([symbol])
        if symbol in fyers_res:
            return fyers_res[symbol]

        # 2. Check central_feed cache (from active broker stream)
        try:
            from app.services.central_feed import central_feed as _cf_fast
            _cached = _cf_fast.get_latest_tick(symbol)
            if _cached and _cached.ltp > 0:
                _ltp = float(_cached.ltp)
                _open = float(_cached.open) if _cached.open else _ltp
                _high = float(_cached.high) if _cached.high else _ltp
                _low = float(_cached.low) if _cached.low else _ltp
                _prev = float(_cached.close) if _cached.close else 0.0
                _change = round(_ltp - _prev, 2) if _prev else 0.0
                _change_pct = round((_change / _prev * 100) if _prev else 0.0, 2)
                is_open = calendar_service.is_market_open_now()
                nq = NormalizedQuote(
                    symbol=symbol,
                    display_name=symbol,
                    timestamp=_cached.timestamp,
                    ltp=round(_ltp, 2),
                    open=round(_open, 2),
                    high=round(_high, 2),
                    low=round(_low, 2),
                    previous_close=round(_prev, 2),
                    change=_change,
                    change_percent=_change_pct,
                    volume=int(_cached.volume) if _cached.volume else 0,
                    open_interest=_cached.open_interest,
                    status=DataStatus.CLOSED if not is_open else DataStatus.LIVE,
                    provider=self.provider_name,
                )
                self._last_known_quotes[symbol] = nq
                return nq
        except Exception:
            pass

        # 3. Check provider last known memory snapshot from broker
        if symbol in self._last_known_quotes:
            last = self._last_known_quotes[symbol]
            if last.ltp > 0:
                is_open = calendar_service.is_market_open_now()
                original_ts = getattr(last, "timestamp", None) or now
                return NormalizedQuote(
                    symbol=symbol,
                    display_name=symbol,
                    timestamp=original_ts,
                    ltp=last.ltp,
                    open=last.open,
                    high=last.high,
                    low=last.low,
                    previous_close=last.previous_close,
                    change=last.change,
                    change_percent=last.change_percent,
                    volume=last.volume,
                    open_interest=last.open_interest,
                    status=DataStatus.CLOSED if not is_open else DataStatus.STALE,
                    provider=self.provider_name,
                )

        # 4. No fake demo data — explicit OFFLINE
        return NormalizedQuote(
            symbol=symbol, display_name=symbol, timestamp=now,
            ltp=0.0, open=0.0, high=0.0, low=0.0,
            previous_close=0.0, change=0.0, change_percent=0.0,
            volume=0, open_interest=None,
            status=DataStatus.OFFLINE, provider=self.provider_name,
        )

    async def get_quotes(self, symbols: list[str] | None = None) -> list[NormalizedQuote]:
        targets = symbols or list(self.symbol_map.keys())
        fyers_map = await self._fetch_fyers_quotes(targets)
        quotes = []
        for sym in targets:
            if sym in fyers_map:
                quotes.append(fyers_map[sym])
            else:
                quotes.append(await self.get_quote(sym))
        return quotes

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "5m",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]:
        await self.rate_limiter.acquire()
        from_ts = int(start.timestamp()) if start else None
        to_ts = int(end.timestamp()) if end else None
        return await self._fetch_fyers_history(symbol, timeframe, from_ts, to_ts)

    async def get_index_cards(self) -> list[IndexCard]:
        quotes = await self.get_quotes()
        cards = []
        for q in quotes:
            cards.append(IndexCard(
                symbol=q.symbol,
                display_name=q.display_name,
                ltp=q.ltp,
                change=q.change,
                change_percent=q.change_percent,
                open=q.open,
                high=q.high,
                low=q.low,
                previous_close=q.previous_close,
                volume=q.volume,
                open_interest=q.open_interest,
                sparkline=[q.previous_close, q.ltp],
                status=q.status,
                timestamp=q.timestamp,
                provider=self.provider_name,
            ))
        return cards

    async def get_market_status(self) -> MarketStatusResponse:
        now = datetime.now(timezone.utc)
        is_trading = calendar_service.is_trading_day(now.date())
        is_open = calendar_service.is_market_open_now()
        return MarketStatusResponse(
            session=MarketSession.OPEN if is_open else MarketSession.CLOSED,
            market_time=now,
            is_trading_day=is_trading,
            data_status=DataStatus.CLOSED if not is_open else (DataStatus.LIVE if not self.token_manager.is_token_expired() else DataStatus.STALE),
            provider=self.provider_name,
        )

    async def get_health(self) -> MarketHealthStatus:
        self.token_manager.record_heartbeat()
        diag = self.token_manager.get_diagnostics()

        # Honest health: a locally-unexpired token means nothing if FYERS keeps
        # rejecting quote calls (stale daily token, revoked app). The poller
        # records RECONNECTING + consecutive failures in exactly that case, so
        # surface it instead of reporting HEALTHY/LIVE with zero data flowing.
        # When the market is closed, missing ticks are expected — don't cry wolf.
        token_ok = bool(diag["is_token_valid"]) and self.token_manager.state != ConnectionState.AUTH_EXPIRED
        flowing = (
            token_ok
            and self.token_manager.state == ConnectionState.CONNECTED
            and self._consecutive_failures == 0
        )
        try:
            market_open = calendar_service.is_market_open_now()
        except Exception:
            market_open = True  # fail honest: assume open so outages stay visible

        if not token_ok:
            status = "DEGRADED"
            mode = "OFFLINE"
            message = "Awaiting authentication token — re-auth FYERS (daily token expired/missing)"
        elif not market_open:
            status = "HEALTHY" if self._consecutive_failures == 0 else "DEGRADED"
            mode = "OFFLINE"
            message = "Market closed — serving last-known snapshot"
        elif flowing:
            status = "HEALTHY"
            mode = "LIVE"
            message = "FYERS API v3 connected"
        else:
            status = "DEGRADED"
            mode = "OFFLINE"
            message = (
                f"FYERS quote pipeline failing ({self._consecutive_failures} consecutive, "
                f"state={self.token_manager.state.value}) — re-auth FYERS if persistent"
            )

        return MarketHealthStatus(
            status=status,
            provider=self.provider_name,
            mode=mode,
            last_update=datetime.now(timezone.utc),
            data_age_seconds=diag["data_lag_seconds"] or 0.5,
            latency_ms=25.0,
            active_instruments=len(self.symbol_map),
            reconnect_count=diag["reconnect_count"],
            subscriptions=len(self.symbol_map),
            buffer_depth=0,
            dropped_events=0,
            circuit_breaker_state="CLOSED",
            last_heartbeat=datetime.now(timezone.utc),
            message=message,
        )

    async def get_market_breadth(self) -> MarketBreadthData:
        now = datetime.now(timezone.utc)
        is_open = calendar_service.is_market_open_now()
        quotes = [q for q in self._last_known_quotes.values() if q.ltp > 0]
        if quotes:
            adv = sum(1 for q in quotes if q.change > 0)
            dec = sum(1 for q in quotes if q.change < 0)
            unc = sum(1 for q in quotes if q.change == 0)
            total = adv + dec + unc
            ratio = round(adv / dec, 2) if dec > 0 else (float(adv) if adv > 0 else 1.0)
            score = round((adv / total) * 100, 1) if total > 0 else 50.0
            sentiment = "NEUTRAL"
            if score >= 70:
                sentiment = "VERY_BULLISH"
            elif score >= 55:
                sentiment = "BULLISH"
            elif score <= 30:
                sentiment = "VERY_BEARISH"
            elif score <= 45:
                sentiment = "BEARISH"
            return MarketBreadthData(
                advancing=adv,
                declining=dec,
                unchanged=unc,
                advance_decline_ratio=ratio,
                sectors=[],
                sentiment=sentiment,
                sentiment_score=score,
                status=DataStatus.LIVE if is_open else DataStatus.CLOSED,
                timestamp=now,
            )
        return MarketBreadthData(
            advancing=0,
            declining=0,
            unchanged=0,
            advance_decline_ratio=1.0,
            sectors=[],
            sentiment="NEUTRAL",
            sentiment_score=50.0,
            status=DataStatus.OFFLINE,
            timestamp=now,
        )

    async def get_expiries(self, symbol: str) -> list[datetime]:
        from app.services.contract_master import contract_master_service
        sym_upper = symbol.upper().replace(" ", "")
        if "BANK" in sym_upper:
            underlying = "BANKNIFTY"
        elif "FIN" in sym_upper:
            underlying = "FINNIFTY"
        elif "SENSEX" in sym_upper:
            underlying = "SENSEX"
        else:
            underlying = "NIFTY"
        dates = contract_master_service.get_expiries(underlying)
        return [datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) for d in dates]

    async def get_option_chain(
        self,
        symbol: str,
        expiry: datetime | None = None,
    ) -> list[NormalizedOptionQuote]:
        await self.rate_limiter.acquire()

        sym_upper = symbol.upper().replace(" ", "").replace("INDEX", "")
        if "BANK" in sym_upper:
            underlying = "BANKNIFTY"
            fyers_sym = "NSE:NIFTYBANK-INDEX"
            strike_step = 100.0
        elif "FIN" in sym_upper:
            underlying = "FINNIFTY"
            fyers_sym = "NSE:FINNIFTY-INDEX"
            strike_step = 50.0
        elif "SENSEX" in sym_upper:
            underlying = "SENSEX"
            fyers_sym = "BSE:SENSEX-INDEX"
            strike_step = 100.0
        else:
            underlying = "NIFTY"
            fyers_sym = "NSE:NIFTY50-INDEX"
            strike_step = 50.0

        # Attempt Live Fetch from FYERS API v3
        try:
            token = await self.token_manager.get_valid_token()
        except Exception:
            token = ""
        if not token:
            from app.core.broker_runtime import get_config
            cfg_obj = get_config()
            if cfg_obj.provider == "fyers":
                token = cfg_obj.credentials.get("access_token") or ""

        app_id = self.app_id
        if not app_id:
            from app.core.broker_runtime import get_config
            cfg_obj = get_config()
            if cfg_obj.provider == "fyers":
                app_id = cfg_obj.credentials.get("app_id") or ""

        if is_usable_access_token(token):
            auth_header = f"{app_id}:{token}" if app_id and ":" not in token else token
            # FYERS validates `timestamp` against its own expiry calendar
            # (see options-chain-v3 `expiryData`). Our local calendar bootstrap
            # (Thursday rule) can drift from the broker truth (e.g. Tuesday
            # NIFTY weeklies), in which case FYERS answers
            # `s=error "Please provide valid expiry"` and the chain would come
            # back empty. Fall back to the broker's nearest expiry instead of
            # serving an empty chain — all data stays live FYERS truth.
            param_sets: list[dict[str, str | int]] = []
            if expiry:
                param_sets.append({"symbol": fyers_sym, "strikecount": 40, "timestamp": str(int(expiry.timestamp()))})
            param_sets.append({"symbol": fyers_sym, "strikecount": 40})
            try:
                client = self._get_http_client(timeout=5.0)
                for attempt, params in enumerate(param_sets):
                    try:
                        resp = await client.get(
                            "https://api-t1.fyers.in/data/options-chain-v3",
                            params=params,
                            headers={"Authorization": auth_header},
                        )
                    except Exception as e:
                        logger.debug("fyers_option_chain_api_failed", error=str(e))
                        continue
                    if resp.status_code != 200:
                        continue
                    try:
                        data = resp.json()
                    except Exception:
                        continue
                    if data.get("s") != "ok" or "data" not in data:
                        if attempt == 0 and len(param_sets) > 1:
                            logger.debug(
                                "fyers_option_chain_expiry_rejected_fallback_latest",
                                underlying=underlying,
                                detail=str(data.get("message"))[:120],
                            )
                        continue
                    chain_items = data["data"].get("optionsChain", [])
                    if not chain_items:
                        continue
                    quotes: list[NormalizedOptionQuote] = []
                    now = datetime.now(timezone.utc)
                    # True expiry labelling: the broker honours an explicit
                    # timestamp with that expiry; the nearest-expiry fallback
                    # carries the broker calendar date from `expiryData`
                    # (never the stale requested date, never today).
                    broker_expiry = _nearest_fyers_expiry(data["data"].get("expiryData"))
                    if attempt == 0 and expiry is not None:
                        exp_dt = expiry
                    elif broker_expiry is not None:
                        exp_dt = datetime.combine(broker_expiry, datetime.min.time(), tzinfo=timezone.utc)
                    else:
                        exp_dt = now
                    for item in chain_items:
                        strike = float(item.get("strike_price", 0.0))
                        opt_type = str(item.get("option_type", "")).upper()
                        if not strike or opt_type not in ("CE", "PE"):
                            continue
                        ltp = float(item.get("ltp") or 0.0)
                        oi = int(item.get("oi") or 0)
                        vol = int(item.get("volume") or 0)
                        raw_bid = item.get("bid")
                        raw_ask = item.get("ask")
                        bid = float(raw_bid) if raw_bid not in (None, "") else (round(ltp - 0.25, 2) if ltp > 0 else 0.0)
                        ask = float(raw_ask) if raw_ask not in (None, "") else (round(ltp + 0.25, 2) if ltp > 0 else 0.0)
                        bid = max(0.0, bid)
                        ask = max(0.0, ask)
                        oi_chg = int(item.get("oich") or item.get("oi_change") or 0)
                        prev_p = float(item.get("prev_close_price") or ltp)
                        chg = float(item.get("ch") or (round(ltp - prev_p, 2) if prev_p else 0.0))
                        chg_pct = float(item.get("chp") or 0.0)
                        contract_id = item.get("symbol") or f"{underlying}_{int(strike)}_{opt_type}"

                        quotes.append(
                            NormalizedOptionQuote(
                                timestamp=now,
                                provider=self.PROVIDER_ID,
                                instrument=contract_id,
                                contract_id=contract_id,
                                underlying=underlying,
                                expiry=exp_dt,
                                strike=strike,
                                option_type=opt_type,
                                ltp=round(ltp, 2),
                                bid=round(bid, 2),
                                ask=round(ask, 2),
                                volume=vol,
                                oi=oi,
                                oi_change=oi_chg,
                                change=round(chg, 2),
                                change_percent=round(chg_pct, 2),
                                previous_close=round(prev_p, 2),
                            )
                        )
                    if quotes:
                        if attempt == 1 and expiry:
                            logger.info(
                                "fyers_option_chain_served_latest_expiry",
                                symbol=underlying,
                                actual_expiry=exp_dt.date().isoformat(),
                            )
                        return quotes
            except Exception as e:
                logger.debug("fyers_option_chain_api_failed", error=str(e))

        # THE TRUTH OF WALL: All market data must come from broker API only.
        # If the broker option chain API is unavailable, fails, or token is expired,
        # return an empty list — NEVER fabricate synthetic strikes or fake open interest.
        logger.warning("fyers_option_chain_unavailable", symbol=underlying)
        return []

    def _get_start_lock(self) -> asyncio.Lock:
        if self._start_lock is None:
            self._start_lock = asyncio.Lock()
        return self._start_lock

    # ── Inbound tick sanity ──────────────────────────────────────────────
    def _quote_passes_sanity(self, sym: str, q) -> bool:
        """Validate an inbound quote BEFORE it reaches central_feed.

        Returns False (and records the rejection) when the quote is
        implausible: an LTP jump beyond tick_sanity_jump_pct vs the last
        accepted tick, or incoherent intraday OHLC
        (low <= {open, ltp} <= high).

        NOTE: previous_close is yesterday's settlement and is NEVER required
        to sit inside today's [low, high] — on gap up/down days it sits
        outside the day's range by definition. Constraining it froze gap-day
        symbols (e.g. BANKNIFTY) for the whole session: every tick rejected,
        no WS ticks, frontend card stuck at the REST snapshot. It is validated
        separately (positive + within 20% of LTP) to catch corrupt values.
        A rejected tick is a gap, never a repair — nothing corrected is
        emitted in its place.
        """
        ltp = float(getattr(q, "ltp", 0) or 0)
        if not ltp > 0:
            self._record_sanity_reject(sym, "non_positive_ltp", q)
            return False

        low = getattr(q, "low", None)
        high = getattr(q, "high", None)
        open_p = getattr(q, "open", None) or ltp
        prev = getattr(q, "previous_close", None) or 0.0

        try:
            low_f = float(low) if low is not None else None
        except (TypeError, ValueError):
            low_f = None
        try:
            high_f = float(high) if high is not None else None
        except (TypeError, ValueError):
            high_f = None

        # Corrupt range guard (high/low swapped or zeroed).
        if (
            low_f is not None and high_f is not None
            and low_f > 0 and high_f > 0 and low_f > high_f
        ):
            self._record_sanity_reject(sym, "ohlc_range_inverted", q)
            return False

        # Tolerance scales with price: broker open/high/low/ltp fields can
        # jitter by a tick between reads; a fixed 0.0025 tolerance rejected
        # valid 56k-index ticks on rounding noise.
        eps = max(0.10, ltp * 0.0002)
        if low_f is not None and low_f > 0:
            if open_p < low_f - eps or ltp < low_f - eps:
                self._record_sanity_reject(sym, "ohlc_incoherent", q)
                return False
        if high_f is not None and high_f > 0:
            if open_p > high_f + eps or ltp > high_f + eps:
                self._record_sanity_reject(sym, "ohlc_incoherent", q)
                return False

        # previous_close sanity: must be sane, not inside today's range.
        try:
            prev_f = float(prev) if prev else 0.0
        except (TypeError, ValueError):
            prev_f = 0.0
        if prev_f and prev_f > 0:
            if abs(ltp - prev_f) / prev_f > 0.20:
                self._record_sanity_reject(sym, "prev_close_implausible", q)
                return False

        last = self._last_accepted_ltp.get(sym)
        if last is not None and last > 0:
            jump_pct = abs(q.ltp - last) / last * 100.0
            if jump_pct > settings.tick_sanity_jump_pct:
                self._record_sanity_reject(sym, f"ltp_jump_{jump_pct:.2f}pct", q)
                return False

        self._last_accepted_ltp[sym] = q.ltp
        return True

    def _record_sanity_reject(self, sym: str, reason: str, q) -> None:
        import time as _time

        now_m = _time.monotonic()
        self._sanity_reject_events.append((now_m, sym))
        # Keep only the alert window.
        cutoff = now_m - self._SANITY_REJECT_WINDOW_S
        self._sanity_reject_events = [
            (ts, s) for (ts, s) in self._sanity_reject_events if ts >= cutoff
        ]
        window_count = sum(1 for _, s in self._sanity_reject_events if s == sym)
        logger.warning(
            "tick_sanity_rejected",
            symbol=sym,
            reason=reason,
            ltp=getattr(q, "ltp", None),
            high=getattr(q, "high", None),
            low=getattr(q, "low", None),
            window_count=window_count,
            note="Tick dropped — gap, not repair (no synthetic substitute)",
        )
        if window_count >= self._SANITY_REJECT_ALERT_THRESHOLD and sym not in self._sanity_alerted:
            self._sanity_alerted.add(sym)
            logger.error(
                "tick_sanity_sustained_rejections",
                symbol=sym,
                window_count=window_count,
                window_s=self._SANITY_REJECT_WINDOW_S,
                hint="Feed may be corrupted — downstream sees a gap until quotes normalize",
            )

    def sanity_rejection_count(self) -> int:
        """Total rejections still inside the alert window (for /health/subsystems)."""
        import time as _time

        if not self._sanity_reject_events:
            return 0
        cutoff = _time.monotonic() - self._SANITY_REJECT_WINDOW_S
        return sum(1 for ts, _ in self._sanity_reject_events if ts >= cutoff)

    async def _poller_loop(self) -> None:
        """Backend-owned FYERS poller -> central_feed, with backoff reconnect.

        Runs for the lifetime of the backend process (started once at backend
        startup). Survives transient failures via TokenManager exponential
        backoff; only stops at backend shutdown or backend-owned restart.
        Frontend connects/disconnects never touch this loop.
        """
        from app.services.central_feed import central_feed as _cf
        logger.info("fyers_poller_loop_started", interval_s=1.0)
        symbols = list(self.symbol_map.keys())
        while self._stream_running:
            delay = 1.0
            try:
                now = datetime.now(timezone.utc)
                quotes_map = await self._fetch_fyers_quotes(symbols)
                if quotes_map:
                    self._consecutive_failures = 0
                    if self.token_manager.state != ConnectionState.CONNECTED:
                        self.token_manager.set_state(ConnectionState.CONNECTED)
                    self.token_manager.record_message()
                    for sym, q in quotes_map.items():
                        if q.ltp <= 0:
                            continue
                        # Inbound sanity gate: a corrupted quote becomes a gap,
                        # never a trade input (Truth of Wall).
                        if not self._quote_passes_sanity(sym, q):
                            continue
                        tick = TickEvent(
                            timestamp=now,
                            symbol=sym,
                            instrument_token=self.symbol_map.get(sym, sym),
                            ltp=q.ltp,
                            open=q.open,
                            high=q.high,
                            low=q.low,
                            close=q.previous_close or q.ltp,
                            volume=q.volume,
                            provider=self.PROVIDER_ID,
                            priority=EventPriority.HIGH,
                        )
                        await _cf.ingest_tick(tick)
                else:
                    # No fresh quotes: auth/network failure OR market closed.
                    # Truth-of-Wall: never re-publish stale ticks as live while open.
                    # Auth-expired parks the poller at 15s idle (no FYERS hammering)
                    # until re-auth; network blips back off exponentially.
                    if self.token_manager.is_token_expired() or self.token_manager.state == ConnectionState.AUTH_EXPIRED:
                        if self.token_manager.state != ConnectionState.AUTH_EXPIRED:
                            self.token_manager.mark_expired("FYERS daily token expired — re-auth required, poller parked")
                        delay = 15.0
                        logger.info(
                            "fyers_poller_parked_auth_expired",
                            delay_s=delay,
                            hint="Re-auth FYERS via /api/v1/tokens/fyers/auth-url — no synthetic ticks emitted",
                        )
                    else:
                        self._consecutive_failures += 1
                        delay = self.token_manager.record_reconnect_attempt()
                        logger.warning(
                            "fyers_poller_no_quotes_backoff",
                            consecutive_failures=self._consecutive_failures,
                            delay_s=delay,
                        )
                    if not calendar_service.is_market_open_now():
                        # Market closed — do not spoof fresh timestamps into central feed
                        pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._consecutive_failures += 1
                try:
                    delay = self.token_manager.record_reconnect_attempt()
                except Exception:
                    delay = min(60.0, 1.0 * (2 ** min(self._consecutive_failures, 6)))
                logger.debug("fyers_poller_error", error=str(e)[:150], delay_s=delay)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break
        logger.info("fyers_poller_loop_stopped")

    async def start_stream(self) -> None:
        """Idempotent backend-owned start — one REST poller per instance max.

        Interface name `start_stream` is kept for MarketDataProvider compat,
        but this is a 1s REST poller, not a websocket stream.
        """
        lock = self._get_start_lock()
        async with lock:
            if self._stream_running and self._poll_task and not self._poll_task.done():
                return
            # Drop any dead task handle before starting a fresh loop.
            self._poll_task = None
            self._stream_task = None
            self._stream_running = True
            self._consecutive_failures = 0
            self.token_manager.set_state(ConnectionState.CONNECTING)
            logger.info("fyers_stream_started", mode="poller")
            self._poll_task = asyncio.create_task(self._poller_loop())
            self._stream_task = self._poll_task

    async def stop_stream(self) -> None:
        """Backend-owned stop (shutdown / restart only — never frontend)."""
        lock = self._get_start_lock()
        async with lock:
            if not self._stream_running and not self._poll_task and not self._stream_task:
                return
            self._stream_running = False
            self.token_manager.set_state(ConnectionState.MANUAL_STOP)
            for t in (self._poll_task, self._stream_task):
                if t and t is not asyncio.current_task():
                    try:
                        t.cancel()
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass
                    except Exception:
                        pass
            self._poll_task = None
            self._stream_task = None
            if self._http_client and not self._http_client.is_closed:
                try:
                    await self._http_client.aclose()
                except Exception:
                    pass
                self._http_client = None
            logger.info("fyers_stream_stopped")
