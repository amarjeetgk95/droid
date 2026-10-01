"""Support / Resistance Engine (spec §10).

Normalizes levels that already exist in DROID data (value area, pivots, prior
session, Supertrend, option walls, max pain, VWAP, EMA/SMA) into a ranked,
source-attributed level book. Nothing here is invented: a level with no source
is not emitted.
"""
from __future__ import annotations

from app.copilot.models import LevelsBlock, MarketContext, MarketLevel

#: (field, label, weight) — weights are a source-quality prior, not probability.
CLUSTER_ATR_FRACTION = 0.15
PROXIMATE_ATR_FRACTION = 0.20


def _gather_sources(ctx: MarketContext) -> list[tuple[float, str, float]]:
    t = ctx.technicals
    o = ctx.options
    rows: list[tuple[float | None, str, float]] = [
        (t.poc, "POC", 0.85),
        (t.vah, "VAH", 0.80),
        (t.val, "VAL", 0.80),
        (t.supertrend, "Supertrend", 0.75),
        (t.prior_day_high, "Prior day high", 0.70),
        (t.prior_day_low, "Prior day low", 0.70),
        (t.prior_day_close, "Prior day close", 0.60),
        (t.vwap, "VWAP", 0.65),
        (o.call_wall, "Call wall (OI)", 0.75),
        (o.put_wall, "Put wall (OI)", 0.75),
        (o.max_pain, "Max pain", 0.65),
        (t.pivot, "Classic pivot", 0.55),
        (t.r1, "Pivot R1", 0.55),
        (t.r2, "Pivot R2", 0.45),
        (t.s1, "Pivot S1", 0.55),
        (t.s2, "Pivot S2", 0.45),
        (ctx.price.day_high, "Day high", 0.50),
        (ctx.price.day_low, "Day low", 0.50),
        (ctx.price.day_open, "Day open", 0.40),
        (t.ema_20, "EMA20", 0.40),
        (t.ema_50, "EMA50", 0.35),
        (t.sma_200, "SMA200", 0.35),
    ]
    return [(float(price), label, weight) for price, label, weight in rows if price is not None and price > 0]


def _tolerance(ctx: MarketContext) -> float:
    price = ctx.price.ltp or 0.0
    atr = ctx.technicals.atr or 0.0
    return max(price * 0.0005, atr * CLUSTER_ATR_FRACTION)


def _cluster(ctx: MarketContext, rows: list[tuple[float, str, float]]) -> list[MarketLevel]:
    tolerance = _tolerance(ctx)
    price = ctx.price.ltp or 0.0
    clusters: list[dict] = []
    for level_price, label, weight in sorted(rows, key=lambda r: r[0]):
        target = None
        for cluster in clusters:
            if abs(cluster["price"] - level_price) <= tolerance:
                target = cluster
                break
        if target is None:
            clusters.append({"price": level_price, "sources": [label], "weight": weight})
        else:
            total = target["weight"] + weight
            target["price"] = (target["price"] * target["weight"] + level_price * weight) / total
            target["weight"] = total
            target["sources"].append(label)

    levels: list[MarketLevel] = []
    for cluster in clusters:
        distance_pct = round((cluster["price"] - price) / price * 100.0, 4) if price > 0 else None
        above = cluster["price"] > price
        # Multi-source confluence earns a bounded strength boost.
        strength = min(1.0, cluster["weight"] * (1.0 + 0.15 * (len(cluster["sources"]) - 1)))
        levels.append(
            MarketLevel(
                price=round(cluster["price"], 2),
                type="PRIMARY_RESISTANCE" if above else "PRIMARY_SUPPORT",
                source=cluster["sources"],
                strength=round(strength, 4),
                status="ACTIVE",
                distance_pct=distance_pct,
            )
        )
    return levels


def build_levels(ctx: MarketContext, extra: list[tuple[float, str, float]] | None = None) -> LevelsBlock:
    price = ctx.price.ltp
    rows = _gather_sources(ctx)
    if extra:
        rows.extend((float(p), label, weight) for p, label, weight in extra if p and float(p) > 0)
    if price is None or price <= 0 or not rows:
        return LevelsBlock()

    atr = ctx.technicals.atr or 0.0
    proximate = atr * PROXIMATE_ATR_FRACTION
    levels = _cluster(ctx, rows)
    for level in levels:
        if proximate > 0 and abs(level.price - price) <= proximate:
            level.status = "PROXIMATE"

    supports = sorted([lv for lv in levels if lv.price < price], key=lambda lv: lv.price, reverse=True)
    resistances = sorted([lv for lv in levels if lv.price >= price], key=lambda lv: lv.price)

    for index, level in enumerate(supports):
        level.type = "PRIMARY_SUPPORT" if index == 0 else "SECONDARY_SUPPORT"
    for index, level in enumerate(resistances):
        level.type = "PRIMARY_RESISTANCE" if index == 0 else "SECONDARY_RESISTANCE"

    return apply_triggers(ctx, LevelsBlock(support=supports[:4], resistance=resistances[:4]))


def apply_triggers(ctx: MarketContext, block: LevelsBlock) -> LevelsBlock:
    """Triggers always require acceptance, never a single tick (spec §11)."""
    atr = ctx.technicals.atr or 0.0
    buffer_txt = (
        f"with an acceptance buffer of ≈0.15×ATR ({atr * 0.15:,.0f} pts)"
        if atr > 0
        else "with sustained acceptance beyond the level"
    )
    primary_res = block.resistance[0] if block.resistance else None
    primary_sup = block.support[0] if block.support else None
    if primary_res is not None:
        block.bull_trigger = primary_res.price
        block.bull_trigger_note = (
            f"Break and acceptance above {primary_res.price:,.0f} "
            f"({', '.join(primary_res.source[:2])}) — {buffer_txt}; a single tick through the level is not a break."
        )
    if primary_sup is not None:
        block.bear_trigger = primary_sup.price
        block.bear_trigger_note = (
            f"Break and acceptance below {primary_sup.price:,.0f} "
            f"({', '.join(primary_sup.source[:2])}) — {buffer_txt}; a single tick through the level is not a break."
        )
    return block


def evaluate_breakout(ctx: MarketContext, target: float | None) -> dict:
    """Breakout feasibility for an explicit level ("will SENSEX break 75,000?")."""
    price = ctx.price.ltp
    if target is None or price is None:
        return {}
    atr = ctx.technicals.atr or 0.0
    distance = target - price
    atr_units = (distance / atr) if atr > 0 else None
    if abs(distance) < 0.001:
        side = "AT"
    else:
        side = "ABOVE" if distance > 0 else "BELOW"
    required_move_pct = (distance / price * 100.0) if price else None
    return {
        "level": round(float(target), 2),
        "spot": price,
        "side": side,
        "distance_points": round(distance, 2),
        "distance_pct": round(required_move_pct, 4) if required_move_pct is not None else None,
        "distance_atr": round(atr_units, 4) if atr_units is not None else None,
    }

    return levels
