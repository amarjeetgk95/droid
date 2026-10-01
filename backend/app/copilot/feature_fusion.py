"""Feature Fusion (spec §6).

Turns a normalized MarketContext into normalized factors. Each factor is a
weighted committee of independent inputs — a single indicator can never decide
the market state, and a lone input is capped so it cannot dominate the
confluence engine.
"""
from __future__ import annotations

from app.copilot.models import Factor, MarketContext


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _pct_distance(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return (a - b) / b * 100.0


def _atr_distance(price: float | None, level: float | None, atr: float | None) -> float | None:
    if price is None or level is None or not atr or atr <= 0:
        return None
    return (price - level) / atr


class _Votes:
    """Collects one weighted vote per independent input, then normalizes."""

    def __init__(self) -> None:
        self.bull = 0.0
        self.bear = 0.0
        self.count = 0
        self.evidence: list[str] = []

    def vote(self, direction: str, weight: float, note: str) -> None:
        if direction == "BULLISH":
            self.bull += weight
        elif direction == "BEARISH":
            self.bear += weight
        self.count += 1
        self.evidence.append(note)

    def note(self, text: str) -> None:
        self.evidence.append(text)

    def build(self) -> Factor:
        if self.count == 0:
            return Factor(state="UNKNOWN", strength=0.0, confidence=0.0, evidence=self.evidence)
        total = self.bull + self.bear
        if total <= 0:
            return Factor(state="NEUTRAL", strength=0.0, confidence=0.0, evidence=self.evidence)
        net = (self.bull - self.bear) / total
        strength = _clamp(abs(net) * min(1.0, self.count / 2.0), 0.0, 1.0)
        if self.count < 2:
            # A single indicator must never carry a full-strength claim.
            strength = min(strength, 0.45)
        if abs(net) < 0.05:
            return Factor(state="NEUTRAL", strength=0.0, confidence=0.0, evidence=self.evidence)
        state = "BULLISH" if net > 0 else "BEARISH"
        confidence = _clamp(self.count / 4.0, 0.0, 1.0) * _clamp(0.4 + abs(net) * 0.6, 0.0, 1.0)
        return Factor(
            state=state,  # type: ignore[arg-type]
            strength=round(strength, 4),
            confidence=round(confidence, 4),
            evidence=self.evidence,
        )


def fuse_trend(ctx: MarketContext) -> Factor:
    v = _Votes()
    t = ctx.technicals
    price = ctx.price.ltp
    if t.supertrend_direction:
        suffix = f" @ {t.supertrend:,.0f}" if t.supertrend else ""
        v.vote(t.supertrend_direction, 1.0, f"Supertrend {t.supertrend_direction}{suffix}")
    if ctx.regime.name == "TRENDING_BULLISH":
        v.vote("BULLISH", 0.8, "Regime TRENDING_BULLISH")
    elif ctx.regime.name == "TRENDING_BEARISH":
        v.vote("BEARISH", 0.8, "Regime TRENDING_BEARISH")
    elif ctx.regime.name not in ("UNKNOWN", ""):
        v.note(f"Regime {ctx.regime.name}")
    if ctx.regime.adx is not None:
        if ctx.regime.adx >= 25:
            v.note(f"ADX {ctx.regime.adx:.1f} (established trend)")
        elif ctx.regime.adx < 20:
            v.note(f"ADX {ctx.regime.adx:.1f} (weak trend)")
    if price is not None and t.ema_20 is not None:
        v.vote(
            "BULLISH" if price >= t.ema_20 else "BEARISH",
            0.7,
            f"Price {'above' if price >= t.ema_20 else 'below'} EMA20 {t.ema_20:,.0f}",
        )
    if price is not None and t.sma_200 is not None:
        v.vote(
            "BULLISH" if price >= t.sma_200 else "BEARISH",
            0.6,
            f"Price {'above' if price >= t.sma_200 else 'below'} SMA200 {t.sma_200:,.0f}",
        )
    if price is not None and t.supertrend:
        v.vote("BULLISH" if price >= t.supertrend else "BEARISH", 0.5, "Price vs Supertrend level")
    return v.build()


def fuse_momentum(ctx: MarketContext) -> Factor:
    v = _Votes()
    t = ctx.technicals
    price = ctx.price.ltp
    if t.rsi is not None:
        if t.rsi >= 60:
            v.vote("BULLISH", 0.9, f"RSI {t.rsi:.1f}")
        elif t.rsi <= 40:
            v.vote("BEARISH", 0.9, f"RSI {t.rsi:.1f}")
        else:
            v.note(f"RSI {t.rsi:.1f} (balanced)")
    if price is not None and t.vwap is not None:
        v.vote(
            "BULLISH" if price >= t.vwap else "BEARISH",
            0.9,
            f"Price {'above' if price >= t.vwap else 'below'} session VWAP {t.vwap:,.0f}",
        )
    if t.plus_di is not None and t.minus_di is not None:
        v.vote(
            "BULLISH" if t.plus_di >= t.minus_di else "BEARISH",
            0.6,
            f"+DI {t.plus_di:.1f} vs -DI {t.minus_di:.1f}",
        )
    if ctx.price.change_pct is not None:
        direction = "BULLISH" if ctx.price.change_pct > 0 else ("BEARISH" if ctx.price.change_pct < 0 else "NEUTRAL")
        v.vote(direction, 0.5, f"Day change {ctx.price.change_pct:+.2f}%")
    return v.build()


def fuse_volatility(ctx: MarketContext) -> Factor:
    """Volatility is a state factor, never a directional one."""
    v = _Votes()
    t = ctx.technicals
    atr_pct = _pct_distance(t.atr, ctx.price.ltp)
    if atr_pct is not None:
        v.note(f"ATR {t.atr:,.1f} ({atr_pct:.2f}% of spot)")
    if t.bollinger_bandwidth is not None:
        tag = "compressed" if t.bollinger_bandwidth <= 2.2 else ("expanded" if t.bollinger_bandwidth >= 4.5 else "normal")
        v.note(f"Bollinger bandwidth {t.bollinger_bandwidth:.2f}% ({tag})")
    if ctx.regime.vix is not None:
        v.note(f"India VIX {ctx.regime.vix:.2f} ({ctx.regime.vix_category or 'unclassified'})")
    if ctx.regime.name == "COMPRESSION_SQUEEZE":
        v.note("Regime COMPRESSION_SQUEEZE (expansion risk)")
    elif ctx.regime.name == "VOLATILE_EXPANSION":
        v.note("Regime VOLATILE_EXPANSION")
    if v.count == 0:
        return Factor(state="UNKNOWN", strength=0.0, confidence=0.0, evidence=v.evidence)
    return Factor(
        state="NEUTRAL",
        strength=0.0,
        confidence=round(_clamp(v.count / 3.0, 0.0, 1.0), 4),
        evidence=v.evidence,
    )



def fuse_market_structure(ctx: MarketContext) -> Factor:
    v = _Votes()
    price = ctx.price.ltp
    t = ctx.technicals
    if price is None:
        return v.build()
    if t.vah is not None and price > t.vah:
        v.vote("BULLISH", 0.8, f"Price above value-area high {t.vah:,.0f}")
    elif t.val is not None and price < t.val:
        v.vote("BEARISH", 0.8, f"Price below value-area low {t.val:,.0f}")
    elif t.poc is not None:
        v.vote("BULLISH" if price >= t.poc else "BEARISH", 0.5, f"Price vs POC {t.poc:,.0f}")
    if t.prior_day_high is not None:
        v.vote(
            "BULLISH" if price > t.prior_day_high else "BEARISH",
            0.6,
            f"Price vs prior-day high {t.prior_day_high:,.0f}",
        )
    if t.prior_day_low is not None:
        v.vote(
            "BULLISH" if price >= t.prior_day_low else "BEARISH",
            0.4,
            f"Price vs prior-day low {t.prior_day_low:,.0f}",
        )
    if t.pivot is not None:
        v.vote("BULLISH" if price >= t.pivot else "BEARISH", 0.5, f"Price vs classic pivot {t.pivot:,.0f}")
    return v.build()


def fuse_options_positioning(ctx: MarketContext) -> Factor:
    v = _Votes()
    o = ctx.options
    price = ctx.price.ltp
    if o.pcr_oi is not None:
        if o.pcr_oi >= 1.15:
            v.vote("BULLISH", 0.8, f"PCR(OI) {o.pcr_oi:.2f} (put writers dominant)")
        elif o.pcr_oi <= 0.85:
            v.vote("BEARISH", 0.8, f"PCR(OI) {o.pcr_oi:.2f} (call writers dominant)")
        else:
            v.note(f"PCR(OI) {o.pcr_oi:.2f} (balanced)")
    if o.max_pain is not None and price is not None:
        v.vote(
            "BEARISH" if price > o.max_pain else ("BULLISH" if price < o.max_pain else "NEUTRAL"),
            0.6,
            f"Spot vs max pain {o.max_pain:,.0f} (expiry gravity)",
        )
    if o.call_wall is not None:
        v.note(f"Call wall {o.call_wall:,.0f}")
    if o.put_wall is not None:
        v.note(f"Put wall {o.put_wall:,.0f}")
    if o.atm_iv is not None:
        v.note(f"ATM IV {o.atm_iv:.2%}" if o.atm_iv < 3 else f"ATM IV {o.atm_iv:.2f}")
    return v.build()


def fuse_futures_positioning(ctx: MarketContext) -> Factor:
    v = _Votes()
    f = ctx.futures
    if f.positioning:
        mapping = {
            "LONG_BUILDUP": ("BULLISH", 0.9, "4-quadrant: long buildup"),
            "SHORT_BUILDUP": ("BEARISH", 0.9, "4-quadrant: short buildup"),
            "SHORT_COVERING": ("BULLISH", 0.8, "4-quadrant: short covering"),
            "LONG_UNWINDING": ("BEARISH", 0.8, "4-quadrant: long unwinding"),
        }
        vote = mapping.get(f.positioning.upper())
        if vote:
            v.vote(vote[0], vote[1], vote[2])
        else:
            v.note(f"Futures positioning {f.positioning}")
    if f.basis_pct is not None:
        v.note(f"Basis {f.basis_pct:+.2f}% ({f.curve_state or 'curve n/a'})")
    if f.oi_change_pct is not None:
        v.note(f"Futures OI change {f.oi_change_pct:+.2f}%")
    return v.build()


def fuse_institutional_flow(ctx: MarketContext) -> Factor:
    """FII/DII is a daily publication. Without a live feed it stays UNKNOWN."""
    if not ctx.institutional_flow.live or ctx.institutional_flow.net_flow is None:
        note = (
            "Flow feed is a static daily snapshot — not usable as live positioning."
            if ctx.institutional_flow.sentiment
            else "Institutional flow unavailable."
        )
        return Factor(state="UNKNOWN", strength=0.0, confidence=0.0, evidence=[note])
    v = _Votes()
    v.vote(
        "BULLISH" if ctx.institutional_flow.net_flow > 0 else "BEARISH",
        0.9,
        f"Net institutional cash flow {ctx.institutional_flow.net_flow:+,.0f} cr on {ctx.institutional_flow.as_of or '—'}",
    )
    return v.build()


def fuse_liquidity(ctx: MarketContext) -> Factor:
    evidence: list[str] = []
    if ctx.price.volume is None:
        return Factor(state="UNKNOWN", strength=0.0, confidence=0.0, evidence=["Session volume unavailable."])
    evidence.append(f"Session volume {ctx.price.volume:,.0f}")
    confidence = 0.25
    if ctx.technicals.atr and ctx.price.ltp:
        evidence.append(f"ATR {ctx.technicals.atr:,.1f} vs spot {ctx.price.ltp:,.0f}")
        confidence = 0.35
    return Factor(state="NEUTRAL", strength=0.0, confidence=confidence, evidence=evidence)




def fuse_breakout_pressure(ctx: MarketContext) -> Factor:
    """How close price is to escaping its recent boundary, in ATR units."""
    v = _Votes()
    price = ctx.price.ltp
    atr = ctx.technicals.atr
    t = ctx.technicals
    upside = _atr_distance(price, t.vah, atr)
    downside = _atr_distance(price, t.val, atr)
    if upside is not None:
        if upside > 0:
            v.vote("BULLISH", 0.8, f"Price {upside:+.2f} ATR above VAH {t.vah:,.0f}")
        else:
            v.vote("BULLISH" if upside > -0.5 else "BEARISH", 0.5, f"Price {upside:+.2f} ATR vs VAH {t.vah:,.0f}")
    if downside is not None:
        if downside < 0:
            v.vote("BEARISH", 0.8, f"Price {downside:+.2f} ATR below VAL {t.val:,.0f}")
        else:
            v.vote("BEARISH" if downside < 0.5 else "BULLISH", 0.5, f"Price {downside:+.2f} ATR vs VAL {t.val:,.0f}")
    if t.bollinger_bandwidth is not None and t.bollinger_bandwidth <= 2.2:
        v.note(f"Compressed bands ({t.bollinger_bandwidth:.2f}%) — breakout risk elevated")
    if ctx.regime.adx is not None and ctx.regime.adx >= 25:
        v.note(f"ADX {ctx.regime.adx:.1f} confirms directional expansion")
    if ctx.regime.name == "COMPRESSION_SQUEEZE":
        v.note("Regime COMPRESSION_SQUEEZE")
    return v.build()


def fuse_mean_reversion_pressure(ctx: MarketContext) -> Factor:
    """Directional reversion pull: stretched above value pulls down, and vice versa."""
    v = _Votes()
    price = ctx.price.ltp
    atr = ctx.technicals.atr
    t = ctx.technicals
    for level, label in ((t.poc, "POC"), (t.vwap, "VWAP")):
        dist = _atr_distance(price, level, atr)
        if dist is None:
            continue
        if dist >= 1.5:
            v.vote("BEARISH", 0.7, f"Price {dist:+.2f} ATR from {label} {level:,.0f} (stretched above)")
        elif dist <= -1.5:
            v.vote("BULLISH", 0.7, f"Price {dist:+.2f} ATR from {label} {level:,.0f} (stretched below)")
        else:
            v.note(f"Price within {abs(dist):.2f} ATR of {label}")
    if t.rsi is not None and (t.rsi >= 70 or t.rsi <= 30):
        v.vote("BEARISH" if t.rsi >= 70 else "BULLISH", 0.6, f"RSI {t.rsi:.1f} (extreme)")
    if ctx.regime.name.startswith("RANGE"):
        v.note(f"Regime {ctx.regime.name} favours mean reversion")
    return v.build()


def derive_factors(ctx: MarketContext) -> dict[str, Factor]:
    """Full factor set (spec §6). Keys are a stable API contract."""
    return {
        "trend": fuse_trend(ctx),
        "momentum": fuse_momentum(ctx),
        "volatility": fuse_volatility(ctx),
        "market_structure": fuse_market_structure(ctx),
        "options_positioning": fuse_options_positioning(ctx),
        "futures_positioning": fuse_futures_positioning(ctx),
        "institutional_flow": fuse_institutional_flow(ctx),
        "liquidity": fuse_liquidity(ctx),
        "breakout_pressure": fuse_breakout_pressure(ctx),
        "mean_reversion_pressure": fuse_mean_reversion_pressure(ctx),
    }
