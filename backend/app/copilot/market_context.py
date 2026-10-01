"""Parallel market-context acquisition (spec §4, §23, §26).

One MarketContext per analysis, built from the SAME DROID services the rest of
the terminal uses (no parallel calculation system). Every source is fetched
concurrently, individually timed out and individually allowed to fail — a dead
source becomes `None` + an UNAVAILABLE/ERROR freshness record, never an invented
value.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import structlog

from app.copilot.models import (
    DataQualityBlock,
    FuturesContext,
    HistoricalContext,
    InstitutionalFlowContext,
    MarketContext,
    OptionsContext,
    PriceContext,
    RegimeContext,
    SourceFreshness,
    TechnicalContext,
)
from app.services.calendar_service import calendar_service
from app.services.market_service import MarketService
from app.services.regime_service import regime_service

logger = structlog.get_logger()

#: Per-source timeout. A slow source degrades to UNAVAILABLE rather than
#: holding the whole analysis hostage.
SOURCE_TIMEOUT_SECONDS = 12.0
#: Short-lived context cache (spec §26). Deliberately ≤ one 5m candle so a cached
#: context can never be presented as newer than the market data behind it.
CONTEXT_CACHE_TTL_SECONDS = 20.0
_CACHE_MAX_ENTRIES = 32

#: Freshness policy per source kind (seconds before we call it STALE).
FRESHNESS_POLICY: dict[str, float] = {
    "quote": 60.0,
    "regime": 300.0,
    "vwap": 300.0,
    "options": 300.0,
    "futures": 300.0,
    "flow": 86_400.0 * 2,  # FII/DII is a daily publication
    "historical": 86_400.0 * 365,
}

SOURCE_LABELS: dict[str, str] = {
    "quote": "Quote",
    "regime": "Regime & technicals",
    "vwap": "Session VWAP",
    "options": "Options chain",
    "futures": "Futures",
    "flow": "Institutional flow",
    "historical": "Historical analogs",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _norm_symbol(symbol: str) -> str:
    from app.copilot.enums import SUPPORTED_SYMBOLS

    compact = (symbol or "").upper().replace(" ", "")
    for sym in SUPPORTED_SYMBOLS:
        if compact == sym:
            return sym
    if compact == "NIFTY50":
        return "NIFTY"
    if compact == "BSESENSEX":
        return "SENSEX"
    return compact or "NIFTY"


class _TTLContextCache:
    """Tiny bounded TTL cache keyed by symbol+horizon+tool set+time bucket."""

    def __init__(self, ttl_seconds: float, max_entries: int = _CACHE_MAX_ENTRIES) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._store: dict[str, tuple[float, MarketContext]] = {}

    def _key(self, symbol: str, horizon: str, need: tuple[str, ...]) -> str:
        bucket = int(time.time() // self.ttl_seconds)
        return f"{symbol}|{horizon}|{','.join(need)}|{bucket}"

    def get(self, symbol: str, horizon: str, need: tuple[str, ...]) -> MarketContext | None:
        key = self._key(symbol, horizon, need)
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value.model_copy(deep=True)

    def put(self, symbol: str, horizon: str, need: tuple[str, ...], value: MarketContext) -> None:
        if len(self._store) >= self.max_entries:
            oldest = min(self._store.items(), key=lambda kv: kv[1][0])[0]
            self._store.pop(oldest, None)
        self._store[self._key(symbol, horizon, need)] = (
            time.time() + self.ttl_seconds,
            value.model_copy(deep=True),
        )

    def clear(self) -> None:
        self._store.clear()


context_cache = _TTLContextCache(CONTEXT_CACHE_TTL_SECONDS)


class MarketContextBuilder:
    """Builds a normalized MarketContext from live DROID services."""

    def __init__(
        self,
        market_service: MarketService | None = None,
        historical_adapter: Callable[[str, str], Awaitable[HistoricalContext]] | None = None,
    ) -> None:
        self.market_service = market_service or MarketService()
        self._historical_adapter = historical_adapter

    # ------------------------------------------------------------------ #
    # Individual gatherers — thin adapters over existing services
    # ------------------------------------------------------------------ #
    async def _gather_quote(self, symbol: str) -> Any:
        return await self.market_service.get_quote(symbol)

    async def _gather_regime(self, symbol: str) -> Any:
        return await regime_service.classify_market_regime(symbol)

    async def _gather_vwap(self, symbol: str) -> Any:
        """Session VWAP via existing DROID `calculate_intraday_vwap`."""
        candles = await self.market_service.get_candles(symbol, timeframe="5m")
        if not candles:
            return None
        from app.research.features import calculate_intraday_vwap

        rows = [
            {"high": c.high, "low": c.low, "close": c.close, "volume": float(c.volume or 0.0)}
            for c in candles
        ]
        return {"vwap": calculate_intraday_vwap(rows), "candle_timestamp": candles[-1].timestamp}

    async def _gather_options(self, symbol: str) -> Any:
        from app.services.options_service import options_service

        return await options_service.get_option_chain_matrix(symbol)

    async def _gather_futures(self, symbol: str) -> Any:
        from app.services.ai_service import _fetch_futures_safe

        return await _fetch_futures_safe(symbol)

    async def _gather_flow(self, symbol: str) -> Any:
        from app.services.fii_dii_service import FIIDIIService

        return await asyncio.to_thread(FIIDIIService().get_institutional_overview)

    async def _gather_historical(self, symbol: str, horizon: str) -> HistoricalContext:
        if self._historical_adapter is not None:
            return await self._historical_adapter(symbol, horizon)
        from app.copilot.historical_analog import historical_analog_engine

        return await historical_analog_engine.query(symbol, horizon)

    # ------------------------------------------------------------------ #
    # Parallel acquisition
    # ------------------------------------------------------------------ #
    async def build(self, symbol: str, horizon: str, need: set[str], use_cache: bool = True) -> MarketContext:
        sym = _norm_symbol(symbol)
        needs = tuple(sorted(need))
        if use_cache:
            cached = context_cache.get(sym, horizon, needs)
            if cached is not None:
                return cached

        ctx = MarketContext(symbol=sym, horizon=horizon)  # type: ignore[arg-type]
        ctx.market_status = self._market_status()
        sources: list[SourceFreshness] = []

        jobs: dict[str, Awaitable[Any]] = {}
        if "quote" in need or "regime" in need:
            jobs["quote"] = self._timed("quote", self._gather_quote(sym))
        if "regime" in need:
            jobs["regime"] = self._timed("regime", self._gather_regime(sym))
            jobs["vwap"] = self._timed("vwap", self._gather_vwap(sym))
        if "options" in need:
            jobs["options"] = self._timed("options", self._gather_options(sym))
        if "futures" in need:
            jobs["futures"] = self._timed("futures", self._gather_futures(sym))
        if "flow" in need:
            jobs["flow"] = self._timed("flow", self._gather_flow(sym))

        results: dict[str, Any] = {}
        if jobs:
            settled = await asyncio.gather(*jobs.values(), return_exceptions=True)
            for name, value in zip(jobs.keys(), settled):
                results[name] = value

        for name in ("quote", "regime", "vwap", "options", "futures", "flow"):
            value = results.get(name)
            if value is not None:
                sources.append(self._freshness(name, "FRESH", value))
            elif name in need or (name == "vwap" and "regime" in need):
                sources.append(self._freshness(name, "UNAVAILABLE", None, detail="no data returned"))

        self._apply_quote(ctx, results.get("quote"))
        self._apply_regime(ctx, results.get("regime"), results.get("vwap"))
        self._apply_options(ctx, results.get("options"))
        self._apply_futures(ctx, results.get("futures"))
        self._apply_flow(ctx, results.get("flow"), sources)

        ctx.data_quality = self._quality(ctx, sources)
        ctx.missing_sources = sorted(
            {s.source for s in sources if s.status in ("UNAVAILABLE", "ERROR")}
            | set(ctx.data_quality.missing_fields)
        )
        ctx.partial = bool(ctx.missing_sources) or bool(ctx.data_quality.stale_sources)

        if use_cache:
            context_cache.put(sym, horizon, needs, ctx)
        return ctx

    async def _timed(self, name: str, coro: Awaitable[Any]) -> Any:
        try:
            return await asyncio.wait_for(coro, timeout=SOURCE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning("copilot_source_timeout", source=name, timeout_s=SOURCE_TIMEOUT_SECONDS)
            return None
        except Exception as exc:  # one dead source must not kill the analysis
            logger.warning("copilot_source_failed", source=name, error=str(exc)[:240])
            return None

    @staticmethod
    def _market_status() -> str:
        try:
            permission = calendar_service.can_trade_now()
            return "OPEN" if permission.allowed else permission.reason
        except Exception:
            return "UNKNOWN"

    # ------------------------------------------------------------------ #
    # Normalization
    # ------------------------------------------------------------------ #
    @staticmethod
    def _apply_quote(ctx: MarketContext, quote: Any) -> None:
        if quote is None:
            return
        ctx.price = PriceContext(
            ltp=getattr(quote, "ltp", None),
            change_pct=getattr(quote, "change_percent", None),
            day_high=getattr(quote, "high", None),
            day_low=getattr(quote, "low", None),
            day_open=getattr(quote, "open", None),
            previous_close=getattr(quote, "previous_close", None),
            volume=float(getattr(quote, "volume", 0) or 0) or None,
        )

    @staticmethod
    def _apply_regime(ctx: MarketContext, regime: Any, vwap_payload: Any) -> None:
        indicators = getattr(regime, "indicators", None)
        levels = getattr(regime, "key_levels", None)
        vix = getattr(regime, "vix_regime", None)
        classic = getattr(levels, "classic_pivots", None)
        session_vwap = vwap_payload.get("vwap") if isinstance(vwap_payload, dict) else None
        ctx.regime = RegimeContext(
            name=getattr(regime, "regime_state", "UNKNOWN") or "UNKNOWN",
            summary=getattr(regime, "summary_headline", None),
            trend_strength=getattr(indicators, "adx_14", None),
            volatility_state=getattr(vix, "regime_category", None),
            adx=getattr(indicators, "adx_14", None),
            vix=getattr(vix, "vix_value", None),
            vix_category=getattr(vix, "regime_category", None),
            classification_confidence=getattr(regime, "confidence_score", None),
        )
        ctx.technicals = TechnicalContext(
            rsi=getattr(indicators, "rsi_14", None),
            vwap=session_vwap,
            supertrend=getattr(indicators, "supertrend_value", None),
            supertrend_direction=getattr(indicators, "supertrend_direction", None),
            atr=getattr(indicators, "atr_14", None),
            poc=getattr(levels, "poc", None),
            vah=getattr(levels, "vah", None),
            val=getattr(levels, "val", None),
            ema_20=getattr(indicators, "ema_20", None),
            ema_50=getattr(indicators, "ema_50", None),
            sma_200=getattr(indicators, "sma_200", None),
            bollinger_bandwidth=getattr(indicators, "bollinger_bandwidth", None),
            bollinger_pct_b=getattr(indicators, "bollinger_pct_b", None),
            plus_di=getattr(indicators, "plus_di", None),
            minus_di=getattr(indicators, "minus_di", None),
            prior_day_high=getattr(levels, "prior_day_high", None),
            prior_day_low=getattr(levels, "prior_day_low", None),
            prior_day_close=getattr(levels, "prior_day_close", None),
            pivot=getattr(classic, "pivot", None),
            r1=getattr(classic, "r1", None),
            r2=getattr(classic, "r2", None),
            s1=getattr(classic, "s1", None),
            s2=getattr(classic, "s2", None),
        )

    @staticmethod
    def _apply_options(ctx: MarketContext, chain: Any) -> None:
        if chain is None:
            return
        analytics = getattr(chain, "analytics", None)
        strikes = getattr(chain, "strikes", None) or []
        call_wall = put_wall = None
        try:
            calls = [s for s in strikes if getattr(s, "call", None)]
            puts = [s for s in strikes if getattr(s, "put", None)]
            if calls:
                call_wall = float(max(calls, key=lambda s: s.call.open_interest or 0).strike)
            if puts:
                put_wall = float(max(puts, key=lambda s: s.put.open_interest or 0).strike)
        except Exception:  # defensive only — a malformed ladder degrades to null walls
            call_wall = put_wall = None
        ctx.options = OptionsContext(
            pcr_oi=getattr(analytics, "pcr_oi", None),
            pcr_volume=getattr(analytics, "pcr_volume", None),
            max_pain=getattr(chain, "max_pain", None) or getattr(analytics, "max_pain_strike", None),
            atm_iv=getattr(analytics, "atm_iv", None),
            iv_skew=getattr(analytics, "iv_skew", None),
            call_wall=call_wall,
            put_wall=put_wall,
            expiry=getattr(chain, "expiry", None),
            total_call_oi=getattr(analytics, "total_call_oi", None),
            total_put_oi=getattr(analytics, "total_put_oi", None),
            time_to_expiry_days=getattr(analytics, "time_to_expiry_days", None),
        )

    @staticmethod
    def _apply_futures(ctx: MarketContext, futures: Any) -> None:
        if futures is None:
            return
        term = getattr(futures, "term_structure", None)
        contracts = getattr(term, "contracts", None) or []
        near = contracts[0] if contracts else None
        buildup = getattr(futures, "buildup", None)
        rollover = getattr(futures, "rollover", None)
        ctx.futures = FuturesContext(
            contract_price=getattr(near, "ltp", None),
            basis=getattr(near, "basis", None),
            basis_pct=getattr(near, "basis_percent", None),
            oi_change_pct=getattr(near, "oi_change_percent", None),
            positioning=getattr(buildup, "buildup_type", None),
            positioning_note=getattr(buildup, "interpretation", None),
            rollover_pct=getattr(rollover, "rollover_percent", None),
            curve_state=getattr(term, "curve_state", None),
        )

    @staticmethod
    def _apply_flow(ctx: MarketContext, overview: Any, sources: list[SourceFreshness]) -> None:
        if overview is None:
            return
        fii = float(getattr(overview, "fii_cash_net_crores", 0.0) or 0.0)
        dii = float(getattr(overview, "dii_cash_net_crores", 0.0) or 0.0)
        live = bool(getattr(overview, "live_available", False))
        ctx.institutional_flow = InstitutionalFlowContext(
            fii=fii,
            dii=dii,
            net_flow=fii + dii,
            sentiment=getattr(overview, "institutional_sentiment", None),
            as_of=getattr(overview, "as_of", None),
            live=live,
        )
        if not live:
            # Truth-of-wall: FII/DII is a static snapshot, never present as live.
            for record in sources:
                if record.source == "flow":
                    record.status = "STALE"
                    record.detail = (
                        "Static FII/DII snapshot (no live feed wired) — context only, not today's flow."
                    )

    # ------------------------------------------------------------------ #
    # Freshness (spec §23)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _freshness(name: str, status: str, payload: Any, detail: str | None = None) -> SourceFreshness:
        timestamp = MarketContextBuilder._source_timestamp(name, payload)
        age = None
        if timestamp is not None:
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            age = max(0.0, (_utcnow() - timestamp).total_seconds())
        if age is not None and status == "FRESH" and age > FRESHNESS_POLICY.get(name, 300.0):
            status = "STALE"
            detail = detail or f"age {age:.0f}s exceeds {FRESHNESS_POLICY.get(name, 300.0):.0f}s policy"
        return SourceFreshness(
            source=name,
            label=SOURCE_LABELS.get(name, name),
            timestamp=timestamp,
            age_seconds=age,
            status=status,  # type: ignore[arg-type]
            detail=detail,
        )

    @staticmethod
    def _source_timestamp(name: str, payload: Any) -> datetime | None:
        if payload is None:
            return None
        if name == "vwap" and isinstance(payload, dict):
            return payload.get("candle_timestamp")
        return getattr(payload, "timestamp", None)

    # ------------------------------------------------------------------ #
    # Data quality (spec §9, §23)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _quality(ctx: MarketContext, sources: list[SourceFreshness]) -> DataQualityBlock:
        missing: list[str] = []
        stale: list[str] = []
        notes: list[str] = []

        def require(value: Any, field: str) -> None:
            if value is None:
                missing.append(field)

        require(ctx.price.ltp, "price.ltp")
        require(ctx.regime.name if ctx.regime.name != "UNKNOWN" else None, "regime.name")
        require(ctx.technicals.rsi, "technicals.rsi")
        require(ctx.technicals.atr, "technicals.atr")
        if "options" in ctx.missing_sources:
            missing.append("options")
        if "futures" in ctx.missing_sources:
            missing.append("futures")

        for record in sources:
            if record.status in ("UNAVAILABLE", "ERROR"):
                if record.source not in missing:
                    missing.append(record.source)
            elif record.status == "STALE":
                stale.append(record.source)

        available = len([s for s in sources if s.status in ("FRESH", "STALE")])
        critical_missing = [m for m in missing if m in ("price.ltp", "regime.name", "quote", "regime")]
        optional_missing = [m for m in missing if m not in critical_missing]

        if critical_missing:
            overall = "LOW"
        elif stale or optional_missing:
            overall = "MEDIUM"
        elif available >= 4:
            overall = "HIGH"
        else:
            overall = "MEDIUM"

        if ctx.institutional_flow.sentiment and not ctx.institutional_flow.live:
            notes.append("Institutional flow is a static daily snapshot, not live positioning.")
        if ctx.market_status not in ("OPEN", "UNKNOWN"):
            notes.append(f"Market session: {ctx.market_status} — intraday freshness relaxes accordingly.")

        return DataQualityBlock(
            overall=overall,  # type: ignore[arg-type]
            missing_fields=sorted(set(missing)),
            stale_sources=sorted(set(stale)),
            sources=sources,
            notes=notes,
        )


market_context_builder = MarketContextBuilder()
