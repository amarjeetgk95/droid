"""
Market Data Engine — §5 + Technical Analysis §11 + MTF §12 + F&O §13 + Options Selection §14-15

Normalized MarketData decoupled from provider structs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Literal
import structlog

from app.algo.money import D

logger = structlog.get_logger()


@dataclass
class MarketData:
    instrument_id: str
    symbol: str
    timestamp: datetime
    price: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    previous_close: Decimal | None = None
    volume: int | None = None
    open_interest: int | None = None
    oi_change: int | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: int | None = None
    ask_size: int | None = None
    expiry: datetime | None = None
    derivative_metrics: dict = field(default_factory=dict)  # IV, Greeks, PCR etc

    @classmethod
    def from_provider(cls, raw: dict, instrument_id: str, symbol: str) -> "MarketData":
        """Normalize provider-specific response — strategy never touches raw."""
        # Try common keys with fallbacks
        def dec(k, default=None):
            v = raw.get(k, raw.get(k.lower(), default))
            return D(v) if v is not None else default
        def ints(k, default=None):
            v = raw.get(k, raw.get(k.lower(), default))
            return int(v) if v is not None else default

        ts = raw.get("timestamp") or raw.get("last_updated") or raw.get("time") or datetime.now(timezone.utc)
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        return cls(
            instrument_id=instrument_id,
            symbol=symbol,
            timestamp=ts,
            price=dec("ltp") or dec("price") or dec("last_price") or D(0),
            open=dec("open"),
            high=dec("high"),
            low=dec("low"),
            previous_close=dec("previous_close") or dec("prev_close"),
            volume=ints("volume"),
            open_interest=ints("open_interest") or ints("oi"),
            oi_change=ints("oi_change"),
            bid=dec("bid"),
            ask=dec("ask"),
            bid_size=ints("bid_size") or ints("bid_qty"),
            ask_size=ints("ask_size") or ints("ask_qty"),
            expiry=raw.get("expiry"),
            derivative_metrics={
                "iv": raw.get("iv"),
                "delta": raw.get("delta"),
                "gamma": raw.get("gamma"),
                "theta": raw.get("theta"),
                "vega": raw.get("vega"),
                "pcr": raw.get("pcr"),
            },
        )

    def spread_metrics(self) -> dict:
        """§15 mid_price & spread_pct, with UNDEFINED guard."""
        if self.bid is None or self.ask is None:
            return {"spread": "UNDEFINED", "mid_price": None, "spread_pct": None}
        bid, ask = D(self.bid), D(self.ask)
        if bid <= D(0) or ask <= D(0) or ask < bid:
            return {"spread": "UNDEFINED", "mid_price": None, "spread_pct": None, "reason": "INVALID_QUOTE"}
        mid = (bid + ask) / D(2)
        pct = ((ask - bid) / mid * D(100)) if mid > 0 else None
        return {"spread": "DEFINED", "mid_price": mid, "spread_pct": pct}


# ── Technical Analysis Engine §11 ───────────────────────────────────────

@dataclass
class TechnicalState:
    trend: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    momentum: Literal["STRONG", "WEAK", "NEUTRAL"] = "NEUTRAL"
    volume_confirmation: bool = False
    price_vs_vwap: Literal["ABOVE", "BELOW", "AT"] = "AT"
    breakout: bool = False
    breakdown: bool = False
    technical_score: int = 50
    details: dict = field(default_factory=dict)


class TechnicalEngine:
    """Wraps existing quant indicators — configurable set."""

    def analyze(self, candles: list[dict] | None = None, price: Decimal | None = None, indicators: dict | None = None) -> TechnicalState:
        """
        Produce structured state. In production delegates to app.quant.indicators.
        For now rule-based from provided indicators dict.
        """
        if indicators is None:
            indicators = {}

        # Simple scoring: replicate spec's example output
        # Real implementation calls calculate_rsi, macd, vwap etc (already exists)
        try:
            pass
        except Exception:
            pass

        rsi = indicators.get("rsi", 50)
        adx = indicators.get("adx", 15)
        close = D(price) if price is not None else D(indicators.get("close", 0))
        vwap = indicators.get("vwap", close)
        vol_ratio = indicators.get("volume_ratio", 1.0)
        breakout_flag = indicators.get("breakout", False)

        if rsi >= 55 and adx >= 20:
            trend = "BULLISH"
        elif rsi <= 45 and adx >= 20:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"

        momentum = "STRONG" if adx >= 25 else ("WEAK" if adx < 15 else "NEUTRAL")
        price_vs_vwap = "ABOVE" if close > D(vwap) else ("BELOW" if close < D(vwap) else "AT")
        volume_confirmation = vol_ratio >= 1.2
        score = 50
        if trend == "BULLISH": score += 15
        if momentum == "STRONG": score += 10
        if volume_confirmation: score += 10
        if price_vs_vwap == "ABOVE": score += 5
        if breakout_flag: score += 10
        score = max(0, min(100, score))

        return TechnicalState(
            trend=trend, momentum=momentum, volume_confirmation=volume_confirmation,
            price_vs_vwap=price_vs_vwap, breakout=bool(breakout_flag), technical_score=score,
            details=indicators,
        )


# ── Multi-Timeframe Engine §12 ──────────────────────────────────────────

@dataclass
class MTFTimeframeState:
    timeframe: str
    trend: str
    momentum: str
    volatility: str
    structure: str
    support: Decimal | None = None
    resistance: Decimal | None = None
    breakout_state: str = "NONE"
    entry_timing: str = "WAIT"


@dataclass
class MTFBias:
    states: list[MTFTimeframeState] = field(default_factory=list)
    trend_alignment: Literal["ALIGNED", "CONFLICT", "MIXED"] = "MIXED"
    overall_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    conflict: bool = False


class MTFEngine:
    def analyze(self, per_tf: dict[str, dict]) -> MTFBias:
        """
        per_tf: { "1m": {...}, "5m": {...}, "15m": {...}, "1h": {...}, "D": {...} }
        """
        states: list[MTFTimeframeState] = []
        trends: list[str] = []
        for tf in ["1m", "5m", "15m", "1h", "D"]:
            d = per_tf.get(tf, {})
            t = d.get("trend", "NEUTRAL")
            trends.append(t)
            states.append(MTFTimeframeState(
                timeframe=tf, trend=t, momentum=d.get("momentum", "NEUTRAL"),
                volatility=d.get("volatility", "NORMAL"), structure=d.get("structure", "RANGE"),
                support=D(d["support"]) if d.get("support") else None,
                resistance=D(d["resistance"]) if d.get("resistance") else None,
                breakout_state=d.get("breakout_state", "NONE"),
                entry_timing=d.get("entry_timing", "WAIT"),
            ))
        # Alignment logic
        bull_ct = trends.count("BULLISH")
        bear_ct = trends.count("BEARISH")
        if bull_ct >= 4:
            alignment, bias, conflict = "ALIGNED", "BULLISH", False
        elif bear_ct >= 4:
            alignment, bias, conflict = "ALIGNED", "BEARISH", False
        elif bull_ct > 0 and bear_ct > 0:
            alignment, bias, conflict = "CONFLICT", "NEUTRAL", True
        else:
            alignment, bias, conflict = "MIXED", "NEUTRAL", False

        # Higher-timeframe respects strategy config — caller enforces
        return MTFBias(states=states, trend_alignment=alignment, overall_bias=bias, conflict=conflict)


# ── Futures & Options Engine §13 ────────────────────────────────────────

@dataclass
class FoState:
    spot_price: Decimal | None = None
    futures_price: Decimal | None = None
    basis: Decimal | None = None
    futures_oi: int | None = None
    futures_oi_change: int | None = None
    call_oi: int | None = None
    put_oi: int | None = None
    call_oi_change: int | None = None
    put_oi_change: int | None = None
    pcr: Decimal | None = None
    iv: Decimal | None = None
    iv_change: Decimal | None = None
    greeks: dict = field(default_factory=dict)
    buildup_type: str | None = None
    expiry_effect: str | None = None
    # chain support/resistance
    call_writing: bool = False
    put_writing: bool = False
    unusual_oi: bool = False
    unusual_volume: bool = False


class FoEngine:
    def analyze(self, data: dict) -> FoState:
        spot = D(data["spot_price"]) if data.get("spot_price") else None
        fut = D(data["futures_price"]) if data.get("futures_price") else None
        basis = (fut - spot) if spot and fut else None
        # Near expiry distinguish directional vs rollover §13
        days_to_expiry = data.get("days_to_expiry")
        expiry_effect = None
        if days_to_expiry is not None and days_to_expiry <= 2:
            # If OI drop with volume spike → rollover, else directional
            expiry_effect = "ROLLOVER" if data.get("oi_drop") else "DIRECTIONAL"

        put_oi = data.get("put_oi")
        call_oi = data.get("call_oi")
        pcr = None
        if call_oi and call_oi != 0 and put_oi is not None:
            pcr = D(put_oi) / D(call_oi)

        return FoState(
            spot_price=spot, futures_price=fut, basis=basis,
            futures_oi=data.get("futures_oi"), futures_oi_change=data.get("futures_oi_change"),
            call_oi=call_oi, put_oi=put_oi,
            call_oi_change=data.get("call_oi_change"), put_oi_change=data.get("put_oi_change"),
            pcr=pcr, iv=D(data["iv"]) if data.get("iv") else None,
            iv_change=D(data["iv_change"]) if data.get("iv_change") else None,
            greeks=data.get("greeks", {}),
            buildup_type=data.get("buildup_type"),
            expiry_effect=expiry_effect,
            call_writing=bool(data.get("call_writing")),
            put_writing=bool(data.get("put_writing")),
            unusual_oi=bool(data.get("unusual_oi")),
            unusual_volume=bool(data.get("unusual_volume")),
        )


# ── Options Contract Selection §14-15 ───────────────────────────────────

@dataclass
class OptionCandidate:
    instrument_id: str
    symbol: str
    strike: Decimal
    option_type: Literal["CE", "PE"]
    expiry: str
    delta: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    oi: int | None
    volume: int | None
    bid_size: int | None
    ask_size: int | None
    iv: Decimal | None

    def spread(self) -> dict:
        if self.bid is None or self.ask is None:
            return {"spread": "UNDEFINED", "mid": None, "spread_pct": None}
        bid, ask = D(self.bid), D(self.ask)
        if bid <= D(0) or ask <= D(0) or ask < bid:
            return {"spread": "UNDEFINED", "mid": None, "spread_pct": None, "reason": "INVALID_QUOTE"}
        mid = (bid + ask) / D(2)
        pct = ((ask - bid) / mid * D(100)) if mid > 0 else None
        return {"spread": "DEFINED", "mid": mid, "spread_pct": pct}


class OptionsSelector:
    """
    §14 Selection pipeline:
    Direction → Delta candidates → Liquidity → Spread → Volume/OI → Expiry → Margin → Trade Risk → Portfolio Risk → Final
    Delta never overrides veto (§14 last line).
    """

    TARGET_DELTA: Decimal = D("0.60")
    DELTA_RANGE: tuple[Decimal, Decimal] = (D("0.55"), D("0.65"))

    def select(
        self,
        direction: Literal["BULLISH", "BEARISH"],
        candidates: list[OptionCandidate],
        limits: dict | None = None,
         # for later risk checks
        trade_risk_fn=None,
        portfolio_risk_fn=None,
        margin_fn=None,
    ) -> tuple[OptionCandidate | None, str | None]:
        limits = limits or {}
        min_oi = limits.get("min_oi", 10000)
        min_vol = limits.get("min_volume", 5000)
        min_bid = limits.get("min_bid_size", 50)
        min_ask = limits.get("min_ask_size", 50)
        max_spread = D(limits.get("max_spread_pct", 0.5))
        # Direction filter
        want = "CE" if direction == "BULLISH" else "PE"
        filtered = [c for c in candidates if c.option_type == want]
        if not filtered:
            return None, f"NO_CANDIDATES_FOR_{want}"

        # Delta window
        lo, hi = self.DELTA_RANGE
        target = self.TARGET_DELTA
        delta_cands = []
        for c in filtered:
            if c.delta is None:
                continue  # IV null → exclude from Greeks-based selection (§15) OR conservative fallback for existing — but for new entry, exclude
            try:
                d = abs(D(c.delta))
            except Exception:
                continue
            if lo <= d <= hi:
                delta_cands.append(c)
        if not delta_cands:
            # fallback: closest to target
            with_delta = [c for c in filtered if c.delta is not None]
            if not with_delta:
                return None, "NO_VALID_DELTA_CANDIDATES"
            with_delta.sort(key=lambda c: abs(abs(D(c.delta)) - target))
            delta_cands = [with_delta[0]]

        # Sort by delta closeness
        delta_cands.sort(key=lambda c: abs(abs(D(c.delta)) - target))

        # Apply veto chain in order — any veto eliminates candidate
        for cand in delta_cands:
            # Liquidity veto
            if cand.oi is not None and cand.oi < int(min_oi):
                continue
            if cand.volume is not None and cand.volume < int(min_vol):
                continue
            if cand.bid_size is not None and cand.bid_size < int(min_bid):
                continue
            if cand.ask_size is not None and cand.ask_size < int(min_ask):
                continue
            # Spread veto
            sp = cand.spread()
            if sp["spread"] == "UNDEFINED":
                continue
            if sp["spread_pct"] is not None and D(sp["spread_pct"]) > max_spread:
                continue
            # Expiry veto could be added
            # Margin veto
            if margin_fn:
                ok, reason = margin_fn(cand)
                if not ok:
                    continue
            # Trade risk veto
            if trade_risk_fn:
                ok, reason = trade_risk_fn(cand)
                if not ok:
                    continue
            # Portfolio risk veto — last
            if portfolio_risk_fn:
                ok, reason = portfolio_risk_fn(cand)
                if not ok:
                    continue
            # Passed all vetoes
            return cand, None

        return None, "ALL_CANDIDATES_VETOED_BY_LIQUIDITY_SPREAD_RISK_MARGIN"

    def validate_quote(self, cand: OptionCandidate) -> tuple[bool, str | None]:
        """§15 invalid quote guard."""
        if cand.bid is None or cand.ask is None:
            return False, "INVALID_QUOTE_MISSING_BID_ASK"
        bid, ask = D(cand.bid), D(cand.ask)
        if bid <= D(0) or ask <= D(0) or ask < bid:
            return False, "INVALID_QUOTE_BID_ASK"
        if cand.iv is not None:
            try:
                iv = D(cand.iv)
                if not iv.is_finite() or iv.is_nan():
                    return False, "INVALID_IV"
            except Exception:
                return False, "INVALID_IV"
        if cand.delta is not None:
            try:
                d = D(cand.delta)
                if not d.is_finite() or d.is_nan():
                    return False, "INVALID_GREEKS"
            except Exception:
                return False, "INVALID_GREEKS"
        return True, None


# ── Market Regime Engine §19 ────────────────────────────────────────────

class RegimeEngine:
    REGIMES = ["STRONG_BULL","BULL","RANGE","BEAR","STRONG_BEAR","HIGH_VOLATILITY","EVENT_RISK"]

    def classify(self, inputs: dict) -> dict:
        """
        inputs: trend, adx, atr, vix, breadth, price_structure etc.
        Returns regime label + confidence.
        """
        adx = inputs.get("adx", 15)
        vix = inputs.get("vix", 15)
        trend = inputs.get("trend", "NEUTRAL")
        breadth = inputs.get("breadth", 0)
        atr_pct = inputs.get("atr_pct", 1.0)
        event_flag = inputs.get("event_risk", False)

        if event_flag:
            return {"regime": "EVENT_RISK", "confidence": 0.9, "reason": "EVENT_FLAG"}
        if vix >= 24 or atr_pct >= 3:
            return {"regime": "HIGH_VOLATILITY", "confidence": 0.85, "reason": "VIX/ATR_ELEVATED"}
        if trend == "BULLISH" and adx >= 30:
            return {"regime": "STRONG_BULL", "confidence": 0.88, "reason": "TREND_STRONG_BULL"}
        if trend == "BULLISH":
            return {"regime": "BULL", "confidence": 0.75, "reason": "TREND_BULL"}
        if trend == "BEARISH" and adx >= 30:
            return {"regime": "STRONG_BEAR", "confidence": 0.88, "reason": "TREND_STRONG_BEAR"}
        if trend == "BEARISH":
            return {"regime": "BEAR", "confidence": 0.75, "reason": "TREND_BEAR"}
        return {"regime": "RANGE", "confidence": 0.7, "reason": "DEFAULT_RANGE"}


# Singletons
technical_engine = TechnicalEngine()
mtf_engine = MTFEngine()
fo_engine = FoEngine()
options_selector = OptionsSelector()
regime_engine = RegimeEngine()
